"""
chharbot/tools/graphify_preflight.py

Always-on auto-trigger that runs on EVERY chharbot prompt (not just FFXI).
Decides whether the prompt benefits from a graphify graph query and, if so,
runs it and produces a context block to inject into the LLM prompt.

This is the universal pre-flight hook. It does NOT pick a target directory
on its own â€” chharbot's brain provides the working directory (and optionally
extra targets) when calling preflight().

Universal: works on any drive/folder, not just F:\\ffxi\\lsb-repo.

Usage from chharbot's brain:
    from chharbot.tools.graphify_preflight import preflight, PreflightResult
    
    pf = preflight(
        prompt=user_prompt,
        targets=[cwd, *extra_repo_paths],  # any drives, any folders
        ollama_client=local_ollama,        # optional, for ambiguous fallback
    )
    if pf.context_block:
        # inject pf.context_block into the LLM context
        ...
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import List, Optional

from . import classifier as gc
from . import graphify as gt


@dataclass
class PreflightResult:
    decision: str                       # the classifier Decision value
    confidence: float
    reason: str
    targets_queried: List[str] = field(default_factory=list)
    graph_results: List[dict] = field(default_factory=list)  # one per target
    context_block: str = ""             # ready-to-inject context, "" if skipped
    duration_s: float = 0.0
    classifier_query: Optional[str] = None
    estimated_tokens_used: int = 0


def _format_context_block(query: str, results: List[dict]) -> str:
    """Render graph query results as a Markdown context block."""
    if not results:
        return ""
    parts = [
        "<!-- chharbot graphify_preflight: auto-injected context -->",
        f"## Graph query results for: \"{query}\"",
        "",
    ]
    for r in results:
        target = r.get("target", "?")
        ok = r.get("ok", False)
        text = r.get("text", "").strip()
        cached = r.get("cached", False)
        marker = "(cached)" if cached else ""
        if not ok:
            parts.append(f"### {target} {marker}")
            parts.append(f"_(query failed: {text[:200]})_")
            parts.append("")
            continue
        parts.append(f"### {target} {marker}")
        parts.append("```")
        parts.append(text[:3000])
        parts.append("```")
        parts.append("")
    return "\n".join(parts)


def preflight(
    prompt: str,
    targets: Optional[List[str]] = None,
    ollama_client=None,
    auto_build: bool = True,
    max_targets: int = 3,
) -> PreflightResult:
    """
    Run the auto-trigger pipeline on a prompt.
    
    Args:
        prompt: user/agent prompt
        targets: optional list of folders to query (any drives). If None or
                 empty, the cwd is used as a single target.
        ollama_client: optional client for the LLM-classifier fallback
        auto_build: if a target lacks a graph and structural decision was made,
                    auto-build the graph
        max_targets: cap on how many targets to actually query (cost control)
    
    Returns:
        PreflightResult with decision, optional context_block to inject, and
        timing/cost info.
    """
    t0 = time.time()
    
    if not targets:
        targets = [os.getcwd()]
    targets = [os.path.abspath(t) for t in targets[:max_targets] if t]
    
    # Step 1: classify (cheap)
    has_graph_for_any = any(gt._has_graph(t) for t in targets) if targets else False
    classified = gc.classify(prompt, has_graph=has_graph_for_any or auto_build)
    
    # Step 2: if ambiguous and we have an LLM client, defer to it
    if classified.decision == gc.Decision.LLM_CLASSIFY and ollama_client is not None:
        classified = gc.llm_classify_fallback(prompt, ollama_client)
    
    # Step 3: act on the decision
    if classified.decision != gc.Decision.USE_GRAPHIFY:
        return PreflightResult(
            decision=classified.decision.value,
            confidence=classified.confidence,
            reason=classified.reason,
            targets_queried=[],
            graph_results=[],
            context_block="",
            duration_s=time.time() - t0,
            classifier_query=classified.extracted_query,
            estimated_tokens_used=0,
        )
    
    # Step 4: graphify is not available? skip with note
    if not gt.is_installed():
        return PreflightResult(
            decision=classified.decision.value,
            confidence=classified.confidence,
            reason=f"{classified.reason}; graphify_not_installed",
            duration_s=time.time() - t0,
            classifier_query=classified.extracted_query,
        )
    
    # Step 5: query each target (build first if needed)
    query_str = classified.extracted_query or prompt
    results = []
    queried = []
    for t in targets:
        if not os.path.isdir(t):
            continue
        if auto_build and not gt._has_graph(t):
            br = gt.build(t)
            if not br.ok:
                results.append({
                    "target": t,
                    "ok": False,
                    "text": f"build failed: {br.text[:300]}",
                })
                queried.append(t)
                continue
        qr = gt.query(t, query_str, auto_build=False)
        results.append({
            "target": t,
            "ok": qr.ok,
            "text": qr.text,
            "cached": qr.cached,
            "duration_s": qr.duration_s,
        })
        queried.append(t)
    
    context = _format_context_block(query_str, results)
    
    return PreflightResult(
        decision=classified.decision.value,
        confidence=classified.confidence,
        reason=classified.reason,
        targets_queried=queried,
        graph_results=results,
        context_block=context,
        duration_s=time.time() - t0,
        classifier_query=query_str,
        estimated_tokens_used=gc.COST_GRAPH_QUERY * len(queried),
    )


def discover_targets(cwd: Optional[str] = None) -> List[str]:
    """
    Best-effort discover candidate folders to graphify-query for THIS session.
    Looks in CWD and its parents up to a drive root, plus any chharbot-known
    repos. Universal â€” not FFXI-specific.
    
    Heuristics:
    - cwd itself if it has a .git folder OR contains code files
    - any sibling folder with .git in cwd's parent
    - cwd's parent if it has .git (we may be in a subdir)
    """
    cwd = os.path.abspath(cwd or os.getcwd())
    out = set()
    
    def _is_repo(p: str) -> bool:
        return os.path.isdir(os.path.join(p, ".git"))
    
    # Walk upward looking for a git root
    cur = cwd
    for _ in range(8):
        if _is_repo(cur):
            out.add(cur)
            break
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    
    # If no git root, just use cwd
    if not out:
        out.add(cwd)
    
    return sorted(out)


# ----- self-test ---------------------------------------------------------
def _self_test() -> int:
    print("=== graphify_preflight self-test ===")
    
    # Conversational prompt â€” should skip graphify entirely
    pf = preflight("hi chharbot", targets=[os.getcwd()], auto_build=False)
    print(f"\n  test 1: conversational")
    print(f"    decision: {pf.decision}")
    print(f"    reason:   {pf.reason}")
    print(f"    targets:  {pf.targets_queried}")
    print(f"    context:  {'(empty)' if not pf.context_block else 'PRESENT'}")
    if pf.decision != "skip_graphify":
        return 1
    
    # Targeted prompt â€” should also skip
    pf = preflight("fix the bug in foo.py line 42", targets=[os.getcwd()], auto_build=False)
    print(f"\n  test 2: targeted")
    print(f"    decision: {pf.decision}")
    print(f"    reason:   {pf.reason}")
    if pf.decision != "skip_graphify":
        return 1
    
    # Structural prompt â€” would normally use_graphify, but graphify may not be installed
    pf = preflight("what calls the auth function", targets=[os.getcwd()], auto_build=False)
    print(f"\n  test 3: structural")
    print(f"    decision: {pf.decision}")
    print(f"    reason:   {pf.reason}")
    print(f"    classifier_query: {pf.classifier_query}")
    if pf.decision != "use_graphify":
        return 1
    
    # discover_targets
    targets = discover_targets()
    print(f"\n  test 4: discover_targets")
    print(f"    targets: {targets}")
    if not targets:
        return 1
    
    print("\n=== preflight self-test PASSED ===")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_self_test())

