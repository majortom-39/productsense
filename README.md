# ProductSense

AI product manager (Maya) for non-technical solopreneurs. The founder chats with Maya in natural language; Maya runs research, drafts a PRD, generates a sprint board, and exposes everything via MCP so the founder's coding agent can pick up tasks and report progress.

> Bring an idea, leave with a sprint board your coding agent can pick up and build from.

---

## Status

**Pre-scaffolding.** This repo is the planned destination for ProductSense v1. The architecture, scope, agent design, database schema, tech stack, and implementation plan are all locked.

**Read first:** the memory files in `~/.claude/projects/C--Majortom-Proojects-ProductSense/memory/` (auto-loaded by Claude Code when working in this directory). They contain the full context.

Predecessor codebase: `C:\Majortom\Proojects\Productsense v.0` — kept for reference only, not actively developed. Visual preview UI lives there at `frontend/src/pages/Preview.tsx`.

---

## Planned structure

```
ProductSense/
├── apps/
│   ├── web/              # React/Vite/shadcn — founder UI
│   ├── api/              # FastAPI — Maya + sub-agents
│   └── mcp/              # MCP server (Streamable HTTP) — coding-agent bridge
├── packages/
│   ├── shared-types/     # TS types shared across apps
│   └── prompts/          # Agent system prompts (markdown)
├── supabase/
│   ├── migrations/
│   └── policies/
├── docs/
└── pnpm-workspace.yaml
```

## Stack

- **Frontend:** React 18 + Vite + Tailwind + shadcn/ui
- **Backend:** Python 3.12 + FastAPI
- **LLM:** Vertex AI — Gemini 3.1 Pro (Maya) + Gemini 3.1 Flash Lite (sub-agents)
- **Database:** Supabase (Postgres + Auth + Realtime + Storage)
- **Web research:** Firecrawl
- **MCP:** Anthropic Python MCP SDK with Streamable HTTP

## The team (sub-agents)

**Maya** — orchestrator (Gemini 3.1 Pro)

Research agents (Firecrawl-driven, Gemini 3.1 Flash Lite):
- **Aiden** — Competitor Mapper
- **Iris** — Problem Validator
- **Hugo** — Risk Researcher
- **Zara** — User Researcher
- **Theo** — Tech Advisor

Reasoning agents (no Firecrawl, Gemini 3.1 Flash Lite):
- **Nora** — PRD Writer
- **Kai** — Sprint Planner
- **Wes** — Guardrail Compiler

## License

TBD.
