from pathlib import Path
from queue import Queue
import io
import os
import platform
import subprocess
import sys
import threading

SENTINEL = object()
WIN = platform.system() == 'Windows'


class Streamer:

    def __init__(self, stream=None, name=None):
        self.in_stream = Queue() if stream is None else stream
        self.name = name or id(self)

    def reader(self):
        # handle queues
        if isinstance(self.in_stream, Queue):
            while True:
                chunk = self.in_stream.get()
                if chunk == SENTINEL:
                    return
                yield chunk

        # handles buffers
        for chunk in iter(lambda: self.in_stream.readline(2048), ""):
            if not chunk:
                return
            yield chunk
        # try:
        # except ValueError:
        #     # readline raises a ValueError on closed stream
        #     pass

    def writer(self, generator, out_stream, autoclose=False):
        if isinstance(out_stream, Queue):
            # handle queues
            for chunk in generator:
                out_stream.put(chunk)
            out_stream.put(SENTINEL)
        else:
            # handle buffers
            mode = getattr(out_stream, 'mode', None)
            write = out_stream.buffer.write if mode == 'w' else out_stream.write
            for chunk in generator:
                write(chunk)
                out_stream.flush()
            if autoclose:
                out_stream.close()

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
        self.stdin = None
        self.stdout = None
        self.stderr = None
        self.parent = None

    def clone(self, *extra_args):
        return Cmd(self.cmd_path, *(self.args + extra_args))

    def setup(self, stdin=None, stdout=None, stderr=None):
        if stdin:
            self.stdin = stdin
        if stdout:
            self.stdout = stdout
        if stderr:
            self.stderr = stderr

    def __call__(self, *extra_args):
        # Create buffers for stderr and stdout
        out_buff = io.BytesIO()
        err_buff = io.BytesIO()
        # And plug them
        self.setup(stdout=out_buff, stderr=err_buff)
        # Run subprocess
        errcode = self.run(*extra_args)
        return Result(errcode, out_buff.getvalue(),
                      err_buff.getvalue())

    def run(self, *extra_args):
        # Start subprocess
        process = subprocess.Popen(
            (str(self.cmd_path),) + self.args + extra_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
        )

        # Plug io
        out_thread = Streamer(
            process.stdout,
            name=str(self)
        ).plug(self.stdout or sys.stdout)
        err_thread = Streamer(
            process.stderr,
            name=str(self) + ' - stderr',
        ).plug(self.stderr or sys.stderr)
        if self.stdin:
            # XXX stdin should be a queue (or a buffer), not a stream!
            if isinstance(self.stdin, Streamer):
                self.stdin.plug(process.stdin, autoclose=True)
            else:
                Streamer(self.stdin).plug(process.stdin, autoclose=True)

        # Start parent
        parent_thread = None
        if self.parent:
            parent_thread = threading.Thread(target=self.parent.run).start()

        # Wait for process to finish
        errcode = process.wait()
        # Wait for streamers to finish
        out_thread.join()
        err_thread.join()
        # Close file descriptors
        process.stdin.close()
        process.stdout.close()
        process.stderr.close()
        # Close parent thread
        if parent_thread:
            parent_thread.join()

        return errcode

    def pipe(self, something, *args):
        if isinstance(something, Cmd):
            return self.pipe_cmd(something, *args)
        elif callable(something):
            return self.pipe_func(something, *args)
        else:
            raise ValueError('Unable to pipe to type: "%s"' % type(something))

    def pipe_func(self, fn):
        func = Func(fn)
        pipe_stream = Streamer(name='func pipe')
        self.setup(stdout=pipe_stream)
        func.setup(stdin=pipe_stream)
        func.set_parent(self)
        return func

    def pipe_cmd(self, cmd, *args):
        # Chain IO
        if not isinstance(cmd, Cmd):
            other = Cmd(cmd, *args)
        elif args:
            other = cmd.clone(*args)
        else:
            other = cmd
        pipe_stream = Streamer(name='cmd pipe')
        self.setup(stdout=pipe_stream)
        other.setup(stdin=pipe_stream)
        other.set_parent(self)
        return other

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
        self.setup(stdin=open(other, 'rb'))
        return self


class Func:

    def __init__(self, fn, *args):
        self.fn = fn
        self.args = args
        self.stdin = None
        self.stdout = None
        self.stderr = None
        self.parent = None

    def pipe(self, cmd):
        pipe_stream = Streamer(name='func pipe')
        self.setup(stdout=pipe_stream)
        cmd.setup(stdin=pipe_stream)
        cmd.set_parent(self)
        return cmd

    def run(self):
        for chunk in self.fn(*self.args):
            self.stdout.in_stream.put(chunk.encode())
        self.stdout.in_stream.put(SENTINEL)

    def set_parent(self, parent):
        self.parent = parent

    def setup(self, stdin=None, stdout=None, stderr=None):
        if stdin:
            self.stdin = stdin
        if stdout:
            self.stdout = stdout
        if stderr:
            self.stderr = stderr

    def __call__(self, *extra_args):
        self.parent.run()
        for chunk in self.stdin.reader():
            yield self.fn(chunk.decode(), *self.args)

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
    Cmd(*sys.argv[1:]).run()
