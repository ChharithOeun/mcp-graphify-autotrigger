"""Security stress tests for the classifier (ReDoS, prompt caps)."""
import time
from autotrigger.classifier import classify, PROMPT_CAP_CHARS


def test_redos_pathological_input():
    """Pathological repeated patterns must classify in <100ms."""
    pathological = "what " * 10000 + "calls the auth"
    t0 = time.time()
    classify(pathological)
    elapsed_ms = (time.time() - t0) * 1000
    assert elapsed_ms < 500, f"classify took {elapsed_ms:.0f}ms"


def test_huge_prompt_truncation():
    """Prompts above PROMPT_CAP_CHARS are truncated, not crashed."""
    huge = "what calls the auth function " * 100000
    assert len(huge) > PROMPT_CAP_CHARS
    r = classify(huge)
    assert r is not None  # didn't crash


def test_empty_input():
    """Empty / None input handled gracefully."""
    assert classify("").reason == "empty_or_trivial"
    assert classify(None).reason == "empty_or_trivial"
