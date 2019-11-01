from conquer import sh

script = 'true && echo "ok"'

def test_base_script():
    res = sh(script)
    assert str(res) == 'ok\n'
