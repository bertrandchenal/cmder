from conquer import sh, SSH

script = 'true && echo "ok"'

def test_base_script():
    res = sh(script)
    assert str(res) == 'ok\n'

def test_remote_script():
    remote = SSH('localhost')
    res = remote(script)
    assert str(res) == 'ok\n'
