import pytest
from autotrigger.delegate import delegate_shell

def test_basic():
    r = delegate_shell(["python", "-c", "print('hi')"])
    assert r.ok and "hi" in r.stdout

def test_exit_code():
    r = delegate_shell(["python", "-c", "import sys; sys.exit(7)"])
    assert r.exit_code == 7

def test_bad_argv():
    with pytest.raises(TypeError):
        delegate_shell("not a list")
