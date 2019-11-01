from conquer import sh, SSH
from conquer.script import ping

script = 'true && echo "ok"'

def test_base_script():
    res = sh(script)
    assert str(res) == 'ok\n'

def test_remote_script():
    remote = SSH('localhost')
    res = remote(script)
    assert str(res) == 'ok\n'

def test_builtin_script():
    res = ping()
    assert str(res) == 'pong\n'

    remote = SSH('localhost')
    res = ping(remote)
    assert str(res) == 'pong\n'

