from pathlib import Path
import io
import os
import platform
import types
import subprocess
import sys
import threading
try:
    import paramiko
except ImportError:
    paramiko = None

WIN = platform.system() == 'Windows'
ellipsis = lambda x: x if len(x) < 40 else x[:40] + '...'


class Streamer:

    def __init__(self, stream=None, name=None):
        self.in_stream = stream
        self.name = name or id(self)

    def reader(self):
        # handles buffers
        if hasattr(self.in_stream, 'readline'):
            try:
                for chunk in iter(lambda: self.in_stream.readline(2048), ""):
                    if not chunk:
                        return
                    yield chunk
            except ValueError:
                # readline raises a valueerror on closed paramiko chan
                return
        # handle iterable
        elif isinstance(self.in_stream, types.GeneratorType):
            yield from self.in_stream
        else:
            raise ValueError(
                f'Unable to consume "{self.in_stream}" of type '
                f'{type(self.in_stream)} as stream input')

    def writer(self, generator, out_stream, autoclose=False):
        if hasattr(out_stream, 'write'):
            # handle buffers
            has_buff = hasattr(out_stream, 'buffer')
            write = out_stream.buffer.write if has_buff else out_stream.write
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
            stdin = self.redirect_stdin
        elif self.parent and isinstance(self.parent, (Cmd, RemoteCmd)):
            parent_proc = self.parent.run()
            stdin = parent_proc.stdout
        elif self.parent and isinstance(self.parent, Func):
            parent_func = self.parent.run()
            stdin = parent_func

        proc = Process(
            str(self.cmd_path),
            self.args + extra_args,
            stdin=stdin,
        )

        if parent_proc:
            # Will eventually close fd's
            parent_proc.detach()
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
        process.push_stderr(err_buff)
        process.wait()
        return Result(process.errcode, out_buff.getvalue(),
                      err_buff.getvalue())

    def pipe_cmd(self, cmd, *args):
        # Chain commands
        if not isinstance(cmd, (Cmd, RemoteCmd)):
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
        if isinstance(something, (Cmd, RemoteCmd)):
            return self.pipe_cmd(something, *args)
        elif isinstance(something, str):
            return self.pipe_cmd(something, *args)
        elif callable(something):
            return self.pipe_func(something, *args)
        else:
            raise ValueError(f'Unable to pipe to type: "{type(something)}"')

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
        if isinstance(other, Result):
            self.redirect_stdin = io.BytesIO(other.stdout)
        else:
            self.redirect_stdin = open(other, 'rb')
        return self


class Process:

    def __init__(self, cmd, args, stdin=None):
        self.cmd = cmd

        # Check if stdin is a readable filehandle
        is_stdin_fh = isinstance(stdin, io.BufferedReader)
        self.process = subprocess.Popen(
            (cmd,) + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=stdin if is_stdin_fh else subprocess.PIPE,
        )
        self.stdout = self.process.stdout
        self.stderr = self.process.stderr
        self.stdin = self.process.stderr
        self.errcode = None
        self.to_join = []
        if stdin is not None and not is_stdin_fh:
            self.pull_stdin(stdin)

    def push_stdout(self, output):
        thread = Streamer(self.process.stdout).plug(output)
        self.to_join.append(thread)

    def push_stderr(self, output):
        thread = Streamer(self.stderr).plug(output)
        self.to_join.append(thread)

    def pull_stdin(self, input_):
        thread = Streamer(input_).plug(self.process.stdin, autoclose=True)
        self.to_join.append(thread)

    def wait(self):
        self.errcode = self.process.wait()
        for thread in self.to_join:
            thread.join()
        for stream in (self.stdin, self.stdout, self.stderr):
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

    def pipe(self, other):
        assert isinstance(other, (Cmd, RemoteCmd))
        other.set_parent(self)
        return cmd

    def run(self, args=tuple()):
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

    @property
    def success(self):
        return self.errcode == 0

    def __str__(self):
        return self.stdout.decode()

    def __eq__(self, other):
        if isinstance(other, bytes):
            return self.stdout == other
        return self.stdout.decode() == other

    def __repr__(self):
        extra = ''
        if self.stdout:
            stdout = ellipsis(repr(self.stdout)[2:-1])
            extra += f" stdout='{stdout}'"
        if self.stderr:
            stderr = ellipsis(repr(self.stderr)[2:-1])
            extra += f" stderr='{stderr}'"
        return f'<Result(errorcode={self.errcode}{extra})>'

    def __gt__(self, other):
        if isinstance(other, Cmd):
            return other.__lt__(self)
        elif isinstance(other, (str, bytes)):
            with open(other, 'wb') as fh:
                fh.write(self.stdout)
            return self.errcode
        else:
            raise ValueError(f'Unable to pipe "{other}" of type "{type(other)}"')



class SSH:

    _connection_cache = {}

    def __init__(self, host, password=None, private_key=None):
        if host in self._connection_cache:
            self.client = self._connection_cache[host]
            return

        if private_key:
            private_key = os.path.expanduser(private_key)
            if not os.path.exists(private_key):
                msg = f'Private key file "{private_key}" not found'
                raise FileNotFoundError(msg)
            password = self.get_passphrase(private_key)
        else:
            password = self.get_password(host)

        if '@' in host:
            username, hostname = host.split('@', 1)
        else:
            hostname = host
            username = None
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname, username=username, password=password,
                       key_filename=private_key,
        )
        self._connection_cache[host] = client
        self.client = client


    def get_password(self, host):
        pass

    def __getattr__(self, cmd):
        return RemoteCmd(self, cmd)



class RemoteCmd:

    def __init__(self, ssh, cmd, args=tuple()):
        self.ssh = ssh
        self.cmd = cmd
        self.args = args
        self.parent= None
        self.redirect_stdin = None

    def run(self, extra_args=tuple()):
        parent_proc = parent_func = stdin = None
        if self.redirect_stdin:
            stdin = self.redirect_stdin
        elif self.parent and isinstance(self.parent, (Cmd, RemoteCmd)):
            parent_proc = self.parent.run()
            stdin = parent_proc.process.stdout
        elif self.parent and isinstance(self.parent, Func):
            parent_func = self.parent.run()
            stdin = parent_func

        proc = RemoteProcess(self.ssh.client, self.cmd, self.args + extra_args,
                             stdin=stdin)
        if parent_proc:
            # Will eventually close fd's
            parent_proc.detach()
        return proc

    def __call__(self, *extra_args):
        return self.communicate(extra_args)

    def communicate(self, extra_args=tuple()):
        process = self.run(extra_args)

        # Create buffers for stderr and stdout
        out_buff = io.BytesIO()
        process.push_stdout(out_buff)
        err_buff = io.BytesIO()
        process.push_stderr(err_buff)
        process.wait()
        return Result(process.errcode, out_buff.getvalue(),
                      err_buff.getvalue())
    def __or__(self, other):
        return self.pipe(other)

    def set_parent(self, parent):
        assert self.parent is None
        self.parent = parent

    def clone(self, *extra_args):
        return RemoteCmd(self.ssh, self.cmd, extra_args)

    def pipe_cmd(self, cmd, *args):
        # Chain commands
        if not isinstance(cmd, (Cmd, RemoteCmd)):
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
        if isinstance(something, (Cmd, RemoteCmd)):
            return self.pipe_cmd(something, *args)
        elif isinstance(something, str):
            return self.pipe_cmd(something, *args)
        elif callable(something):
            return self.pipe_func(something, *args)
        else:
            raise ValueError(f'Unable to pipe to type: "{type(something)}"')

    def __add__(self, arg):
        return self.clone(arg)

    def __sub__(self, arg):
        return self.clone(f'-{arg}')

    def __truediv__(self, arg):
        return self.clone(f'/{arg}')

    def __str__(self):
        args = ' '.join(self.args)
        return f'{self.cmd_path} {args}'

    def __lt__(self, other):
        if isinstance(other, Result):
            self.redirect_stdin = io.BytesIO(other.stdout)
        else:
            self.redirect_stdin = open(other, 'rb')
        return self


class RemoteProcess:

    def __init__(self, client, cmd, args=None, stdin=None):
        self.errcode = None
        self.chan = client.get_transport().open_session()
        self.stdin = self.chan.makefile('wb')
        self.stdout = self.chan.makefile('rb')
        self.stderr = self.chan.makefile_stderr('rb')
        self.chan.exec_command(cmd + ' ' + ' '.join(args))

        self.to_join = []
        if stdin:
            # XXX use a real buff (not a simple str) ?
            self.pull_stdin(stdin)

    def wait(self):
        self.errcode = self.chan.recv_exit_status()
        for thread in self.to_join:
            thread.join()
        for stream in (self.stdin, self.stdout, self.stderr):
            stream.flush()
            stream.close()
        self.chan.shutdown_write()
        return self.errcode

    def pull_stdin(self, input_):
        thread = Streamer(input_).plug(self.stdin, autoclose=True)
        self.to_join.append(thread)

    def push_stdout(self, output):
        thread = Streamer(self.stdout).plug(output)
        self.to_join.append(thread)

    def push_stderr(self, output):
        thread = Streamer(self.stderr).plug(output)
        self.to_join.append(thread)

    def detach(self):
        t = threading.Thread(target=self.wait)
        t.start()
        return t


class SH:

    def __getattr__(self, name):
        return Cmd(name)
sh = SH()


if __name__ == '__main__':
    print(Cmd(*sys.argv[1:]).communicate())
