# Conquer

Conquer is a small python3 utility to help run commands. It supports
Linux, Windows, MacOS and supports running commands over SSH.

It is inspired by [amoffat's sh](https://github.com/amoffat/sh) module.

## Example usage

The basic usage is to use the magic object `sh`, that lets you
instantiate command objects and run them:

    >>> from conquer import sh
    >>> sh.pwd()
    '/\n'

    >>> print(sh.ls('-l'))
    total 104
    drwxr-xr-x   2 root root  4096 aoû 20  2018 bin
    drwxr-xr-x   4 root root  4096 aoû 25  2018 boot
    drwxr-xr-x  19 root root  3260 sep 20 18:53 dev
    drwxr-xr-x 161 root root 12288 oct  8 18:50 etc
    drwxr-xr-x   3 root root  4096 fév 24  2016 home
    [...]


## Command flags through magic methods

You can also compose commands with `|` and add argument to commands
with `+`, `-` or `/` (windows style):

    >>> cmd = sh.git +"status" -"s" | sh.head -3
    >>> print(cmd())
	M README.md
	M conquer.py
	?? out.txt

Because of operator precedence, long options wont work, in this case
the `+` operator is a better fit:

```
>>> cmd = sh.ls --version  # Fail with "TypeError: bad operand type for unary -: 'str'"
>>> cmd = sh.ls + '--version' | sh.head -2
>>> print(cmd())
ls (GNU coreutils) 8.30
Copyright © 2018 Free Software Foundation, Inc.
```

## Redirections

Conquer also let you redirect stdin and stdout:

```python
sh.ls() > 'out.txt'       # Redirect output to file
cmd =  sh.wc < 'out.txt'  # Use file as stdin
print(cmd())              # Same result as running `ls | wc`
```


## SSH

You can also create an SSH object and use it in the same fashion:


``` python
from conquer import SSH

ssh = SSH('localhost')
print(ssh.echo('$SHELL')) # -> /bin/bash
```


Piping works across local and remote:


```python
from conquer import sh, SSH

ssh = SSH('localhost')
cmd = sh.env | ssh.grep + "SSH"
print(cmd())

cmd = ssh.env | sh.grep + "SSH"
print(cmd())
```

Which prints:

```
SSH_AUTH_SOCK=/tmp/ssh-pbTptmrP2U0x/agent.397331
SSH_AGENT_PID=397376

SSH_CONNECTION=::1 46554 ::1 22
SSH_CLIENT=::1 46554 22
```
