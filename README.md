# Conquer

Conquer is a small python3 utility to help run commands. It supports
Linux, Windows and MacOS.

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


You can also compose commands with `|` and add argument to commands
with `+`, `-` or `/` (windows style):

    >>> cmd = sh.ls + "/" - "1" | sh.head - '3'
    >>> print(cmd())
    bin
    boot
    dev

You can instantiate Cmd object manually, by default they print stdout
and stderr to the respective streams of current process.

So if you save this in `test.py`:

```python
from conquer import Cmd
cmd = Cmd('ls', '-l', '/').pipe('head', '-3')
cmd.run()
```

You can execute it like this:

    $ python test.py
    total 104
    drwxr-xr-x   2 root root  4096 aoû 20  2018 bin
    drwxr-xr-x   4 root root  4096 aoû 25  2018 boot
