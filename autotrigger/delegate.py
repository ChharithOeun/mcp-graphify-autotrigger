"""
chharbot/tools/delegate.py

Delegation tool: lets external agents (Claude in Cowork, MCP clients, etc.)
drive shell commands through chharbot's unrestricted Python process.

NO ALLOWLIST. Chharbot has full user-privilege filesystem and subprocess access.
The tradeoff is full autonomy for the calling agent.

Every call is appended to ~/.chharbot/delegate-audit.log as JSON-lines so the
operator can review what was delegated.

Exposed via chharbot's MCP server as `delegate_shell`. From there, Claude in
Cowork can call any shell command — `pip install`, `git`, `graphify`, native
tools — without the tier=click typing restriction.
"""
from __future__ import annotations

import datetime
import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


AUDIT_LOG = Path.home() / ".chharbot" / "delegate-audit.log"
AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)


@dataclass
class DelegateResult:
    ok: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    argv: List[str]
    cwd: str
    truncated_stdout: bool = False
    truncated_stderr: bool = False


# Safety caps (not security — just memory protection)
STDOUT_CAP_BYTES = 256 * 1024   # 256KB
STDERR_CAP_BYTES = 64 * 1024    # 64KB


def _audit(entry: dict) -> None:
    """Append a single JSON-line audit entry."""
    entry["ts"] = datetime.datetime.utcnow().isoformat() + "Z"
    try:
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass  # never let audit failure break the delegation


def _cap(text: str, max_bytes: int) -> tuple[str, bool]:
    if not text:
        return "", False
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text, False
    return encoded[-max_bytes:].decode("utf-8", errors="replace"), True


def delegate_shell(
    argv: List[str],
    cwd: Optional[str] = None,
    timeout: int = 300,
    env: Optional[Dict[str, str]] = None,
    stdin: Optional[str] = None,
    inherit_env: bool = True,
) -> DelegateResult:
    """
    Run a shell command on chharbot's behalf.
    
    Args:
        argv: command and args as a list of strings (no shell parsing).
              Example: ["git", "status", "--short"]
        cwd: working directory. Defaults to chharbot's current cwd.
        timeout: max seconds to wait. Default 300 (5 minutes).
        env: env vars to merge into subprocess env.
        stdin: text to pipe to subprocess stdin.
        inherit_env: if True (default), inherit parent env then merge `env`.
                     If False, use only the explicit `env` dict.
    
    Returns:
        DelegateResult with stdout / stderr / exit_code / timing.
    
    Raises:
        TypeError if argv is not list[str]
        ValueError if argv is empty
    """
    if not isinstance(argv, list) or not all(isinstance(x, str) for x in argv):
        raise TypeError("argv must be List[str]")
    if not argv:
        raise ValueError("argv must not be empty")
    
    cwd = cwd or os.getcwd()
    if inherit_env:
        full_env = os.environ.copy()
        if env:
            full_env.update(env)
    else:
        full_env = dict(env or {})
    
    audit_id = f"{int(time.time()*1000):x}"
    _audit({
        "event": "delegate_shell.start",
        "id": audit_id,
        "argv": argv,
        "cwd": cwd,
        "timeout": timeout,
        "stdin_chars": len(stdin) if stdin else 0,
        "env_keys": sorted(env.keys()) if env else [],
    })
    
    t0 = time.time()
    truncated_out = False
    truncated_err = False
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=full_env,
            input=stdin,
        )
        elapsed = time.time() - t0
        stdout, truncated_out = _cap(proc.stdout or "", STDOUT_CAP_BYTES)
        stderr, truncated_err = _cap(proc.stderr or "", STDERR_CAP_BYTES)
        result = DelegateResult(
            ok=proc.returncode == 0,
            exit_code=proc.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_s=elapsed,
            argv=argv,
            cwd=cwd,
            truncated_stdout=truncated_out,
            truncated_stderr=truncated_err,
        )
    except subprocess.TimeoutExpired as e:
        elapsed = time.time() - t0
        partial_out = ""
        partial_err = ""
        if e.stdout:
            partial_out = e.stdout if isinstance(e.stdout, str) else e.stdout.decode("utf-8", errors="replace")
        if e.stderr:
            partial_err = e.stderr if isinstance(e.stderr, str) else e.stderr.decode("utf-8", errors="replace")
        partial_out, truncated_out = _cap(partial_out, STDOUT_CAP_BYTES)
        partial_err, truncated_err = _cap(partial_err, STDERR_CAP_BYTES)
        result = DelegateResult(
            ok=False,
            exit_code=-1,
            stdout=partial_out,
            stderr=(partial_err + f"\n[chharbot.delegate] timeout after {timeout}s"),
            duration_s=elapsed,
            argv=argv,
            cwd=cwd,
            truncated_stdout=truncated_out,
            truncated_stderr=truncated_err,
        )
    except FileNotFoundError as e:
        elapsed = time.time() - t0
        result = DelegateResult(
            ok=False,
            exit_code=-2,
            stdout="",
            stderr=f"[chharbot.delegate] FileNotFoundError: {e}",
            duration_s=elapsed,
            argv=argv,
            cwd=cwd,
        )
    except OSError as e:
        elapsed = time.time() - t0
        result = DelegateResult(
            ok=False,
            exit_code=-3,
            stdout="",
            stderr=f"[chharbot.delegate] OSError: {e}",
            duration_s=elapsed,
            argv=argv,
            cwd=cwd,
        )
    
    _audit({
        "event": "delegate_shell.done",
        "id": audit_id,
        "argv": argv,
        "cwd": cwd,
        "ok": result.ok,
        "exit_code": result.exit_code,
        "duration_s": round(result.duration_s, 3),
        "stdout_chars": len(result.stdout),
        "stderr_chars": len(result.stderr),
        "truncated_stdout": result.truncated_stdout,
        "truncated_stderr": result.truncated_stderr,
    })
    
    return result


def delegate_shell_dict(argv, cwd=None, timeout=300, env=None, stdin=None,
                        inherit_env=True) -> dict:
    """JSON-friendly wrapper for MCP tool exposure."""
    r = delegate_shell(argv=list(argv), cwd=cwd, timeout=timeout,
                        env=env, stdin=stdin, inherit_env=inherit_env)
    return asdict(r)


def tail_audit(n: int = 20) -> List[dict]:
    """Return the last N audit entries (parsed JSON)."""
    if not AUDIT_LOG.exists():
        return []
    lines = AUDIT_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    out = []
    for ln in lines[-n:]:
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            pass
    return out


# ----- self-test ---------------------------------------------------------
def _self_test() -> int:
    print("=== delegate self-test ===")
    print(f"  AUDIT_LOG: {AUDIT_LOG}")
    
    # Test 1: simple python call
    print("\n  test 1: python -c print('hello')")
    r = delegate_shell(["python", "-c", "print('hello from delegate')"])
    print(f"    ok={r.ok} exit={r.exit_code} duration={r.duration_s:.3f}s")
    print(f"    stdout: {r.stdout.strip()}")
    if not r.ok:
        print(f"    stderr: {r.stderr.strip()}")
        return 1
    
    # Test 2: command that fails
    print("\n  test 2: python -c 'import sys; sys.exit(7)'")
    r = delegate_shell(["python", "-c", "import sys; sys.exit(7)"])
    print(f"    ok={r.ok} exit={r.exit_code} (expected 7)")
    if r.exit_code != 7:
        return 1
    
    # Test 3: nonexistent binary
    print("\n  test 3: nonexistent_binary_xyz")
    r = delegate_shell(["nonexistent_binary_xyz"])
    print(f"    ok={r.ok} exit={r.exit_code}")
    if r.ok or r.exit_code != -2:
        print(f"    expected exit=-2 (FileNotFoundError); got {r.exit_code}")
        return 1
    
    # Test 4: timeout
    print("\n  test 4: short sleep + timeout")
    r = delegate_shell(["python", "-c", "import time; time.sleep(5)"], timeout=1)
    print(f"    ok={r.ok} exit={r.exit_code} (expected -1 timeout)")
    if r.exit_code != -1:
        return 1
    
    # Test 5: stdin pipe
    print("\n  test 5: stdin pipe")
    r = delegate_shell(["python", "-c", "import sys; print(sys.stdin.read().upper())"],
                        stdin="hello world")
    print(f"    ok={r.ok} stdout: {r.stdout.strip()}")
    if "HELLO WORLD" not in r.stdout:
        return 1
    
    # Test 6: cwd
    print("\n  test 6: cwd argument")
    r = delegate_shell(["python", "-c", "import os; print(os.getcwd())"],
                        cwd=os.path.dirname(os.path.abspath(__file__)))
    print(f"    cwd: {r.stdout.strip()}")
    
    # Test 7: TypeError on bad argv
    print("\n  test 7: TypeError on str argv")
    try:
        delegate_shell("python -c 'print(1)'")  # type: ignore[arg-type]
        print("    FAIL: should have raised TypeError")
        return 1
    except TypeError:
        print("    OK: TypeError raised")
    
    # Test 8: audit log
    print("\n  test 8: audit log present")
    audit = tail_audit(20)
    print(f"    last {len(audit)} entries; example: {audit[-1]['event'] if audit else 'none'}")
    if not audit:
        return 1
    
    print("\n=== delegate self-test PASSED ===")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_self_test())
