from conquer import SSH, sh

def test_remote_to_local():
    localhost = SSH('localhost')
    cmd = localhost.env | sh.grep + 'SSH_CLIENT'
    assert len(str(cmd()))

def test_local_to_remote():
    localhost = SSH('localhost')
    cmd = sh.env | localhost.grep + 'SSH_CLIENT'
    assert len(str(cmd()))
