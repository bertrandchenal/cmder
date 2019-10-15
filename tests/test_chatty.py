from conquer import sh

def test_base():
    cmd = sh.python +'tests/chatty.py' | sh.wc
    print(cmd())
    assert True
