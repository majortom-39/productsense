# Architecture

> **Single source of truth:** the memory files at `~/.claude/projects/C--Majortom-Proojects-ProductSense/memory/`.
> This doc is a copy/summary for humans browsing the repo. When in doubt, the memory wins.

## High-level shape

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                       │
│                         FOUNDER (chat)                                │
│                              │                                        │
│                              ▼                                        │
│                    ┌──────────────────┐                               │
│                    │      MAYA        │ ◄──── MCP request_clarification│
│                    │ (Gemini 3.1 Pro) │       (from coding agent)     │
│                    └────────┬─────────┘                               │
│                             │                                          │
│        ┌────────────────────┼────────────────────┐                    │
│        │                    │                    │                    │
│        ▼                    ▼                    ▼                    │
│  ┌──────────────┐   ┌─────────────────┐  ┌─────────────────┐         │
│  │  Research    │   │   Reasoning     │  │ Pure functions  │         │
│  │  agents (5)  │   │   agents (3)    │  │ (DB writes,     │         │
│  │              │   │                 │  │  file syncs)    │         │
│  │ Iris, Aiden, │   │ Nora, Kai, Wes  │  │                 │         │
│  │ Hugo, Zara,  │   │                 │  │                 │         │
│  │ Theo         │   │ no Firecrawl    │  │ no LLM          │         │
│  │              │   │ (work over PRD/ │  │                 │         │
│  │ + Firecrawl  │   │  decisions)     │  │                 │         │
│  └──────────────┘   └─────────────────┘  └─────────────────┘         │
│       Flash Lite          Flash Lite                                  │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

## The four canonical artifacts

Every project has these four artifacts. They live in Supabase (canonical). The coding agent reads them on demand via the MCP server (`get_session_context`, `get_prd`, `get_decisions_log`, `get_guardrails`).

| File | Purpose | Owner |
|---|---|---|
| `prd.md` | Canonical product spec | Maya (only editor) |
| `sprint.md` | Live sprint board | Maya + coding agent |
| `decisions.md` | Append-only log of choices | Maya + coding agent |
| `guardrails.md` | Anti-patterns from research | Maya |

## Tier 1 / Tier 3 routing

When the coding agent calls MCP `request_clarification`:

- **Tier 1 (~80%)** — Maya answers autonomously from context. Decision auto-logged. Agent unblocks itself.
- **Tier 3 (~5%)** — Maya escalates: open decision card on Decisions tab, founder discusses with Maya in chat to resolve.

Tier 2 (tentative assumptions) doesn't reach ProductSense — the coding agent flags those in IDE chat with the founder, then calls `log_decision` to record the resolution as `agent_with_user`.
