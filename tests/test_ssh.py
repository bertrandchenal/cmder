from conquer import SSH, sh

def test_communicate():
    localhost = SSH('localhost')
    res = localhost.env()
    keys = [l.split('=', 1)[0] for l in str(res).splitlines()]
    assert 'SSH_CLIENT' in keys

def test_remote_to_local():
    localhost = SSH('localhost')
    cmd = localhost.env | sh.grep + 'SSH_CLIENT'
    assert len(str(cmd()))

def test_local_to_remote():
    localhost = SSH('localhost')
    cmd = sh.env | localhost.wc -'l'
    res = str(cmd())
    local_cmd = sh.env | sh.wc -'l'
    expected = str(local_cmd())
    assert res and res == expected
