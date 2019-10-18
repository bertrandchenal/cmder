from conquer import sh
from concurrent import futures

def test_base():
    scripts = ['tests/chatty.py'] * 3
    with futures.ThreadPoolExecutor() as executor:
        for res in executor.map(sh.python, scripts):
            assert len(res.stdout.splitlines()) == 2000

def test_pipe():
    cmd = sh.python + 'tests/chatty.py' | sh.wc
    args = ['-m', '-w', '-L']
    expected = [7780, 2000, 3]
    with futures.ThreadPoolExecutor() as executor:
        for res, exp in zip(executor.map(cmd, args), expected):
            assert res.success
            assert exp == int(res.stdout)
