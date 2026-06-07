# MCP — Coding Agent Surface

ProductSense exposes a small set of tools to coding agents (Claude Code, Cursor, Lovable, etc.) over MCP with Streamable HTTP transport.

**Hosted at:** `${MCP_PUBLIC_URL}/v1/mcp` (TBD; localhost during dev).

## Tools

### Read

| Tool | Purpose |
|---|---|
| `get_session_context()` | One-call "continue" — current task, recent decisions, recent files touched, next unblocked tasks |
| `list_tasks(status?)` | List tasks, optionally filtered by status |
| `get_task(id)` | Full task spec |
| `get_decisions_log()` | Read full decisions list |
| `get_guardrails()` | Read guardrails.md |

### Write

| Tool | Purpose |
|---|---|
| `update_task_status(id, status, notes?)` | Mark in_progress / done |
| `complete_task(id, summary, files_touched[])` | Done with completion record |
| `log_files_touched(task_id, files[])` | Track files |
| `log_decision(task_id, decided_by, title, detail, why)` | For IDE-resolved decisions (`agent_with_user`) |

### Hot path

| Tool | Purpose |
|---|---|
| `request_clarification(task_id, question)` | Routes to Maya. Returns `Tier 1` answer or `Tier 3` queued response. |

## Tier 1 / Tier 3 response shape

```json
// Tier 1 (autonomous answer)
{
  "tier": 1,
  "decision_id": "D-014",
  "answer": "Yes — and lowercase normalized at insert.",
  "reasoning": "..."
}

// Tier 3 (escalated)
{
  "tier": 3,
  "decision_id": "D-015",
  "status": "queued",
  "maya_recommendation": "...",
  "next_unblocked_task_ids": ["t6", "t9"]
}
```

The agent should:
- On `tier: 1` — apply the answer and continue.
- On `tier: 3` — pick up the next unblocked task and poll back later. The clarification will be answered asynchronously and the next `get_session_context()` call will reflect the resolution.

## Permissions

Coding agents CAN: read tasks, update task status, log files touched, mark complete, ask for clarification, log IDE-resolved decisions.

Coding agents CANNOT: create new tasks, edit the PRD, reorder tasks, restructure the sprint, define scope, override guardrails.
