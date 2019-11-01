from .main import sh

def ping(host=None):
    cmd = 'echo "pong"'
    if host:
        return host(cmd)
    return sh(cmd)
