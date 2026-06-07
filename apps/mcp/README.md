# MCP Server

ProductSense's MCP server is the surface that coding agents (Claude Code, Cursor, etc.) connect to. It exposes a small set of tools for reading sprint state, updating task status, asking Maya for clarification, and logging decisions.

**Status:** scaffolding only. Phase 5 fills this in.

See `~/.claude/projects/C--Majortom-Proojects-ProductSense/memory/architecture.md` (section "MCP routing") for the full design.

## Transport

Streamable HTTP. Hosted at `${MCP_PUBLIC_URL}/v1/mcp`.

## Tool surface

| Tool | Purpose |
|---|---|
| `get_session_context()` | The "continue" call — one MCP roundtrip returns everything needed to resume work |
| `list_tasks(status?)` | List tasks, optionally filtered |
| `get_task(id)` | Full task spec |
| `update_task_status(id, status, notes)` | Mark in_progress / done |
| `complete_task(id, summary, files[])` | Done with completion record |
| `request_clarification(task_id, question)` | Routes to Maya for Tier 1/3 |
| `log_decision(...)` | Log a decision resolved in IDE (`agent_with_user`) |
| `log_files_touched(task_id, files[])` | Track files |
| `get_decisions_log()` | Read full decisions list |
| `get_guardrails()` | Read guardrails.md |
