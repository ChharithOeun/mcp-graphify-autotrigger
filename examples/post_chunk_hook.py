"""Example: auto-cleanup after every milestone in your agent loop."""
from autotrigger.cleanup import on_milestone, run_if_milestone, run_full_cleanup


# Pattern A: decorator on a chunk-handler function
@on_milestone(workspace="F:/your/repo", dry_run=False)
def process_chunk(chunk):
    # ... do work ...
    return {"status": "ok"}


# Pattern B: keyword-detect inline (recommended for chharbot agent.run())
def run_agent(user_prompt, history=None, workspace=None):
    workspace = workspace or "F:/your/repo"
    messages = list(history or [])
    messages.append({"role": "user", "content": user_prompt})

    # ... your LLM call here ...
    response = "..."

    # Auto-cleanup if user signals milestone
    cleanup_result = run_if_milestone(user_prompt, workspace=workspace)
    if cleanup_result:
        for step, r in cleanup_result.items():
            print(f"[cleanup] {step}: {r.summary()}")

    return response


# Pattern C: explicit at session-end
if __name__ == "__main__":
    out = run_full_cleanup("F:/your/repo")
    for step, r in out.items():
        print(f"{step}: {r.summary()}")
