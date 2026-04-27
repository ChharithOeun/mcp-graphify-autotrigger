"""
autotrigger.cleanup - post-session / post-milestone cleanup.

Functions:
    cleanup_files(workspace, archive=True, dry_run=False) -> CleanupResult
    cleanup_screenshots(min_age_min=15, dry_run=False) -> CleanupResult
    close_stale_windows(target_processes=DEFAULT_STALE_PROCESSES) -> CleanupResult
    run_full_cleanup(workspace, ...) -> dict[str, CleanupResult]

Decorators:
    @on_milestone(workspace, **opts) - run cleanup after the wrapped fn returns

Auto-trigger keywords detected by run_if_milestone():
    "session end", "milestone", "chunk done", "wrapping up", "cleanup"

Safe by default:
- archive (don't delete) session files
- skip git-tracked files
- never close shells (cmd, powershell, pwsh) or Cowork (msedgewebview2)
- screenshots only if >15 minutes old
"""
from __future__ import annotations

import datetime
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import List, Optional, Sequence


SESSION_FILE_PATTERNS = [
    "AB_*.ps1", "AB_*.bat", "AB_*.log",
    "AAR_*.ps1", "AAR_*.bat", "AAR_*.log", "AAR_*.py",
    "AGENT_DIAG.*",
    "AI_BRIDGE_*",
    "ASHITA_*.ps1", "ASHITA_*.bat", "ASHITA_*.log",
    "BUILD_*.ps1", "BUILD_*.log",
    "CHHARBOT_MAP.*",
    "CLEANUP.ps1", "CLEANUP.log",
    "DB_CREDS.ps1", "DB_CREDS.bat",
    "DIAG_*.ps1", "DIAG_*.bat", "DIAG_*.log", "DIAG_*.new",
    "FIX_*.ps1", "FIX_*.bat", "FIX_*.log",
    "GRAPHIFY_*.ps1", "GRAPHIFY_*.bat", "GRAPHIFY_*.log",
    "INIT_*.ps1", "INIT_*.log",
    "LIBS_DUMP.*",
    "MCP_*.ps1", "MCP_*.log",
    "POLISH.*", "PROBE.*",
    "PORT_CHECK*.ps1", "PORT_CHECK*.bat", "PORT_CHECK*.log",
    "PUBLISH*.ps1", "PUBLISH*.log",
    "REPO_STATUS.*",
    "RS2.*",
    "SANDBOX_WRITE_TEST.*",
    "SMOKE_*.ps1", "SMOKE_*.bat", "SMOKE_*.log",
    "TOOLS_MCP_COMMIT.log",
    "V3_REF.*",
    "WRITE_README.*",
    "XL_*.ps1", "XL_*.bat", "XL_*.log",
    "XILOADER_*",
]

DEFAULT_SCREENSHOT_LOCATIONS = [
    "~/Desktop",
    "~/Pictures/Screenshots",
    "~/.cowork/screenshots",
]

# Process names allowed to be force-closed.
# Deliberately EXCLUDES: cmd.exe, powershell.exe, pwsh.exe (user shells),
# msedgewebview2.exe (Cowork itself), python.exe (running agents).
DEFAULT_STALE_PROCESSES = ["notepad", "notepad++"]

MILESTONE_KEYWORDS = [
    "session end", "session complete", "session done",
    "milestone", "milestone reached",
    "chunk done", "chunk complete", "chunk end",
    "wrapping up", "cleanup", "wrap up",
]


@dataclass
class CleanupResult:
    archived: List[str] = field(default_factory=list)
    deleted: List[str] = field(default_factory=list)
    closed_windows: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    archive_dir: Optional[str] = None
    dry_run: bool = False

    def summary(self) -> str:
        prefix = "[DRY RUN] " if self.dry_run else ""
        return (f"{prefix}archived={len(self.archived)} "
                f"deleted={len(self.deleted)} "
                f"closed_windows={len(self.closed_windows)} "
                f"errors={len(self.errors)}")


def _expand(p: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(p)))


def _git_tracked(workspace: Path) -> set:
    if not (workspace / ".git").exists():
        return set()
    try:
        proc = subprocess.run(
            ["git", "ls-files"], cwd=str(workspace),
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode == 0:
            return {(workspace / p).resolve() for p in proc.stdout.splitlines()}
    except (subprocess.SubprocessError, OSError):
        pass
    return set()


def cleanup_files(
    workspace: str,
    *,
    archive: bool = True,
    dry_run: bool = False,
    patterns: Optional[Sequence[str]] = None,
    skip_tracked: bool = True,
) -> CleanupResult:
    """Move session diagnostic files out of the workspace root."""
    res = CleanupResult(dry_run=dry_run)
    ws = _expand(workspace)
    if not ws.is_dir():
        res.errors.append(f"workspace not a directory: {ws}")
        return res

    pats = list(patterns or SESSION_FILE_PATTERNS)
    tracked = _git_tracked(ws) if skip_tracked else set()

    candidates: list = []
    for pat in pats:
        candidates.extend(ws.glob(pat))
    candidates = [c for c in candidates if c.is_file()
                  and (not skip_tracked or c.resolve() not in tracked)]

    if archive:
        date = datetime.date.today().isoformat()
        archive_dir = ws / "session-archive" / date
        if not dry_run:
            archive_dir.mkdir(parents=True, exist_ok=True)
        res.archive_dir = str(archive_dir)
        for f in candidates:
            try:
                if not dry_run:
                    shutil.move(str(f), str(archive_dir / f.name))
                res.archived.append(str(f))
            except OSError as e:
                res.errors.append(f"{f.name}: {e}")
    else:
        for f in candidates:
            try:
                if not dry_run:
                    f.unlink()
                res.deleted.append(str(f))
            except OSError as e:
                res.errors.append(f"{f.name}: {e}")
    return res


def cleanup_screenshots(
    locations: Sequence[str] = DEFAULT_SCREENSHOT_LOCATIONS,
    *,
    min_age_min: int = 15,
    dry_run: bool = False,
    delete: bool = True,
) -> CleanupResult:
    """Delete screenshot PNGs older than min_age_min minutes."""
    res = CleanupResult(dry_run=dry_run)
    cutoff = time.time() - (min_age_min * 60)
    patterns = ["Screenshot*.png", "screen*.png", "image*.png", "scratch_*.png", "Snip*.png"]
    for loc in locations:
        d = _expand(loc)
        if not d.is_dir():
            continue
        for pat in patterns:
            for f in d.glob(pat):
                if not f.is_file():
                    continue
                if f.stat().st_mtime > cutoff:
                    continue
                try:
                    if not dry_run and delete:
                        f.unlink()
                    res.deleted.append(str(f))
                except OSError as e:
                    res.errors.append(f"{f.name}: {e}")
    return res


def close_stale_windows(
    target_processes: Sequence[str] = DEFAULT_STALE_PROCESSES,
    *,
    dry_run: bool = False,
    protect_pids: Sequence[int] = (),
) -> CleanupResult:
    """Force-close stale UI windows. Windows-only. Never closes shells or Cowork."""
    res = CleanupResult(dry_run=dry_run)
    if sys.platform != "win32":
        res.errors.append("close_stale_windows is Windows-only")
        return res

    NEVER = {"cmd", "powershell", "pwsh", "msedgewebview2", "claude",
             "python", "pythonw", "code", "explorer", "winlogon"}
    safe_targets = [t for t in target_processes if t.lower() not in NEVER]
    if not safe_targets:
        return res

    names_re = "|".join(safe_targets)
    protect = ",".join(map(str, protect_pids)) or "0"
    ps_cmd = (
        f"Get-Process | Where-Object {{ "
        f"$_.ProcessName -match '^({names_re})$' "
        f"-and $_.Id -notin @({protect}) "
        f"}} | ForEach-Object {{ "
        f"Write-Output ($_.Id); "
        f"{'' if dry_run else 'Stop-Process -Id $_.Id -Force'} "
        f"}}"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=30,
        )
        for line in proc.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                res.closed_windows.append(f"pid={line}")
        if proc.stderr:
            res.errors.append(proc.stderr.strip()[:500])
    except (subprocess.SubprocessError, OSError) as e:
        res.errors.append(f"window enumeration failed: {e}")
    return res


def run_full_cleanup(
    workspace: str,
    *,
    archive_files: bool = True,
    close_windows: bool = True,
    cleanup_screenshots_min_age: int = 15,
    dry_run: bool = False,
) -> dict:
    """Run all cleanup steps; returns dict[step -> CleanupResult]."""
    out = {}
    out["files"] = cleanup_files(workspace, archive=archive_files, dry_run=dry_run)
    out["screenshots"] = cleanup_screenshots(
        min_age_min=cleanup_screenshots_min_age, dry_run=dry_run
    )
    if close_windows:
        out["windows"] = close_stale_windows(dry_run=dry_run)
    return out


def run_if_milestone(prompt: str, workspace: str, **kw) -> Optional[dict]:
    """Run cleanup IF the prompt mentions a milestone keyword. Else return None.
    
    Useful for hooking into agent loops:
        result = run_if_milestone(user_prompt, workspace=cwd)
    """
    if not prompt:
        return None
    p = prompt.lower()
    if any(kw_ in p for kw_ in MILESTONE_KEYWORDS):
        return run_full_cleanup(workspace, **kw)
    return None


def on_milestone(workspace: str, **kw):
    """Decorator: run cleanup after the wrapped function returns successfully."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            try:
                run_full_cleanup(workspace, **kw)
            except Exception:
                pass  # never let cleanup break the wrapped function
            return result
        return wrapper
    return deco


# ----- CLI -----------------------------------------------------------------
def _main():
    import argparse
    parser = argparse.ArgumentParser(description="Post-session cleanup")
    parser.add_argument("workspace", help="workspace dir to clean")
    parser.add_argument("--no-archive", action="store_false", dest="archive_files",
                        help="DELETE files instead of archiving")
    parser.add_argument("--no-windows", action="store_false", dest="close_windows",
                        help="skip closing stale windows")
    parser.add_argument("--screenshots-min-age", type=int, default=15)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    out = run_full_cleanup(
        args.workspace,
        archive_files=args.archive_files,
        close_windows=args.close_windows,
        cleanup_screenshots_min_age=args.screenshots_min_age,
        dry_run=args.dry_run,
    )
    print("=== cleanup summary ===")
    for step, r in out.items():
        print(f"  {step}: {r.summary()}")
    if out["files"].archive_dir:
        print(f"\narchive: {out['files'].archive_dir}")


if __name__ == "__main__":
    _main()
