from conquer import sh

def test_base():
    expected = sh.echo('-e', 'ham\nspam')
    cmd = sh.echo -'e' + 'ham\nspam'
    res = cmd()
    assert res.success()
    assert str(res) == str(expected)
