from conquer import sh, Func

def test_func_tail():
    cmd = (sh.echo + '-e' + 'ham\nspam') | str.upper
    assert tuple(cmd()) == ('HAM\n', 'SPAM\n')


def test_func_head():
    fn = lambda: map(str, range(10))
    cmd = Func(fn) | sh.cat
    print(cmd())
