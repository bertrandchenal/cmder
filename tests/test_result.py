from conquer import Result
from conquer.main import Process


def test_eq():
    proc = Process('echo', ('-n', 'foo',))
    res = Result(proc)
    assert res == 'foo'
    assert res == b'foo'


def test_iter():
    # Short runnig process
    proc = Process('echo', ('-n', 'foo',))
    res = Result(proc)
    assert list(res) == ['foo']

    # Long runnig process
    script = 'while true; do echo foo ; sleep 0.1;  done'
    proc = Process(script, shell=True)
    res = Result(proc)
    it = iter(res)
    for i in range(3):
        assert next(it) == 'foo\n'

    proc.kill()
