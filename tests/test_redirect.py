from conquer import sh

def test_base():
    sh.ls() > 'out.txt'       # Redirect output to file
    cmd =  sh.wc < 'out.txt'  # Use file as stdin
    res = cmd()
    assert len(str(res).splitlines()) == 1
