from autotrigger.classifier import classify, Decision

def test_structural():
    assert classify("what calls the auth function").decision == Decision.USE_GRAPHIFY

def test_targeted():
    assert classify("fix bug in login.py line 42").decision == Decision.SKIP_GRAPHIFY

def test_conversational():
    assert classify("hi there").decision == Decision.SKIP_GRAPHIFY

def test_no_graph():
    assert classify("what calls the auth function", has_graph=False).decision == Decision.SKIP_GRAPHIFY
