from time import sleep
from conquer import sh, Func


def test_chatty():
    cmd = sh.python +'tests/chatty.py' | sh.wc
    res = cmd().stdout
    assert res.strip() == b'2000    2000    7780'

def fn():
    for i in range(3):
        for i in range(10):
            yield str(i)
        sleep(1)

def test_slow_func():
    cmd = Func(fn) | sh.wc
    res = cmd().stdout
    assert res.strip() == b'0       1      30'
