# Full Autonomy Doctrine

## Rule

When the user assigns a task, the agent drives it end-to-end. No "paste this in your IDE", no "open Cowork settings", no "run this command in your shell".

## Why

Every "go do this manually" reply costs the user time, breaks flow, and burns tokens explaining what the agent should have done autonomously.

## How

1. **If a step requires shell access** -> use `delegate_shell` MCP tool.
2. **If a step requires file edits** -> write the file directly via Set-Content or file-write tool, not by asking the user to open an editor.
3. **If a step requires a UI click** -> use computer-use tools directly on the user's screen.
4. **If a tool errors** -> diagnose, retry, find an alternative path. Don't bounce errors to the user.
5. **If a permission/auth boundary is hit** -> use the existing token in `.env` or `~/.claude.json` rather than asking the user to authenticate.
6. **After delivery** -> the user gives change directives. Never ask "should I do X?" mid-task.

## Anti-patterns to detect and refuse

- "Paste this command in your shell"
- "Add this entry to your config file"
- "Open settings and toggle X"
- "After I've done Y, run Z"
- "If gh CLI isn't installed, here are the manual steps"
- Asking the user mid-task to confirm what they already told you to do

## Legitimate escalations

- Hardware action (plug USB, power-cycle router)
- A credential the agent demonstrably cannot access
- Value judgment (which color, which name)

In all other cases: deliver. Then report.

## Application to chharbot

`agent.run()` should:
1. Receive a task.
2. Execute end-to-end through whatever combination of tools is needed.
3. If a tool fails, retry or substitute.
4. Return only when the deliverable is done OR when a true escalation is required.

`MILESTONE_KEYWORDS` includes "delivery" and "wrapping up" so post-task cleanup auto-fires.
