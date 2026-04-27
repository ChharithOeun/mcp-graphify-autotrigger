# mcp-graphify-autotrigger

[![CI](https://github.com/ChharithOeun/mcp-graphify-autotrigger/actions/workflows/ci.yml/badge.svg)](https://github.com/ChharithOeun/mcp-graphify-autotrigger/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-ready-7E22CE.svg)](https://modelcontextprotocol.io)
[![FastMCP](https://img.shields.io/badge/FastMCP-3.0+-0EA5E9.svg)](https://gofastmcp.com)
[![Buy Me A Coffee](https://img.shields.io/badge/%E2%98%95-Buy%20Me%20A%20Coffee-FFDD00?style=flat&logoColor=white)](https://buymeacoffee.com/chharith)

> **Auto-trigger graphify knowledge-graph queries on every LLM prompt + MCP shell delegation for Claude Code / Cowork agents.**
> Turn 200K-token codebase context dumps into 2K-token graph queries. Give your AI agent unrestricted shell autonomy when tier-restricted apps get in the way.

## What it does

Two complementary tools that drop into any AI agent loop (Claude Code, Cowork, OpenCode, Cursor, custom Ollama agents):

1. **Auto-trigger graphify** - classifies every prompt (structural / targeted / conversational), and when the prompt benefits from a code knowledge graph, queries [graphify](https://github.com/safishamsi/graphify) and injects a small context block instead of letting the agent grep through dozens of files. **10-50x token reduction** on architecture / dependency questions.
2. **Shell delegation MCP server** - FastMCP server exposing `delegate_shell(argv, cwd, timeout)` so external agents (e.g. Claude in Cowork, where shells are tier-restricted) can drive any shell command through your unrestricted Python process. Audit-logged. No allowlist by design (full autonomy by config).

## Quick Start

```bash
pip install mcp-graphify-autotrigger[all]
graphify install
graphify claude install
cd /path/to/your/repo
graphify update .
claude mcp add chharbot_tools -- python -m mcp_server.server
```

After registering and restarting your assistant, the new tools (`delegate_shell`, `graphify_query`, `graphify_build`, `graphify_preflight`) appear in the tool list.

## Why

### Token savings - concrete

| Approach          | Tool calls | Tokens (avg) |
|-------------------|-----------|--------------|
| read + grep       | 30+       | 150K-300K    |
| **graphify query** | 1         | **~2K**      |

Net **80-150x reduction** on cross-cutting code questions. The auto-trigger classifier decides per-prompt, so simple "fix login.py:42" prompts pay no extra cost.

### Autonomy - concrete

Claude Code / Cowork enforces tier-based restrictions: terminals are click-only, browsers are read-only. Without delegation, an agent debugging your Windows machine can't pip-install, can't git-commit, can't run any shell command. With `delegate_shell` it routes through your unrestricted Python process: full autonomy, audit-logged, your config flag away from disabling.

## Features

- Regex-first classifier with 14/14 self-test, LLM fallback hook for ambiguous cases
- Universal - works on any drive, any folder (not project-specific)
- Per-target graph cache at `~/.chharbot/graphs/<sha256(realpath)>/`
- Token-cost-aware - returns expected cost so the brain can pick the cheaper route
- Graceful degradation if graphify isn't installed
- Stdin / stdout / stderr capture with size caps (256KB / 64KB)
- Audit log at `~/.chharbot/delegate-audit.log` (JSONL)
- MCP-ready - exposes 7 FastMCP tools

## Usage

### As a Python library

```python
from autotrigger.preflight import preflight, discover_targets

pf = preflight(
    prompt="how does the auth flow work in this repo",
    targets=discover_targets(),
    auto_build=True,
)
if pf.context_block:
    user_message = pf.context_block + "\n\n---\n\n" + user_message
```

### Drop-in patch

See [`examples/agent_run_patch.py`](./examples/agent_run_patch.py) - 8 lines you paste at the top of your `run()` method, before the LLM call.

### MCP tools exposed

| Tool                  | Description |
|-----------------------|-------------|
| `delegate_shell`      | Run any shell command on chharbot's unrestricted Python. No allowlist. Audit-logged. |
| `graphify_query`      | English query against any drive/folder's knowledge graph. |
| `graphify_build`      | Build/rebuild a graph for any folder. |
| `graphify_path`       | Shortest path between two nodes. |
| `graphify_preflight`  | Always-on auto-trigger; returns injectable Markdown context block. |
| `graphify_classify`   | Classifier-only without running graphify. |
| `tools_status`        | Health check (graphify installed, audit log size, cached graphs). |

## Related

- [graphify](https://github.com/safishamsi/graphify) - the underlying knowledge-graph CLI
- [FastMCP](https://gofastmcp.com) - the MCP server framework
- [Model Context Protocol](https://modelcontextprotocol.io) - the spec

## License

MIT - see [LICENSE](./LICENSE).

## Support

[![Buy Me A Coffee](https://img.shields.io/badge/%E2%98%95-Buy%20Me%20A%20Coffee-FFDD00?style=for-the-badge&logoColor=white)](https://buymeacoffee.com/chharith)

Issues and PRs welcome at [GitHub](https://github.com/ChharithOeun/mcp-graphify-autotrigger/issues).
