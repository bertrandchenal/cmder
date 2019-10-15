from conquer import sh, Func

def test_func_tail():
    cmd = (sh.echo + '-e' + 'ham\nspam') | str.upper
    assert tuple(cmd()) == ('HAM\n', 'SPAM\n')


def fn():
    for i in range(10):
        print('fn', i)
        yield str(i)

def test_func_head():
    cmd = Func(fn) | sh.cat
    res = cmd()
    print(res.stdout)
    assert res == '0123456789'

test_func_head()
