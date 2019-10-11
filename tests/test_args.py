from conquer import sh

def test_base():
    expected = sh.echo('-e', 'ham\nspam')
    cmd = sh.echo -'e' + 'ham\nspam'
    assert str(cmd()) == str(expected)
