"""Agent-tool parity for chharbot's MCP surface.

Exposes the same primitives Cowork-Claude / Claude Code use natively
(Read, Write, Edit, Glob, Grep, Bash) so that when those agents delegate to
chharbot, every call has a 1:1 mapping. Plus skill_dispatch / list_skills
that surface Claude Code skills (under ~/.claude/skills) to any caller.

All tool callables are returned by `register(mcp)` so server.py keeps its
imports tidy. Each tool:

  - has size caps on file content + command output to keep MCP traffic small
  - records every action to ~/.chharbot/agent-audit.log (JSONL)
  - returns a structured dict (never raises across the MCP boundary)

These tools are intentionally ASYMMETRIC from delegate_shell:

  - delegate_shell takes argv (list) and is the "raw" escape hatch.
  - bash() here takes a string command and is what the agent reaches for
    when it would otherwise type into a terminal.

Both are full-autonomy. The user has accepted that risk explicitly.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Caps + audit
# ---------------------------------------------------------------------------

MAX_READ_BYTES = 1_048_576       # 1 MiB per Read
MAX_READ_LINES_DEFAULT = 2000
MAX_WRITE_BYTES = 5_242_880      # 5 MiB per Write
MAX_GREP_RESULTS = 1000
MAX_GLOB_RESULTS = 1000
MAX_BASH_OUTPUT_BYTES = 262_144  # 256 KiB stdout/stderr each
DEFAULT_BASH_TIMEOUT = 120
MAX_BASH_TIMEOUT = 600

_AUDIT_DIR = Path.home() / ".chharbot"
_AUDIT_LOG = _AUDIT_DIR / "agent-audit.log"


def _audit(action: str, **fields: Any) -> None:
    """Append a JSONL line to ~/.chharbot/agent-audit.log. Never raises."""
    try:
        _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        rec = {"ts": datetime.now(timezone.utc).isoformat(), "action": action}
        rec.update(fields)
        with _AUDIT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    except Exception:
        pass  # auditing is best-effort, never break the tool


def _truncate(s: str, cap: int) -> tuple[str, bool]:
    """Return (possibly truncated, was_truncated)."""
    if len(s) <= cap:
        return s, False
    return s[:cap] + f"\n... [truncated {len(s) - cap} bytes]", True


def _err(msg: str, **extra: Any) -> Dict[str, Any]:
    return {"ok": False, "error": msg, **extra}


# ---------------------------------------------------------------------------
# Skill dispatch
# ---------------------------------------------------------------------------

def _skills_root() -> Path:
    """Default ~/.claude/skills/. Override via CHHARBOT_SKILLS_DIR."""
    override = os.environ.get("CHHARBOT_SKILLS_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude" / "skills"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(mcp) -> None:
    """Register all agent-tool primitives onto the FastMCP instance."""

    # ---- read_file -------------------------------------------------------
    @mcp.tool
    def read_file(
        file_path: str,
        offset: int = 0,
        limit: int = MAX_READ_LINES_DEFAULT,
    ) -> Dict[str, Any]:
        """Read a file and return numbered lines (mirrors Read).

        Args:
            file_path: absolute path to file
            offset: 0-indexed line to start at
            limit: max lines to return (capped at 10_000)

        Returns:
            ok, file_path, lines (list of {n, text}), truncated, total_lines
        """
        try:
            p = Path(file_path).expanduser()
            if not p.is_absolute():
                return _err("file_path must be absolute", file_path=file_path)
            if not p.exists():
                return _err("file not found", file_path=str(p))
            if not p.is_file():
                return _err("not a regular file", file_path=str(p))
            size = p.stat().st_size
            if size > MAX_READ_BYTES:
                return _err(
                    f"file exceeds {MAX_READ_BYTES} byte cap; use offset/limit",
                    file_path=str(p), size=size,
                )

            limit = max(1, min(int(limit), 10_000))
            offset = max(0, int(offset))

            with p.open("r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()

            total = len(all_lines)
            slc = all_lines[offset : offset + limit]
            lines = [{"n": offset + i + 1, "text": ln.rstrip("\n")}
                     for i, ln in enumerate(slc)]
            _audit("read_file", file_path=str(p), offset=offset, limit=limit, returned=len(lines))
            return {
                "ok": True,
                "file_path": str(p),
                "lines": lines,
                "total_lines": total,
                "truncated": (offset + limit) < total,
            }
        except Exception as e:
            return _err(f"read failed: {e}", file_path=file_path)

    # ---- write_file ------------------------------------------------------
    @mcp.tool
    def write_file(file_path: str, content: str) -> Dict[str, Any]:
        """Write text to a file, creating parents as needed (mirrors Write).

        Overwrites if file exists. Use edit_file for targeted in-place edits.
        Caps content size at 5 MiB to keep MCP traffic sane.
        """
        try:
            if len(content.encode("utf-8")) > MAX_WRITE_BYTES:
                return _err(f"content exceeds {MAX_WRITE_BYTES} byte cap")
            p = Path(file_path).expanduser()
            if not p.is_absolute():
                return _err("file_path must be absolute", file_path=file_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            existed = p.exists()
            p.write_text(content, encoding="utf-8")
            _audit("write_file", file_path=str(p), bytes=len(content), overwrite=existed)
            return {"ok": True, "file_path": str(p), "bytes_written": len(content),
                    "existed": existed}
        except Exception as e:
            return _err(f"write failed: {e}", file_path=file_path)

    # ---- edit_file -------------------------------------------------------
    @mcp.tool
    def edit_file(
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> Dict[str, Any]:
        """Exact-string replacement in a file (mirrors Edit).

        Fails if old_string is not unique unless replace_all=True. Returns the
        number of replacements made.
        """
        try:
            p = Path(file_path).expanduser()
            if not p.is_absolute():
                return _err("file_path must be absolute", file_path=file_path)
            if not p.exists():
                return _err("file not found", file_path=str(p))

            text = p.read_text(encoding="utf-8")
            count = text.count(old_string)
            if count == 0:
                return _err("old_string not found", file_path=str(p))
            if count > 1 and not replace_all:
                return _err(
                    f"old_string matches {count} occurrences; pass replace_all=True or expand context",
                    file_path=str(p), matches=count,
                )

            new_text = text.replace(old_string, new_string,
                                    -1 if replace_all else 1)
            p.write_text(new_text, encoding="utf-8")
            replaced = count if replace_all else 1
            _audit("edit_file", file_path=str(p), replaced=replaced)
            return {"ok": True, "file_path": str(p), "replacements": replaced}
        except Exception as e:
            return _err(f"edit failed: {e}", file_path=file_path)

    # ---- glob_files ------------------------------------------------------
    @mcp.tool
    def glob_files(
        pattern: str,
        path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Find files by glob pattern, sorted by mtime descending (mirrors Glob).

        Pattern supports ** for recursive match. Path defaults to cwd.
        Capped at MAX_GLOB_RESULTS hits.
        """
        try:
            root = Path(path).expanduser() if path else Path.cwd()
            if not root.exists():
                return _err("path not found", path=str(root))
            matches = list(root.rglob(pattern) if "**" in pattern else root.glob(pattern))
            matches = [m for m in matches if m.is_file()]
            matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            truncated = len(matches) > MAX_GLOB_RESULTS
            matches = matches[:MAX_GLOB_RESULTS]
            _audit("glob_files", pattern=pattern, path=str(root), hits=len(matches))
            return {
                "ok": True,
                "pattern": pattern,
                "path": str(root),
                "files": [str(m) for m in matches],
                "truncated": truncated,
            }
        except Exception as e:
            return _err(f"glob failed: {e}", pattern=pattern)

    # ---- grep_files ------------------------------------------------------
    @mcp.tool
    def grep_files(
        pattern: str,
        path: Optional[str] = None,
        glob: Optional[str] = None,
        output_mode: str = "files_with_matches",
        case_insensitive: bool = False,
        max_results: int = 250,
    ) -> Dict[str, Any]:
        """Regex search through files (mirrors Grep, prefers rg if available).

        output_mode: "files_with_matches" | "content" | "count"
        """
        try:
            search_root = Path(path).expanduser() if path else Path.cwd()
            if not search_root.exists():
                return _err("path not found", path=str(search_root))
            max_results = max(1, min(int(max_results), MAX_GREP_RESULTS))

            # Prefer rg for speed if installed
            rg = _which("rg")
            if rg:
                cmd = [rg, "--no-heading", "-n"]
                if case_insensitive:
                    cmd.append("-i")
                if output_mode == "files_with_matches":
                    cmd.append("-l")
                elif output_mode == "count":
                    cmd.append("-c")
                if glob:
                    cmd.extend(["--glob", glob])
                cmd.extend([pattern, str(search_root)])
                try:
                    proc = subprocess.run(cmd, capture_output=True, text=True,
                                          timeout=30, encoding="utf-8", errors="replace")
                    out = proc.stdout
                    lines = [ln for ln in out.splitlines() if ln.strip()][:max_results]
                    _audit("grep_files", pattern=pattern, mode=output_mode, hits=len(lines), engine="rg")
                    return {"ok": True, "pattern": pattern, "mode": output_mode,
                            "results": lines, "engine": "rg"}
                except subprocess.TimeoutExpired:
                    return _err("grep (rg) timed out", pattern=pattern)

            # Fallback: pure-Python walk
            flags = re.IGNORECASE if case_insensitive else 0
            try:
                rx = re.compile(pattern, flags)
            except re.error as e:
                return _err(f"bad regex: {e}", pattern=pattern)

            results: List[str] = []
            files_with: List[str] = []
            counts: Dict[str, int] = {}
            for f in search_root.rglob("*"):
                if not f.is_file():
                    continue
                if glob and not fnmatch.fnmatch(f.name, glob):
                    continue
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                hits = list(rx.finditer(text))
                if not hits:
                    continue
                if output_mode == "files_with_matches":
                    files_with.append(str(f))
                    if len(files_with) >= max_results:
                        break
                elif output_mode == "count":
                    counts[str(f)] = len(hits)
                else:  # content
                    for h in hits:
                        ln = text.count("\n", 0, h.start()) + 1
                        results.append(f"{f}:{ln}:{text.splitlines()[ln-1] if ln-1 < len(text.splitlines()) else ''}")
                        if len(results) >= max_results:
                            break
                    if len(results) >= max_results:
                        break
            payload = {
                "ok": True,
                "pattern": pattern,
                "mode": output_mode,
                "engine": "python",
            }
            if output_mode == "files_with_matches":
                payload["results"] = files_with
            elif output_mode == "count":
                payload["results"] = [f"{p}:{c}" for p, c in counts.items()][:max_results]
            else:
                payload["results"] = results
            _audit("grep_files", pattern=pattern, mode=output_mode,
                   hits=len(payload["results"]), engine="python")
            return payload
        except Exception as e:
            return _err(f"grep failed: {e}", pattern=pattern)

    # ---- bash ------------------------------------------------------------
    @mcp.tool
    def bash(
        command: str,
        cwd: Optional[str] = None,
        timeout: int = DEFAULT_BASH_TIMEOUT,
        env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Run a shell command via the system shell (mirrors Bash).

        On Windows, executes via cmd.exe /c. On POSIX, /bin/sh -c.
        Output capped at MAX_BASH_OUTPUT_BYTES per stream. Audit-logged.
        """
        try:
            timeout = max(1, min(int(timeout), MAX_BASH_TIMEOUT))
            full_env = os.environ.copy()
            if env:
                full_env.update({k: str(v) for k, v in env.items()})

            t0 = time.time()
            if sys.platform == "win32":
                proc = subprocess.run(
                    ["cmd", "/c", command],
                    capture_output=True, text=True, timeout=timeout,
                    cwd=cwd, env=full_env, encoding="utf-8", errors="replace",
                )
            else:
                proc = subprocess.run(
                    ["/bin/sh", "-c", command],
                    capture_output=True, text=True, timeout=timeout,
                    cwd=cwd, env=full_env, encoding="utf-8", errors="replace",
                )
            dur = time.time() - t0
            stdout, sout_trunc = _truncate(proc.stdout or "", MAX_BASH_OUTPUT_BYTES)
            stderr, serr_trunc = _truncate(proc.stderr or "", MAX_BASH_OUTPUT_BYTES)
            _audit("bash", command=command, cwd=cwd, exit=proc.returncode, dur=round(dur, 3))
            return {
                "ok": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "duration_s": round(dur, 3),
                "truncated_stdout": sout_trunc,
                "truncated_stderr": serr_trunc,
                "command": command,
                "cwd": cwd,
            }
        except subprocess.TimeoutExpired as e:
            _audit("bash", command=command, cwd=cwd, error="timeout", timeout=timeout)
            return _err(f"bash timed out after {timeout}s", command=command, timeout=timeout)
        except Exception as e:
            return _err(f"bash failed: {e}", command=command)

    # ---- skill_dispatch -------------------------------------------------
    @mcp.tool
    def skill_dispatch(name: str) -> Dict[str, Any]:
        """Load a Claude Code skill by name and return SKILL.md content.

        Looks under ~/.claude/skills/<name>/SKILL.md (override path with
        env CHHARBOT_SKILLS_DIR). Returns the markdown so the caller's LLM
        can follow the skill's instructions inline. This is how Cowork or
        any MCP client gets parity with Claude Code skills without
        re-publishing each one as a Cowork plugin.
        """
        try:
            if not re.match(r"^[a-z0-9][a-z0-9_-]{0,63}$", name):
                return _err("invalid skill name (kebab-case, max 64 chars)", name=name)
            root = _skills_root()
            skill_dir = root / name
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                return _err(f"skill not found at {skill_md}", name=name, root=str(root))
            content = skill_md.read_text(encoding="utf-8")
            # also list bundled resources so the caller knows what's available
            extras = []
            for sub in ("references", "scripts", "assets"):
                d = skill_dir / sub
                if d.is_dir():
                    extras.extend([str(p.relative_to(skill_dir)) for p in d.rglob("*") if p.is_file()])
            _audit("skill_dispatch", name=name, bytes=len(content), extras=len(extras))
            return {
                "ok": True,
                "name": name,
                "path": str(skill_md),
                "content": content,
                "bundled_files": extras,
            }
        except Exception as e:
            return _err(f"skill_dispatch failed: {e}", name=name)

    # ---- list_skills -----------------------------------------------------
    @mcp.tool
    def list_skills() -> Dict[str, Any]:
        """List all installed Claude Code skills under ~/.claude/skills/.

        Returns a list of {name, description, path} drawn from each
        SKILL.md's YAML frontmatter. Use this to discover what skill_dispatch
        can call.
        """
        try:
            root = _skills_root()
            if not root.is_dir():
                return {"ok": True, "root": str(root), "skills": []}
            results = []
            for d in sorted(root.iterdir()):
                if not d.is_dir():
                    continue
                skill_md = d / "SKILL.md"
                if not skill_md.exists():
                    continue
                head = skill_md.read_text(encoding="utf-8", errors="replace")[:4000]
                m = re.search(
                    r"^---\s*\n(.*?)\n---\s*\n",
                    head, re.DOTALL,
                )
                desc = ""
                if m:
                    fm = m.group(1)
                    dm = re.search(r"^description:\s*(.+?)(?:\n[a-z]|\Z)",
                                   fm, re.DOTALL | re.MULTILINE)
                    if dm:
                        desc = dm.group(1).strip().strip('"').strip("'")
                        # collapse multi-line descriptions
                        desc = re.sub(r"\s+", " ", desc)
                        desc = desc[:400]
                results.append({
                    "name": d.name,
                    "description": desc,
                    "path": str(skill_md),
                })
            _audit("list_skills", count=len(results), root=str(root))
            return {"ok": True, "root": str(root), "skills": results}
        except Exception as e:
            return _err(f"list_skills failed: {e}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _which(cmd: str) -> Optional[str]:
    """Look up an executable on PATH, returning the full path or None."""
    from shutil import which
    return which(cmd)
