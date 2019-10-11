from conquer import sh

def test_base():
    cmd = sh.echo + "ham\nspam" | sh.head - '1'
    assert str(cmd()).strip() == 'ham'


def test_redirect():
    # Put two lines in a file
    cmd = sh.echo('ham\nspam') > 'out.txt'
    # Read it back
    cmd = (sh.cat < 'out.txt') |  sh.wc -'l'
    assert str(cmd()).strip() == '2'

    # Read  back again
    cmd = ('out.txt' > sh.cat)  | sh.wc -'l' # XXX add support for
                                             # piping to sh.wc() ?
    assert str(cmd()).strip() == '2'
