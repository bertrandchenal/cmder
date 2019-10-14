from conquer import Result

def test_eq():
    assert Result(0, b'foo', None) == 'foo'
    assert Result(0, b'foo', None) == b'foo'
