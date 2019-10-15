from pathlib import Path
import io
import os
import platform
import subprocess
import sys
import threading

WIN = platform.system() == 'Windows'


class Streamer:

    def __init__(self, stream=None, name=None):
        self.in_stream = stream
        self.name = name or id(self)

    def reader(self):
        # handles buffers
        if hasattr(self.in_stream, 'readline'):
            for chunk in iter(lambda: self.in_stream.readline(2048), ""):
                if not chunk:
                    return
                yield chunk

        # handle iterable
        else:
            yield from self.in_stream

    def writer(self, generator, out_stream, autoclose=False):
        if hasattr(out_stream, 'write'):
            # handle buffers
            mode = getattr(out_stream, 'mode', None)
            write = out_stream.buffer.write if mode == 'w' else out_stream.write
            for chunk in generator:
                write(chunk)
                out_stream.flush()
            if autoclose:
                out_stream.close()
        else:
            raise ValueError('Can not handle "%s"' % out_stream)

    def _plug(self, out_stream, autoclose=False):
        if isinstance(out_stream, Streamer):
            # Daisy chain streams
            out_stream = out_stream.in_stream
        self.writer(self.reader(), out_stream, autoclose=autoclose)

    def plug(self, out_stream, autoclose=False):
        t = threading.Thread(target=self._plug, args=(out_stream, autoclose))
        t.start()
        return t


class Cmd:

    def __init__(self, cmd, *args):
        if os.path.isfile(cmd):
            self.cmd_path = cmd
        else:
            if WIN and not cmd.endswith('.exe'):
                cmd += '.exe'
            # Resolve full path
            cmd_path = None
            for p in os.environ.get('PATH', '').split(os.pathsep):
                if not os.path.isdir(p):
                    continue
                if cmd in os.listdir(p):
                    cmd_path = Path(p) / cmd
                    break
            else:
                raise Exception(f'Command not found: {cmd}')
            self.cmd_path = cmd_path

        self.args = args
        self.parent= None
        self.redirect_stdin = None

    def run(self, extra_args=tuple()):
        '''
        Create process instance, plug file descriptor (stdin) to parent
        process one (stdout) if any.
        '''
        parent_proc = parent_func = stdin = None
        if self.redirect_stdin:
            stdin = open(self.redirect_stdin, 'rb')
        elif self.parent and isinstance(self.parent, Cmd):
            parent_proc = self.parent.run()
            stdin = parent_proc.process.stdout
        elif self.parent and isinstance(self.parent, Func):
            parent_func = self.parent.run(extra_args)
            stdin = subprocess.PIPE

        proc = Process(
            str(self.cmd_path),
            self.args + extra_args,
            stdin=stdin,
            stderr=sys.stderr,
        )

        if parent_proc:
            # Will eventually close fd's
            parent_proc.detach()
        elif parent_func:
            proc.pull_stdin(parent_func)# -> todo close stdin in some way

        return proc

    def clone(self, *extra_args):
        return Cmd(self.cmd_path, *(self.args + extra_args))

    def __call__(self, *extra_args):
        return self.communicate(extra_args)

    def communicate(self, extra_args=tuple()):
        process = self.run(extra_args)

        # Create buffers for stderr and stdout
        out_buff = io.BytesIO()
        process.push_stdout(out_buff)
        err_buff = io.BytesIO()
        process.push_stderr(out_buff)
        process.wait()
        return Result(process.errcode, out_buff.getvalue(),
                      err_buff.getvalue())

    def pipe_cmd(self, cmd, *args):
        # Chain commands
        if not isinstance(cmd, Cmd):
            other = Cmd(cmd, *args)
        elif args:
            other = cmd.clone(*args)
        else:
            other = cmd
        other.set_parent(self)
        return other

    def pipe_func(self, fn):
        func = Func(fn)
        func.set_parent(self)
        return func

    def pipe(self, something, *args):
        if isinstance(something, Cmd):
            return self.pipe_cmd(something, *args)
        elif isinstance(something, str):
            return self.pipe_cmd(something, *args)
        elif callable(something):
            return self.pipe_func(something, *args)
        else:
            raise ValueError('Unable to pipe to type: "%s"' % type(something))

    def set_parent(self, parent):
        assert self.parent is None
        self.parent = parent

    def __add__(self, arg):
        return self.clone(arg)

    def __sub__(self, arg):
        return self.clone(f'-{arg}')

    def __truediv__(self, arg):
        return self.clone(f'/{arg}')

    def __or__(self, other):
        return self.pipe(other)

    def __str__(self):
        args = ' '.join(self.args)
        return f'{self.cmd_path} {args}'

    def __lt__(self, other):
        self.redirect_stdin = other
        return self


class Process:

    def __init__(self, cmd, args, stdin=None, stdout=None, stderr=None):
        self.cmd = cmd
        self.process = subprocess.Popen(
            (cmd,) + args,
            stdout=stdout or subprocess.PIPE,
            stderr=stderr or subprocess.PIPE,
            stdin=stdin or subprocess.PIPE,
        )
        self.errcode = None
        self.to_join = []

    def push_stdout(self, output):
        if not self.process.stdout:
            return
        thread = Streamer(self.process.stdout).plug(output)
        self.to_join.append(thread)

    def push_stderr(self, output):
        if not self.process.stderr:
            return
        thread = Streamer(self.process.stderr).plug(output)
        self.to_join.append(thread)

    def pull_stdin(self, input_):
        if not self.process.stdin:
            return
        thread = Streamer(input_).plug(self.process.stdin, autoclose=True)
        self.to_join.append(thread)

    def wait(self):
        self.errcode = self.process.wait()
        for thread in self.to_join:
            thread.join()
        for stream in (self.process.stdin, self.process.stdout,
                       self.process.stderr):
            if not stream:
                continue
            stream.close()
        return self.errcode

    def detach(self):
        t = threading.Thread(target=self.wait)
        t.start()
        return t


class Func:

    def __init__(self, fn, *args):
        self.fn = fn
        self.args = args
        self.parent = None

    def pipe(self, cmd):
        cmd.set_parent(self)
        return cmd

    def run(self, args):
        if self.parent:
            parent_proc = self.parent.run()
            stdin = parent_proc.process.stdout
            reader = Streamer(stdin).reader()
            parent_proc.detach()
            for chunk in reader:
                yield self.fn(chunk.decode(), *args)
        else:
            for chunk in self.fn():
                yield chunk.encode()

    def set_parent(self, parent):
        self.parent = parent

    def __call__(self, *extra_args):
        return self.run(self.args + extra_args)

    def __or__(self, other):
        return self.pipe(other)


class Result:

    def __init__(self, errcode, stdout, stderr):
        self.errcode = errcode
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self):
        return self.stdout.decode()

    def __eq__(self, other):
        if isinstance(other, bytes):
            return self.stdout == other
        return self.stdout.decode() == other

    def __repr__(self):
        return f'<Result(errorcode={self.errcode})>'

    def __gt__(self, other):
        with open(other, 'wb') as fh:
            fh.write(self.stdout)
        return self.errcode


class SH:

    def __getattr__(self, name):
        return Cmd(name)

sh = SH()


if __name__ == '__main__':
    print(Cmd(*sys.argv[1:]).communicate())
