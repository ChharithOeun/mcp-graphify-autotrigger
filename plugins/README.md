# Cowork Plugin

`chharbot-tools.plugin` is a drop-in Cowork plugin that bundles the slash-command skills and the chharbot MCP server so /graphify, /autotrigger, and the full chharbot tool surface light up natively in Cowork.

## Install

1. Open Cowork.
2. Drag `chharbot-tools.plugin` into the chat (or use a `present_files` install card from an agent).
3. Click **Add** on the install card.
4. Restart Cowork.
5. Type `/graphify` or `/autotrigger` to verify the slash commands appear. The chharbot MCP server starts automatically; tools like `chharbot.delegate_shell`, `chharbot.bash`, `chharbot.read_file`, `chharbot.skill_dispatch` show up in the tool list.

## What's inside

```
chharbot-tools.plugin (zip)
├── .claude-plugin/
│   └── plugin.json           # name + version + metadata
├── skills/
│   ├── graphify/SKILL.md     # /graphify slash command
│   └── autotrigger/SKILL.md  # /autotrigger slash command
├── .mcp.json                 # launches python -m mcp_server.server
└── README.md
```

The `.mcp.json` points at `F:\ChharithOeun\mcp-graphify-autotrigger` as the cwd. If your install lives elsewhere, edit the plugin (it's just a zip) and update that path before installing.

## Tools surfaced

After install, Cowork sees the full chharbot toolkit:

**Original 7 (existed in v0.2.x):** `delegate_shell`, `graphify_query`, `graphify_build`, `graphify_preflight`, `graphify_classify`, `graphify_path`, `tools_status`, plus `cleanup_session`.

**Agent-tool parity (new in v0.3.0):** `read_file`, `write_file`, `edit_file`, `glob_files`, `grep_files`, `bash`, `skill_dispatch(name)`, `list_skills`.

That parity layer is what makes end-to-end delegation work without friction: any tool call Cowork-Claude or Claude Code makes natively has a 1:1 chharbot MCP equivalent, audit-logged with size caps.

## Rebuilding the .plugin

The plugin is a plain zip. To rebuild after editing source files:

```bash
cd path/to/chharbot-plugin-source && zip -r ../chharbot-tools.plugin . -x "*.DS_Store"
```
