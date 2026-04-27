# Changelog

All notable changes to mcp-graphify-autotrigger.

## [0.3.0] - 2026-04-27

### Added
- **`mcp_server/agent_tools.py`** — full agent-tool parity layer registering 8
  new MCP tools so chharbot can stand in for Cowork-Claude / Claude Code on any
  delegated task without losing capability:
  - `read_file(path, offset, limit)` with line-numbered output (mirrors Read).
  - `write_file(path, content)` with 5 MiB cap (mirrors Write).
  - `edit_file(path, old, new, replace_all)` with uniqueness enforcement
    (mirrors Edit).
  - `glob_files(pattern, path)` mtime-sorted (mirrors Glob).
  - `grep_files(pattern, path, glob, output_mode)` ripgrep-backed with
    pure-Python fallback (mirrors Grep).
  - `bash(command, cwd, timeout, env)` cross-platform shell with output caps
    (mirrors Bash).
  - `skill_dispatch(name)` — load any Claude Code skill from
    `~/.claude/skills/` and return its SKILL.md so a remote LLM can follow it
    without re-publishing each skill as a Cowork plugin.
  - `list_skills()` — enumerate installed skills with descriptions.
- **`plugins/chharbot-tools.plugin`** — drop-in Cowork plugin bundling the
  graphify and autotrigger SKILL.md files plus an `.mcp.json` that points at
  this server. Click-to-install via the Cowork plugin card.
- **`tests/test_agent_tools.py`** — 12 unit tests covering registration,
  read/write/edit roundtrip, glob, grep, bash, skill_dispatch (including path
  traversal rejection), and list_skills.

### Changed
- **`pyproject.toml`** — BOM stripped (was breaking pytest config parsing) and
  version bumped to 0.3.0.
- **README** — split tool list into "original 7" and "agent-tool parity new 8";
  documented the Cowork plugin install path alongside the Claude Code skill
  installer.

### Hardening
- All agent_tools entries route through a per-call audit log at
  `~/.chharbot/agent-audit.log` (JSONL).
- Size caps on every payload: 1 MiB read, 5 MiB write, 256 KiB stdout/stderr,
  1000-result cap on glob/grep, 10s timeout floor + 600s ceiling on bash.
- `skill_dispatch` validates names against `^[a-z0-9][a-z0-9_-]{0,63}$` to
  block path-traversal-style inputs.

## [0.2.1] - 2026-04-27

- Aggressive cleanup mode (`taskkill /F /IM` cascade for UWP Notepad +
  WindowsTerminal-hosted cmd).
- `docs/AUTONOMY_DOCTRINE.md` — formal doctrine: drive tasks end-to-end, no
  chatbot delegation back to user.

## [0.2.0] - 2026-04-26

- Auto-cleanup tool (`cleanup_session`): close stale windows, clear
  screenshots, recycle desktop artifacts. `run_if_milestone` hook plumbed
  into chharbot agent.

## [0.1.x] - 2026-04-25

- Initial release: graphify auto-trigger classifier + delegate_shell + MCP
  server (7 FastMCP tools).
- Flashy README banner, SECURITY.md, input size hardening, security tests.
