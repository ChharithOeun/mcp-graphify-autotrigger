"""mcp_chharbot_tools - MCP server exposing chharbot's tool surface.

Where ffxi_chharbot exposes the *agent* loop (chharbot_ask), and ffxi_client/
ffxi_admin expose individual bridge endpoints, this MCP exposes chharbot's
tool primitives directly:

    - delegate_shell(argv, cwd, timeout, env, stdin)
        Run any shell command through chharbot's unrestricted Python.
        No allowlist - full user-level permissions. Audit-logged.
    - graphify_query(target_path, question)
        Query a graphify knowledge graph for any folder. Auto-builds.
    - graphify_build(target_path, mode, force)
        Build/rebuild a graphify graph for any folder.
    - graphify_path(target_path, node_a, node_b)
        Find shortest path between two nodes in a graph.
    - graphify_preflight(prompt, targets)
        Run the auto-trigger pipeline: classify a prompt and, if structural,
        query each target's graph and return an injectable context block.
    - tools_status()
        Health check: graphify installed?, audit log size, etc.

Install deps:
    pip install fastmcp
    pip install -e <repo>/chharbot

Register in Claude's mcp.json:
    {
        "mcpServers": {
            "chharbot_tools": {
                "command": "python",
                "args": ["F:/ffxi/lsb-repo/mcp/chharbot_tools/server.py"]
            }
        }
    }
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

# Make the chharbot package importable when this server is launched directly
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CHHARBOT_PKG = os.path.join(_REPO_ROOT, "chharbot")
if _CHHARBOT_PKG not in sys.path:
    sys.path.insert(0, _CHHARBOT_PKG)

try:
    from fastmcp import FastMCP
except ImportError:
    raise SystemExit("fastmcp not installed. Run: pip install fastmcp")

from autotrigger import delegate as _delegate
from autotrigger import graphify as _gt
from autotrigger import classifier as _gc
from autotrigger import preflight as _gp


mcp = FastMCP("chharbot_tools")


@mcp.tool
def delegate_shell(
    argv: List[str],
    cwd: Optional[str] = None,
    timeout: int = 300,
    env: Optional[Dict[str, str]] = None,
    stdin: Optional[str] = None,
    inherit_env: bool = True,
) -> Dict[str, Any]:
    """Run a shell command on chharbot's unrestricted Python process.

    NO ALLOWLIST - chharbot has full user-level filesystem and subprocess
    access. Use this to bypass tier-restricted apps when driving Windows
    from an external agent (e.g. Claude in Cowork).

    Every call is appended to ~/.chharbot/delegate-audit.log as JSONL.

    Args:
        argv: command and arguments as list of strings (no shell parsing).
              Example: ["git", "status", "--short"]
        cwd: working directory (default: chharbot's cwd)
        timeout: max seconds to wait (default 300)
        env: environment vars to merge into subprocess env
        stdin: text to pipe to subprocess stdin
        inherit_env: if True, inherit parent env then merge `env`

    Returns:
        Dict with keys: ok, exit_code, stdout, stderr, duration_s, argv, cwd,
        truncated_stdout, truncated_stderr.
    """
    return _delegate.delegate_shell_dict(
        argv=argv, cwd=cwd, timeout=timeout, env=env,
        stdin=stdin, inherit_env=inherit_env,
    )


@mcp.tool
def graphify_query(
    target_path: str,
    question: str,
    auto_build: bool = True,
) -> Dict[str, Any]:
    """Query a graphify knowledge graph in plain English.

    Args:
        target_path: any folder on any drive (e.g. "F:/ffxi/lsb-repo")
        question: natural-language question
        auto_build: if no graph exists, build one first

    Returns:
        Dict: ok, text, target_path, duration_s, stderr, exit_code, cached
    """
    r = _gt.query(target_path, question, auto_build=auto_build)
    return {
        "ok": r.ok,
        "text": r.text,
        "target_path": r.target_path,
        "duration_s": r.duration_s,
        "stderr": r.stderr,
        "exit_code": r.exit_code,
        "cached": r.cached,
    }


@mcp.tool
def graphify_build(
    target_path: str,
    mode: str = "default",
    force: bool = False,
) -> Dict[str, Any]:
    """Build (or rebuild) a graphify knowledge graph.

    Args:
        target_path: any folder on any drive
        mode: 'default' or 'deep' (deep = aggressive multi-modal extraction)
        force: rebuild even if a cached graph exists

    Returns:
        Dict: ok, text, target_path, duration_s, stderr, exit_code, cached
    """
    r = _gt.build(target_path, mode=mode, force=force)
    return {
        "ok": r.ok,
        "text": r.text,
        "target_path": r.target_path,
        "duration_s": r.duration_s,
        "stderr": r.stderr,
        "exit_code": r.exit_code,
        "cached": r.cached,
    }


@mcp.tool
def graphify_path(
    target_path: str,
    node_a: str,
    node_b: str,
) -> Dict[str, Any]:
    """Find the shortest path between two nodes in a graphify graph."""
    r = _gt.path_between(target_path, node_a, node_b)
    return {
        "ok": r.ok,
        "text": r.text,
        "target_path": r.target_path,
        "duration_s": r.duration_s,
    }


@mcp.tool
def graphify_preflight(
    prompt: str,
    targets: Optional[List[str]] = None,
    auto_build: bool = True,
    max_targets: int = 3,
) -> Dict[str, Any]:
    """Run the auto-trigger pipeline.

    Classifies the prompt (structural / targeted / conversational), and if
    structural, queries each target's graph and returns an injectable
    Markdown context block.

    Args:
        prompt: user/agent prompt
        targets: list of folders to query (any drives). If empty, uses cwd.
        auto_build: if a target lacks a graph, build it first
        max_targets: max targets to query (cost cap)

    Returns:
        Dict: decision, confidence, reason, targets_queried, graph_results,
        context_block, duration_s, classifier_query, estimated_tokens_used.
    """
    pf = _gp.preflight(
        prompt=prompt,
        targets=targets,
        auto_build=auto_build,
        max_targets=max_targets,
    )
    return {
        "decision": pf.decision,
        "confidence": pf.confidence,
        "reason": pf.reason,
        "targets_queried": pf.targets_queried,
        "graph_results": pf.graph_results,
        "context_block": pf.context_block,
        "duration_s": pf.duration_s,
        "classifier_query": pf.classifier_query,
        "estimated_tokens_used": pf.estimated_tokens_used,
    }


@mcp.tool
def graphify_classify(prompt: str, has_graph: bool = True) -> Dict[str, Any]:
    """Classify a prompt without running graphify.

    Returns the classifier decision so callers can decide whether to invoke
    the full preflight pipeline or skip.
    """
    r = _gc.classify(prompt, has_graph=has_graph)
    return {
        "decision": r.decision.value,
        "confidence": r.confidence,
        "reason": r.reason,
        "extracted_query": r.extracted_query,
        "matched_pattern": r.matched_pattern,
        "expected_token_cost": r.expected_token_cost,
    }


@mcp.tool
def tools_status() -> Dict[str, Any]:
    """Health check for the chharbot tools surface."""
    audit = _delegate.AUDIT_LOG
    audit_size = audit.stat().st_size if audit.exists() else 0
    audit_lines = sum(1 for _ in open(audit, "r", encoding="utf-8")) if audit.exists() else 0
    cached = _gt.list_cached_graphs()
    return {
        "graphify_installed": _gt.is_installed(),
        "graphify_binary": _gt.binary_path(),
        "audit_log_path": str(audit),
        "audit_log_bytes": audit_size,
        "audit_log_lines": audit_lines,
        "cached_graphs_count": len(cached),
        "cached_graphs": [{"hash": h, "mtime": ts} for h, ts in cached[:10]],
        "tool_versions": {
            "delegate": "0.1.0",
            "graphify_classifier": "0.1.0",
            "graphify_tool": "0.1.0",
            "graphify_preflight": "0.1.0",
        },
    }


# ===== auto-cleanup tools (added v0.2.0) ======================================
from autotrigger import cleanup as _cleanup


@mcp.tool
def cleanup_session(workspace: str, archive: bool = True, dry_run: bool = False,
                     close_windows: bool = True, screenshots_min_age: int = 15) -> Dict[str, Any]:
    """Post-session/milestone cleanup: archive diagnostic files, delete old screenshots,
    close stale windows. Defaults are safe (archive not delete, skip git-tracked,
    never closes shells or Cowork)."""
    out = _cleanup.run_full_cleanup(
        workspace,
        archive_files=archive,
        close_windows=close_windows,
        cleanup_screenshots_min_age=screenshots_min_age,
        dry_run=dry_run,
    )
    return {step: {
        "archived": r.archived,
        "deleted": r.deleted,
        "closed_windows": r.closed_windows,
        "errors": r.errors,
        "archive_dir": r.archive_dir,
        "summary": r.summary(),
    } for step, r in out.items()}


@mcp.tool
def archive_files(workspace: str, dry_run: bool = False) -> Dict[str, Any]:
    """Move session diagnostic files (PS1/bat/log etc) to session-archive/<date>/.
    Skips git-tracked files."""
    r = _cleanup.cleanup_files(workspace, archive=True, dry_run=dry_run)
    return {
        "archived": r.archived,
        "errors": r.errors,
        "archive_dir": r.archive_dir,
        "summary": r.summary(),
    }


@mcp.tool
def close_stale_windows(target_processes: Optional[List[str]] = None,
                         dry_run: bool = False) -> Dict[str, Any]:
    """Close stale UI windows (default: notepad, notepad++).
    Never closes shells (cmd/powershell/pwsh) or Cowork (msedgewebview2)."""
    r = _cleanup.close_stale_windows(
        target_processes=target_processes or _cleanup.DEFAULT_STALE_PROCESSES,
        dry_run=dry_run,
    )
    return {
        "closed_windows": r.closed_windows,
        "errors": r.errors,
        "summary": r.summary(),
    }
# ===== end auto-cleanup tools =================================================
if __name__ == "__main__":
    mcp.run()


