"""Security stress tests for delegate_shell."""
import pytest
from autotrigger.delegate import delegate_shell, STDIN_CAP_BYTES


def test_argv_list_blocks_shell_injection():
    """argv list form prevents shell metachar interpretation."""
    r = delegate_shell(["python", "-c", "print('safe')"])
    assert r.ok and "safe" in r.stdout
    # An attacker passing shell metachars in an argv element is treated as
    # a literal arg, not parsed by a shell.
    r = delegate_shell(["python", "-c", "print('A; rm -rf /')"])
    assert r.ok
    assert "rm -rf" in r.stdout  # treated as literal output


def test_bad_cwd_raises_oserror():
    """Non-existent cwd -> exit_code=-3, no crash."""
    r = delegate_shell(["python", "-c", "print('x')"], cwd="C:/nonexistent/path/xyz")
    assert not r.ok
    assert r.exit_code in (-2, -3)


def test_stdin_size_cap():
    """stdin larger than STDIN_CAP_BYTES is rejected."""
    huge = "A" * (STDIN_CAP_BYTES + 1)
    with pytest.raises(ValueError, match="stdin exceeds"):
        delegate_shell(["python", "-c", "import sys; sys.stdin.read()"], stdin=huge)


def test_timeout_kills_runaway():
    """Long-running commands are killed at timeout."""
    r = delegate_shell(["python", "-c", "import time; time.sleep(60)"], timeout=1)
    assert not r.ok
    assert r.exit_code == -1
