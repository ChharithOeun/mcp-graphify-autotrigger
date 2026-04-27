---
name: graphify
description: Build and query a code knowledge graph using the safishamsi/graphify CLI. Trigger ANY time the user asks structural code questions ("where is X defined", "what calls Y", "what depends on Z", "trace function", "find all callers", "dependency chain", "graphify this repo", "/graphify"), explores cross-file relationships, function call chains, module dependencies, symbol definitions, refactoring impact, or large-codebase navigation. Trigger PROACTIVELY when the user explores an unfamiliar repo, plans a refactor, investigates a multi-file bug, or does architecture review. Also trigger on "code map", "knowledge graph", "AST", "tree-sitter", "impact analysis". User has graphify installed as `graphifyy` pip package, exposed as `graphify` on PATH.
---

# Graphify - Code Knowledge Graph

Graphify is a CLI that builds a queryable knowledge graph of any codebase using tree-sitter AST extraction. It's faster and more accurate than grep for structural questions.

## When to use this skill

Use graphify whenever the user asks about code structure, relationships, or cross-file dependencies. Examples:

- "Where is `process_order` defined?" → `graphify query "process_order"`
- "What calls `validate_user`?" → `graphify callers validate_user`
- "What does `payment_service` depend on?" → `graphify deps payment_service`
- "Show me the architecture of this repo" → `graphify build && graphify summary`
- "Trace the login flow" → `graphify trace login`
- "What's affected if I rename `Order.total`?" → `graphify impact Order.total`

If the user is exploring a codebase they don't know, build the graph first, then query.

## Workflow

### Step 1: Build the graph (one-time per repo)

```bash
cd <repo-root>
graphify build
```

This walks the repo, parses each file via tree-sitter, and writes the graph to `.graphify/graph.db` (sqlite). Builds are incremental — re-running only re-parses changed files.

If `graphify build` is slow (>30s for a large repo), tell the user the build is in progress rather than letting it look hung.

### Step 2: Query

Common queries:

| Question | Command |
|---|---|
| Find symbol definitions | `graphify query "<name>"` |
| List callers of a function | `graphify callers <function>` |
| List callees of a function | `graphify callees <function>` |
| Module/file dependencies | `graphify deps <module>` |
| Reverse dependencies | `graphify rdeps <module>` |
| Architecture summary | `graphify summary` |
| Impact analysis | `graphify impact <symbol>` |

Run the relevant query, parse the output (newline-delimited records: `file:line  symbol  context`), and present the answer in plain prose with file paths and line numbers.

### Step 3: Keep the graph fresh

After significant edits, re-run `graphify build` (incremental — fast). For a brand-new clone, build before any queries.

## Output formatting

When showing graphify results to the user:

1. Lead with the direct answer (the file:line and symbol).
2. Show 1-3 surrounding context lines if helpful.
3. If there are many results (>10), summarize the pattern and offer to drill in.
4. Always cite `path:line` so the user can jump to the source.

## Auto-trigger heuristic

Trigger graphify when ANY of these conditions hold:

- The user asks a structural code question (where/what calls/what depends).
- The user starts work on an unfamiliar repo (>50 files).
- The user is planning a refactor or rename.
- The user asks for an architecture overview, code map, or dependency chain.
- The user types `/graphify` or mentions "graphify" by name.

Do NOT use graphify for:

- Single-file questions (just read the file).
- Runtime debugging (that's traces/logs, not static graph).
- Questions about content/text (use grep).

## Companion: autotrigger MCP

The user's chharbot instance has the `mcp-graphify-autotrigger` MCP server which fires graphify automatically as a pre-flight before LLM calls when it detects a code-structural question. That covers the chharbot path; this skill covers the Cowork/Claude path so behavior is consistent across both.

## Installation check

If `graphify` is not on PATH, instruct the user once: `pip install graphifyy` (or point them at https://github.com/safishamsi/graphify). Don't keep retrying.

## Source

- Upstream CLI: https://github.com/safishamsi/graphify
- chharbot integration: https://github.com/ChharithOeun/mcp-graphify-autotrigger
