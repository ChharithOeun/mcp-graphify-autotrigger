"""
chharbot/tools/graphify_tool.py

Wrapper around the graphify CLI (safishamsi/graphify, pip name: graphifyy).
Provides:
- is_installed() : bool
- build(target_path, mode="default", force=False) : GraphifyResult
- query(target_path, question, auto_build=True) : GraphifyResult
- path_between(target_path, node_a, node_b) : GraphifyResult

Universal: works on ANY drive/folder. Per-target graphs cached at
~/.chharbot/graphs/<sha256(realpath)>/ so repeat queries are cheap.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


CACHE_ROOT = Path.home() / ".chharbot" / "graphs"
GRAPHIFY_BIN = "graphify"


@dataclass
class GraphifyResult:
    ok: bool
    text: str
    target_path: str
    duration_s: float = 0.0
    stderr: str = ""
    exit_code: int = 0
    cached: bool = False


def is_installed() -> bool:
    """Return True iff `graphify` is on PATH."""
    return shutil.which(GRAPHIFY_BIN) is not None


def binary_path() -> Optional[str]:
    return shutil.which(GRAPHIFY_BIN)


def _target_hash(path: str) -> str:
    norm = os.path.realpath(os.path.abspath(path))
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def _cache_dir_for(target: str) -> Path:
    d = CACHE_ROOT / _target_hash(target)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ensure_dir(target: str) -> Optional[GraphifyResult]:
    if not os.path.isdir(target):
        return GraphifyResult(
            ok=False,
            text=f"target not a directory: {target}",
            target_path=target,
        )
    return None


def _has_graph(target: str) -> bool:
    cache = _cache_dir_for(target)
    if (cache / "graph.json").exists():
        return True
    out_dir = Path(target) / "graphify-out"
    return (out_dir / "graph.json").exists()


def build(target_path: str, mode: str = "default", force: bool = False,
          timeout_s: int = 600) -> GraphifyResult:
    """
    Build (or rebuild) a graphify graph for target_path.
    
    Args:
        target_path: any folder on any drive
        mode: 'default' or 'deep' (deep = aggressive multi-modal extraction)
        force: rebuild even if cached
        timeout_s: max build time
    """
    if not is_installed():
        return GraphifyResult(
            ok=False,
            text="graphify not installed. Run: pip install --user graphifyy",
            target_path=target_path,
        )
    target = os.path.abspath(target_path)
    err = _ensure_dir(target)
    if err:
        return err
    
    if _has_graph(target) and not force:
        return GraphifyResult(
            ok=True,
            text=f"using cached graph for {target}",
            target_path=target,
            cached=True,
        )
    
    argv = [GRAPHIFY_BIN, target]
    if mode == "deep":
        argv.extend(["--mode", "deep"])
    
    t0 = time.time()
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout_s, cwd=target)
        elapsed = time.time() - t0
    except subprocess.TimeoutExpired:
        return GraphifyResult(
            ok=False,
            text=f"graphify build timed out after {timeout_s}s",
            target_path=target,
            duration_s=float(timeout_s),
        )
    except FileNotFoundError as e:
        return GraphifyResult(
            ok=False,
            text=f"graphify binary not found: {e}",
            target_path=target,
            duration_s=time.time() - t0,
        )
    
    # Mirror graphify-out/ into our per-target cache
    cache = _cache_dir_for(target)
    out_dir = Path(target) / "graphify-out"
    if out_dir.exists():
        for fname in ("graph.json", "GRAPH_REPORT.md", "manifest.json", "graph.html"):
            src = out_dir / fname
            if src.exists():
                try:
                    shutil.copy2(src, cache / fname)
                except OSError:
                    pass
    
    return GraphifyResult(
        ok=proc.returncode == 0,
        text=(proc.stdout or "")[-4000:],
        target_path=target,
        duration_s=elapsed,
        stderr=(proc.stderr or "")[-2000:],
        exit_code=proc.returncode,
    )


def query(target_path: str, question: str, auto_build: bool = True,
          timeout_s: int = 120) -> GraphifyResult:
    """
    Query a graphify graph in plain English.
    
    Args:
        target_path: any folder
        question: natural-language question
        auto_build: if no graph exists, build one first
    """
    if not is_installed():
        return GraphifyResult(
            ok=False,
            text="graphify not installed",
            target_path=target_path,
        )
    target = os.path.abspath(target_path)
    err = _ensure_dir(target)
    if err:
        return err
    
    if not _has_graph(target):
        if auto_build:
            br = build(target)
            if not br.ok:
                return br
        else:
            return GraphifyResult(
                ok=False,
                text="no graph built; call build() first or pass auto_build=True",
                target_path=target,
            )
    
    argv = [GRAPHIFY_BIN, "query", question]
    t0 = time.time()
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout_s, cwd=target)
        elapsed = time.time() - t0
    except subprocess.TimeoutExpired:
        return GraphifyResult(
            ok=False,
            text=f"query timed out after {timeout_s}s",
            target_path=target,
            duration_s=float(timeout_s),
        )
    
    return GraphifyResult(
        ok=proc.returncode == 0,
        text=(proc.stdout or "")[-4000:],
        target_path=target,
        duration_s=elapsed,
        stderr=(proc.stderr or "")[-2000:],
        exit_code=proc.returncode,
    )


def path_between(target_path: str, node_a: str, node_b: str,
                 timeout_s: int = 60) -> GraphifyResult:
    """Find shortest path between two nodes in a graph."""
    if not is_installed():
        return GraphifyResult(ok=False, text="graphify not installed", target_path=target_path)
    target = os.path.abspath(target_path)
    err = _ensure_dir(target)
    if err:
        return err
    
    argv = [GRAPHIFY_BIN, "path", node_a, node_b]
    t0 = time.time()
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout_s, cwd=target)
        elapsed = time.time() - t0
    except subprocess.TimeoutExpired:
        return GraphifyResult(
            ok=False,
            text="path query timed out",
            target_path=target,
            duration_s=float(timeout_s),
        )
    
    return GraphifyResult(
        ok=proc.returncode == 0,
        text=(proc.stdout or "")[-2000:],
        target_path=target,
        duration_s=elapsed,
        stderr=(proc.stderr or "")[-1000:],
        exit_code=proc.returncode,
    )


def list_cached_graphs() -> list:
    """Return list of (target_hash, last_built_ts) for all cached graphs."""
    if not CACHE_ROOT.exists():
        return []
    out = []
    for sub in CACHE_ROOT.iterdir():
        if sub.is_dir():
            gj = sub / "graph.json"
            if gj.exists():
                out.append((sub.name, gj.stat().st_mtime))
    return sorted(out, key=lambda x: -x[1])


def merge_graphs(target_paths: list, output_path: str,
                 timeout_s: int = 600) -> GraphifyResult:
    """
    Merge multiple graphs into one super-graph.
    Useful for cross-repo queries (e.g. lsb-repo + ashita addons + retail docs).
    """
    if not is_installed():
        return GraphifyResult(ok=False, text="graphify not installed", target_path=str(target_paths))
    
    argv = [GRAPHIFY_BIN, "merge-graphs", "--output", output_path] + list(target_paths)
    t0 = time.time()
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s)
        elapsed = time.time() - t0
    except subprocess.TimeoutExpired:
        return GraphifyResult(
            ok=False,
            text=f"merge timed out after {timeout_s}s",
            target_path=str(target_paths),
            duration_s=float(timeout_s),
        )
    
    return GraphifyResult(
        ok=proc.returncode == 0,
        text=(proc.stdout or "")[-2000:],
        target_path=output_path,
        duration_s=elapsed,
        stderr=(proc.stderr or "")[-1000:],
        exit_code=proc.returncode,
    )


# ----- self-test ---------------------------------------------------------
def _self_test() -> int:
    print("=== graphify_tool self-test ===")
    print(f"  CACHE_ROOT: {CACHE_ROOT}")
    installed = is_installed()
    print(f"  is_installed: {installed}")
    if installed:
        print(f"  binary_path: {binary_path()}")
    else:
        print("  install via: pip install --user graphifyy")
        print("  (after install, re-run this self-test)")
    
    cached = list_cached_graphs()
    print(f"  cached graphs: {len(cached)}")
    for h, ts in cached[:5]:
        print(f"    {h}  mtime={time.ctime(ts)}")
    
    # Smoke test the path-resolution helpers without invoking graphify
    test_target = os.path.dirname(os.path.abspath(__file__))
    h = _target_hash(test_target)
    cd = _cache_dir_for(test_target)
    print(f"  test_target hash: {h}")
    print(f"  cache_dir: {cd}")
    print(f"  has_graph(test_target): {_has_graph(test_target)}")
    print("=== self-test done ===")
    return 0


if __name__ == "__main__":
    sys.exit(_self_test())
