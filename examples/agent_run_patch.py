"""Drop-in patch for any LLM agent loop."""
import logging
from autotrigger.preflight import preflight, discover_targets
_log = logging.getLogger(__name__)

def run_agent(user_prompt, history=None):
    messages = list(history or [])
    messages.append({"role": "user", "content": user_prompt})
    try:
        pf = preflight(prompt=user_prompt, targets=discover_targets(), auto_build=True)
        if pf.context_block:
            messages[-1]["content"] = pf.context_block + "\n\n---\n\n" + user_prompt
            _log.info("autotrigger: %s injected %d chars", pf.reason, len(pf.context_block))
    except Exception as e:
        _log.warning("autotrigger skipped: %s", e)
    # ... your LLM call here ...
