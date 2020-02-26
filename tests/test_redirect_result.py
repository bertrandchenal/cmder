from conquer import sh

def test_base():
    res = sh.echo('hello world')
    cmd = res > sh.wc-'c'
    assert str(cmd()).strip() == '12'
