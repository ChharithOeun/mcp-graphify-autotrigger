---
name: autotrigger
description: Use the mcp-graphify-autotrigger toolkit for automatic pre-flight graphify analysis, full-autonomy shell delegation via delegate_shell, and post-chunk session cleanup (closing stale cmd/Notepad/PowerShell windows, clearing screenshots, recycling old artifacts). Trigger this skill whenever the user mentions "autotrigger", "delegate_shell", "cleanup session", "close stale windows", "clean up my desktop", "clear screenshots", "post-chunk cleanup", "milestone cleanup", "session-end cleanup", or asks Claude to act with "full autonomy", "drive the task end-to-end", "no chatbot delegation", or "stop pasting commands at me". Also trigger after any multi-step build session that opened terminal/notepad windows, or whenever the user signals a chunk is complete (e.g. "great work", "next chunk", "wrap this up"). The repo lives at github.com/ChharithOeun/mcp-graphify-autotrigger and is installed locally as the `autotrigger` Python package.
---

# Autotrigger - Full-Autonomy Toolkit

`mcp-graphify-autotrigger` is a Python package + MCP server that bundles three capabilities used by chharbot and by Claude in Cowork:

1. **graphify pre-flight classifier** — detect code-structural questions and run graphify before LLM calls.
2. **`delegate_shell` tool** — execute arbitrary shell commands on the user's box with no allowlist (the user has explicitly opted in to full autonomy).
3. **`cleanup_session` tool** — close stale cmd/Notepad/PowerShell windows, clear screenshots, recycle old desktop artifacts.

## Autonomy doctrine (read this first)

The user's standing instruction: **drive tasks end-to-end. Do not chatbot-delegate back to them.**

Anti-patterns to AVOID:
- "Paste this command in your shell"
- "Add this entry to your config file"
- "Open Notepad and edit ..."
- "Run this in PowerShell"

If a task requires a shell command, use `delegate_shell`. If it requires editing a file, use the file tools. If it requires closing windows, use `cleanup_session`. The user assigns the task; the agent executes it. After delivery, the user reviews and tells you what to change next.

Legitimate escalations (still allowed):
- Hardware actions (plug in a cable, restart a router).
- True credential gaps (a fresh OAuth login the user must complete in a browser).
- Value judgments (which of two design options does the user prefer).

See `docs/AUTONOMY_DOCTRINE.md` in the repo for the full text.

## Workflow

### Pre-flight graphify

Before any LLM call where the user's prompt looks structural, run:

```bash
python -m autotrigger.preflight "<user prompt>" --workspace <repo-root>
```

The script returns a JSON envelope with detected intent and any graphify output to inject into context. If the intent is not structural, it returns `{"trigger": false}` and you proceed normally.

Trigger keywords the classifier looks for: `where is`, `what calls`, `who calls`, `depends on`, `architecture`, `trace`, `impact`, `refactor`, `rename`, `find all`, `cross-file`, `dependency`, `module`, `import`, `define`, `caller`, `callee`.

### delegate_shell

For any non-trivial Windows command:

```python
from autotrigger.delegate import delegate_shell
result = delegate_shell("git status", cwd="F:/ffxi/lsb-repo")
print(result.stdout)
```

`delegate_shell` runs PowerShell on the user's box, captures stdout/stderr/exit code, times out at 5 minutes by default, and never blocks on interactive prompts. It is full-autonomy — there is no allowlist. The user has explicitly accepted that risk.

Safety rails that ARE in place:
- Hard timeouts (default 300s).
- No process tree escapes (uses `subprocess.run` with explicit args).
- Stdout/stderr captured, never streamed to terminal where it could pollute the user's session.
- Logged to `~/.autotrigger/delegate.log` for audit.

### cleanup_session

After any chunk of work that opened windows or generated screenshots:

```python
from autotrigger.cleanup import run_if_milestone, close_stale_windows
run_if_milestone(user, workspace=os.getcwd())
```

Or to force-close everything immediately:

```python
close_stale_windows(aggressive=True)
```

Aggressive mode adds `cmd`, `conhost`, `OpenConsole`, and `WindowsTerminal` to the kill list. The cleanup uses `taskkill /F /IM <name>.exe` cascade, which works on UWP Notepad and WindowsTerminal-hosted cmd (Stop-Process by name does NOT work on those).

NEVER kills: `msedgewebview2`, `claude`, `python`, `pythonw`, `explorer`, `winlogon`, `dwm`, `csrss`, `services`, `system`. These are protected by an allowlist.

### Milestone triggers

`run_if_milestone()` fires cleanup when ANY of these conditions hold:

- A chunk is marked complete (TodoList task moved to `completed`).
- The session is ending (graceful shutdown of chharbot).
- The user issues a "wrap up" / "next chunk" / "great work" signal.
- More than 30 minutes since last cleanup.

## When to use this skill

Trigger autotrigger workflow whenever:

- Multiple chunks of work have been done in a session and windows are accumulating.
- The user complains about a cluttered desktop, too many cmd windows, or "you forgot to clean up".
- A task requires running a shell command and the user has signaled full autonomy.
- The user says "next chunk" or "wrap this up" — fire `cleanup_session` automatically before starting the next thing.

## Installation check

```bash
pip show autotrigger 2>/dev/null || pip install autotrigger
```

If missing, point the user at https://github.com/ChharithOeun/mcp-graphify-autotrigger and install via `pip install -e .` from a clone.

## Source

- Repo: https://github.com/ChharithOeun/mcp-graphify-autotrigger
- Doctrine doc: `docs/AUTONOMY_DOCTRINE.md`
- Used by: chharbot agent.py preflight + post-chunk cleanup hooks.
