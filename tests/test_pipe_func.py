from conquer import sh, Func

def test_func_tail():
    cmd = (sh.echo + '-e' + 'ham\nspam') | str.upper
    for res, exp in zip(cmd(), ('HAM', 'SPAM')):
        assert res.strip() == exp


def fn():
    for i in range(10):
        yield str(i)

def test_func_head():
    cmd = Func(fn) | sh.cat
    res = cmd()
    assert res == '0123456789'

test_func_head()
