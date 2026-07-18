# Architecture

> **Single source of truth:** the memory files at `~/.claude/projects/C--Majortom-Proojects-ProductSense/memory/`.
> This doc is a copy/summary for humans browsing the repo. When in doubt, the memory wins.

## High-level shape

Maya is a **single agent** — one Gemini 3.1 Pro brain holding every tool directly.
There are no sub-agents (the former research/synthesis team was removed in June 2026;
see "Why no sub-agents" below).

```
   FOUNDER (browser)                       CODING AGENT (IDE)
        │  REST + SSE stream                    │  MCP, key-authed
        ▼                                       ▼
┌───────────────────────────────────────────────────────────────────┐
│  FastAPI on Cloud Run  (scale-to-zero, CPU kept allocated)        │
│                                                                   │
│  MayaSession — turn runner            GitHub integration          │
│  · detached turn task (survives       · OAuth (token Fernet-      │
│    SSE drops)                           encrypted in Supabase)    │
│  · event queue + 15s heartbeat        · repo digest ingest        │
│  · post-turn research pruning           (README, packages, tree)  │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Deep agent  (deepagents / LangGraph)                       │  │
│  │                                                             │  │
│  │   MAYA — Gemini 3.1 Pro, dynamic thinking (the only agent)  │  │
│  │     ├─ ask_founder        steering interrupt                │  │
│  │     ├─ domain tools ~30   artifacts / PRD / sprint /        │  │
│  │     │                     decisions / read_attachment       │  │
│  │     └─ research tools ×3  web_search · reddit_research ·    │  │
│  │                           crawl_website (budget 5/turn)     │  │
│  │                                                             │  │
│  │   SummarizationMiddleware   compacts history near ~890k     │  │
│  │   AsyncPostgresSaver        checkpoint every turn           │  │
│  │   Skills + memory           product-arc skill, read-only    │  │
│  └─────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
     │             │              │               │            │
  Supabase      Vertex AI      Firecrawl      LangSmith     GitHub
  data+auth     Gemini         search/scrape  run traces    repo digest
```

Key mechanics:

- **Turns are detached.** Each founder message runs as a background task owned by
  `MayaSession` (`apps/api/app/deepagent/session.py`). If the browser tab hides and
  the SSE socket drops, the turn keeps running; the frontend reconciles when it
  reconnects. Cloud Run keeps CPU allocated so the detached task never freezes.
- **Think first, search rarely.** Maya's prompt tells her to answer from her own
  reasoning and reach for the research tools only when a claim needs real-world
  backing. Searches are hard-capped at 5 per turn.
- **Context stays lean without sub-agent isolation.** After each turn, raw research
  tool results are pruned from the conversation history (replaced with a stub) —
  Maya's synthesis survives, the snippet dumps don't.
- **State lives in Postgres.** The LangGraph checkpointer (AsyncPostgresSaver on the
  Supabase pooler) saves every turn, which is also what makes `ask_founder`
  interrupts resumable across turns.

## Why no sub-agents

Two A/B benchmarks, both in-repo:

1. `apps/api/scripts/bench_compare.py` — a Pro orchestrator vs a Flash orchestrator:
   Pro was more reliable and ~35% cheaper per turn (fewer wasted steps).
2. `scripts/bench_research_ab.py` — a Flash research sub-agent vs Maya (Pro) holding
   the identical tools: Pro caught a false premise in the research question that the
   Flash sub-agent built on uncritically.

Conclusion: a weaker model in the thinking path costs quality, and the isolation
benefit (keeping search dumps out of Maya's context) is achievable with post-turn
pruning instead. Sub-agents that only reshaped context Maya already had (PRD
drafting, sprint planning) were removed for the same reason — Maya authors the PRD
and sprint herself, incrementally, with domain tools.

## GitHub integration

`apps/api/app/routes/integrations.py` + `apps/api/app/services/github_client.py`.

- **OAuth round-trip:** founder authorizes on GitHub → web app callback → backend
  exchanges the code, encrypts the token (Fernet, `ASSET_ENCRYPTION_KEY`), stores it
  in `github_connections`.
- **Repo digest:** on linking, `ingest_repo` pulls README, package/config files, and
  the top-level tree into a markdown digest stored as a project asset
  (`source_kind: 'github_repo'`) and loaded into Maya's context — this grounds her
  tech advice in the real codebase (anti-drift).
- Deliberately narrow: no webhooks, no per-file reads. File-level work belongs to
  the coding agent in the IDE, which reads the repo locally and reports over MCP.

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
