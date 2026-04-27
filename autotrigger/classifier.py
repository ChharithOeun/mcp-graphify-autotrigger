"""
chharbot/tools/graphify_classifier.py

Auto-trigger classifier for graphify. Decides whether a given prompt should
use graphify (graph query) instead of direct file reads.

Design goals:
- Cheap: regex-first, LLM fallback only when ambiguous.
- Conservative: when in doubt, skip graphify (don't waste graph queries).
- Tunable: thresholds and patterns are top-level constants.
- Token-aware: returns expected token cost for each path so the brain can
  pick the cheaper route even when graphify is technically applicable.

Usage:
    from chharbot.tools.graphify_classifier import classify, Decision
    result = classify("how does the login flow work in lsb-repo")
    if result.decision == Decision.USE_GRAPHIFY:
        graphify_query(result.extracted_query)
    elif result.decision == Decision.LLM_CLASSIFY:
        result = llm_classify_fallback(prompt, ollama_client)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple


class Decision(str, Enum):
    USE_GRAPHIFY = "use_graphify"
    SKIP_GRAPHIFY = "skip_graphify"
    LLM_CLASSIFY = "llm_classify"


@dataclass
class ClassifierResult:
    decision: Decision
    confidence: float
    reason: str
    extracted_query: Optional[str] = None
    matched_pattern: Optional[str] = None
    expected_token_cost: int = 0  # rough, used by the brain's budget heuristic
    debug: dict = field(default_factory=dict)


# Patterns that strongly indicate a graph query is the right tool.
# (regex, confidence, reason_tag)
STRUCTURAL_PATTERNS: List[Tuple[str, float, str]] = [
    # "where is", "what calls", "what depends on"
    (r"\b(where\s+(is|are|does|do)|what\s+calls?|what\s+depends?\s+on|what\s+uses?)\b",
     0.95, "explicit_lookup"),
    # "architecture", "structure", "flow of"
    (r"\b(architecture|structure|flow\s+of|trace\s+the|how\s+(do|does)\s+.{1,60}\s+(work|interact|flow|behave))\b",
     0.85, "concept_lookup"),
    # "find all/list all references/callers/dependents"
    (r"\b(find\s+all|list\s+all|show\s+me\s+all|enumerate)\s+\w+\b",
     0.80, "enumeration"),
    # "callers of X", "dependents of Y"
    (r"\b(callers?\s+of|dependents?\s+of|impact\s+of|affected\s+by)\b",
     0.90, "dependency_lookup"),
    # Cross-cutting / multi-file phrasing
    (r"\b(across\s+the|in\s+the\s+codebase|throughout\s+the\s+(repo|project))\b",
     0.85, "cross_cutting"),
]

# Patterns that point to a SPECIFIC file/line â€” direct read beats graphify.
TARGETED_PATTERNS: List[Tuple[str, float, str]] = [
    (r"\bline\s*\d+\b", 0.90, "line_reference"),
    (r"\b[\w/\\.-]+\.(py|lua|js|ts|tsx|jsx|cpp|c|h|hpp|md|json|toml|ya?ml|sh|ps1|bat|sql|rb|go|rs)\b",
     0.80, "file_extension"),
    (r"\b(traceback|exception|stack\s*trace)\b", 0.70, "error_context"),
]

# Conversational / non-code chatter â€” skip graphify entirely.
CONVERSATIONAL_PATTERNS: List[Tuple[str, float, str]] = [
    (r"^(hi|hello|hey|thanks?|cheers|gn|gm|wb|yo|sup|ping|status\??)\b",
     0.95, "greeting"),
    (r"^what('s|s)?\s+(the\s+)?(time|date|day)\b", 0.95, "time_query"),
    (r"^(tell\s+me\s+a\s+joke|sing|rhyme|haiku)\b", 0.90, "creative"),
]

# Token cost estimates (tunable; used for budget-aware routing).
COST_GRAPH_QUERY = 2_000   # graphify query result avg
COST_FILE_READ = 5_000     # avg per-file context cost for a single read
COST_GREP_SCAN = 8_000     # unfocused grep across many files
COST_LLM_CLASSIFY = 500    # local Ollama vote
PROMPT_CAP_CHARS = 32 * 1024  # 32K char max (ReDoS / OOM protection)


def _extract_query(prompt: str) -> str:
    """Strip prompt to a focused query suitable for graphify."""
    q = prompt.strip().rstrip("?.!").lower()
    words = q.split()
    if len(words) > 14:
        q = " ".join(words[:14])
    return q


def _first_match(text: str, patterns: List[Tuple[str, float, str]]):
    """Return list of (confidence, tag, regex, match) for all matching patterns."""
    out = []
    for rx, conf, tag in patterns:
        m = re.search(rx, text)
        if m:
            out.append((conf, tag, rx, m))
    return out


def classify(prompt: str, has_graph: bool = True) -> ClassifierResult:
    """
    Decide whether to invoke graphify for this prompt.

    Args:
        prompt: user/agent prompt
        has_graph: whether a built graph exists for the working repo

    Returns:
        ClassifierResult â€” the decision plus diagnostics.
    """
    if prompt and len(prompt) > PROMPT_CAP_CHARS:
        prompt = prompt[:PROMPT_CAP_CHARS]
    if prompt is None:
        prompt = ""
    text = prompt.lower().strip()

    # Empty / trivial â€” skip
    if len(text) < 3:
        return ClassifierResult(
            decision=Decision.SKIP_GRAPHIFY,
            confidence=1.0,
            reason="empty_or_trivial",
            expected_token_cost=0,
        )

    # No graph available â€” graphify can't help
    if not has_graph:
        return ClassifierResult(
            decision=Decision.SKIP_GRAPHIFY,
            confidence=1.0,
            reason="no_graph_available",
            expected_token_cost=COST_FILE_READ,
        )

    # Conversational override beats everything
    conv_hits = _first_match(text, CONVERSATIONAL_PATTERNS)
    if conv_hits:
        best = max(conv_hits, key=lambda x: x[0])
        return ClassifierResult(
            decision=Decision.SKIP_GRAPHIFY,
            confidence=best[0],
            reason=f"conversational:{best[1]}",
            matched_pattern=best[2],
            expected_token_cost=0,
        )

    structural_hits = _first_match(text, STRUCTURAL_PATTERNS)
    targeted_hits = _first_match(text, TARGETED_PATTERNS)

    # Structural beats targeted unless targeted has clearly higher confidence
    if structural_hits:
        best_s = max(structural_hits, key=lambda x: x[0])
        best_t_conf = max((t[0] for t in targeted_hits), default=0.0)
        if best_s[0] >= best_t_conf:
            return ClassifierResult(
                decision=Decision.USE_GRAPHIFY,
                confidence=best_s[0],
                reason=f"structural:{best_s[1]}",
                extracted_query=_extract_query(prompt),
                matched_pattern=best_s[2],
                expected_token_cost=COST_GRAPH_QUERY,
                debug={"targeted_hits": [(t[1], t[0]) for t in targeted_hits]},
            )

    if targeted_hits:
        best_t = max(targeted_hits, key=lambda x: x[0])
        return ClassifierResult(
            decision=Decision.SKIP_GRAPHIFY,
            confidence=best_t[0],
            reason=f"targeted:{best_t[1]}",
            matched_pattern=best_t[2],
            expected_token_cost=COST_FILE_READ,
            debug={"structural_hits": [(s[1], s[0]) for s in structural_hits]},
        )

    # No regex matched â€” punt to LLM
    return ClassifierResult(
        decision=Decision.LLM_CLASSIFY,
        confidence=0.5,
        reason="ambiguous_no_pattern_match",
        extracted_query=_extract_query(prompt),
        expected_token_cost=COST_GRAPH_QUERY + COST_LLM_CLASSIFY,
    )


def llm_classify_fallback(prompt: str, ollama_client, model: str = "llama3.1:8b-instruct-q4_K_M") -> ClassifierResult:
    """
    LLM fallback for ambiguous cases. Calls chharbot's local Ollama with a
    tight 4-token vote: GRAPHIFY or DIRECT.

    Args:
        prompt: original user/agent prompt
        ollama_client: any object with `.chat(model, messages, options)` returning
                       {"message": {"content": str}}
        model: Ollama model tag (default llama3.1:8b-instruct-q4_K_M)

    Returns:
        ClassifierResult with USE_GRAPHIFY or SKIP_GRAPHIFY based on the vote.
    """
    system = (
        "You are a binary classifier. Given a prompt, decide if it benefits from "
        "querying a code knowledge graph (graphify) versus reading specific files. "
        "Respond with EXACTLY one word: GRAPHIFY or DIRECT. No punctuation."
    )
    try:
        response = ollama_client.chat(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            options={"num_predict": 4, "temperature": 0.0},
        )
        answer = response.get("message", {}).get("content", "").strip().upper()
    except Exception as e:
        return ClassifierResult(
            decision=Decision.SKIP_GRAPHIFY,
            confidence=0.4,
            reason=f"llm_fallback_error:{type(e).__name__}",
            expected_token_cost=COST_FILE_READ,
        )

    if "GRAPHIFY" in answer:
        return ClassifierResult(
            decision=Decision.USE_GRAPHIFY,
            confidence=0.65,
            reason="llm_classify:vote_graphify",
            extracted_query=_extract_query(prompt),
            expected_token_cost=COST_GRAPH_QUERY,
        )
    return ClassifierResult(
        decision=Decision.SKIP_GRAPHIFY,
        confidence=0.65,
        reason="llm_classify:vote_direct",
        expected_token_cost=COST_FILE_READ,
    )


# ----- self-test ---------------------------------------------------------
TEST_FIXTURES = [
    # (prompt, expected_decision)
    ("how does the login flow work in lsb-repo",       Decision.USE_GRAPHIFY),
    ("what calls the auth function",                   Decision.USE_GRAPHIFY),
    ("find all references to ai_bridge",               Decision.USE_GRAPHIFY),
    ("explain the architecture of the version sync",   Decision.USE_GRAPHIFY),
    ("show me all callers of GetDataManager",          Decision.USE_GRAPHIFY),
    ("what depends on the LSB admin API",              Decision.USE_GRAPHIFY),
    ("fix the bug in login.py line 42",                Decision.SKIP_GRAPHIFY),
    ("error in ai_bridge.lua at line 88",              Decision.SKIP_GRAPHIFY),
    ("traceback in chharbot/agent/probe.py",           Decision.SKIP_GRAPHIFY),
    ("hi chharbot",                                    Decision.SKIP_GRAPHIFY),
    ("thanks",                                         Decision.SKIP_GRAPHIFY),
    ("what time is it",                                Decision.SKIP_GRAPHIFY),
    ("write me a poem about FFXI",                     Decision.LLM_CLASSIFY),
    ("can you summarize the recent activity",          Decision.LLM_CLASSIFY),
]


def _run_self_test() -> int:
    print("=== graphify_classifier self-test ===")
    passed = 0
    failed = 0
    for prompt, expected in TEST_FIXTURES:
        r = classify(prompt)
        ok = r.decision == expected
        status = "OK  " if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
        print(f"  [{status}] '{prompt[:55]}'")
        print(f"          -> {r.decision.value} ({r.confidence:.2f}) {r.reason}")
        if r.extracted_query:
            print(f"          query: '{r.extracted_query}'")
        if not ok:
            print(f"          EXPECTED: {expected.value}")
    print(f"=== {passed} passed, {failed} failed ===")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(_run_self_test())

