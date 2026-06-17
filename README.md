<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-dark.svg">
    <img alt="ProductSense" src="docs/assets/logo-light.svg" width="420">
  </picture>
</p>

<p align="center"><b>An AI product manager for people who can build but can't <i>product</i>.</b></p>

<p align="center">
  Bring an idea. Chat with Maya. Leave with a researched PRD and a sprint board<br>
  your coding agent can pick up and build from — over MCP.
</p>

<p align="center">
  <img alt="Python 3.12" src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white">
  <img alt="React" src="https://img.shields.io/badge/React-Vite-61DAFB?logo=react&logoColor=white">
  <img alt="Gemini" src="https://img.shields.io/badge/Gemini_3.1_Pro-Vertex_AI-8E75B2?logo=googlegemini&logoColor=white">
  <img alt="LangGraph" src="https://img.shields.io/badge/LangGraph-deepagents-1C3C3C">
  <img alt="Supabase" src="https://img.shields.io/badge/Supabase-3FCF8E?logo=supabase&logoColor=white">
  <img alt="MCP" src="https://img.shields.io/badge/MCP-coding--agent_bridge-000000">
  <img alt="Cloud Run" src="https://img.shields.io/badge/Google_Cloud_Run-4285F4?logo=googlecloud&logoColor=white">
</p>

---

## The problem

A new generation of founders can *build* — they have Claude Code, Cursor, Lovable, an idea, and momentum. What they don't have is a **product manager**: someone to pressure-test the idea, find out who actually wants it, cut scope honestly, and turn "a vibe" into a buildable plan. So they build the wrong thing, beautifully, and ship it to silence.

**ProductSense is that product manager.** Her name is Maya.

## What it does

You talk to Maya in plain English — *"I want to build X"* or *"I shipped X and nobody's using it."* She:

1. **Researches it for real** — dispatches a team of specialists who dig through Reddit threads, app-store reviews, competitor pages, and forums for first-person evidence (not marketing fluff).
2. **Pushes back** — she's a coach, not a yes-man. She forces scope decisions, names the riskiest assumption, and refuses "all of it."
3. **Writes the spec** — a plain-language PRD, target users, positioning/wedge, the MVP cut, and greyscale screens — all readable by a non-technical founder.
4. **Builds the sprint board** — intent-level tasks your coding agent can actually pick up.
5. **Closes the loop over MCP** — your coding agent connects to the board, pulls tasks, builds, and reports progress back. Maya re-plans the next sprint with you, grounded in what actually got built.

> Maya owns *what to build and why.* Your coding agent owns *how.* ProductSense is the missing handshake between them.

## How it works

```mermaid
flowchart LR
    F([👤 Founder]) -->|chats in plain English| M{{🧠 Maya · AI PM}}
    M -->|delegates research| S[🔎 Specialist team<br/>Iris · Zara · Aiden · Hugo · Theo]
    S -->|Reddit · reviews · competitors| M
    M -->|drafts| P[📄 PRD + screens]
    M -->|plans| B[📋 Sprint board]
    B -->|exposed over MCP| C([🤖 Your coding agent<br/>Claude Code · Cursor · …])
    C -->|builds & reports back| M
    M -->|re-plans next sprint| B
```

Maya is the **only** voice the founder hears. Under the hood she orchestrates a team of specialists as tools — each runs in isolation, grounds its work in live web research, and returns a structured result Maya synthesizes and coaches from.

## Meet the team

| Agent | Role | What they bring back |
|------|------|----------------------|
| **Maya** | **AI Product Manager** (orchestrator) | The only one you talk to. Coaches, pushes back, runs the team, and owns the product record. |
| Iris | Problem Validator | Real-world evidence the problem is worth solving |
| Zara | User Researcher | Who the users *actually* are, in their own words |
| Aiden | Competitor Mapper | Who else solves this — and where the gaps are |
| Hugo | Risk Researcher | The likely failure modes, ranked |
| Theo | Tech Advisor | A build approach + the trade-offs your agent will hit |
| Nora | PRD Writer | Research turned into a decision-ready spec |
| Kai | Sprint Planner | The spec turned into an intent-level sprint board |

## What makes it different

- **Research grounded in real voices.** Specialists lead with Reddit threads + comments, app-store reviews (the 1–3★ ones), and forums — where the unmet need actually lives — over vendor marketing.
- **A coherence graph, not a doc dump.** Every artifact (problem → users → friction → positioning → PRD → sprint) is a node wired to what it came from. Change one upstream and everything downstream is flagged for review. The database — not chat history — is the source of truth.
- **Living artifacts.** Nothing is write-once. Maya edits cards, supersedes stale ones, and keeps the record coherent across sessions and across your agent's build.
- **A conversation, not a firehose.** One move per turn, then she hands back to you. No 1,300-line spec for a date picker.
- **The MCP loop.** The sprint board is a hosted, key-authed MCP endpoint — your coding agent pulls work and reports progress, turning the PRD into a live build cycle.

## Tech stack

| Layer | Choice |
|------|--------|
| Frontend | React 18 · Vite · Tailwind · shadcn/ui |
| Backend | Python 3.12 · FastAPI |
| Agents | [`deepagents`](https://github.com/langchain-ai/deepagents) on LangGraph — coordinator + isolated sub-agents |
| LLM | Vertex AI · **Gemini 3.1 Pro** (Maya, dynamic thinking) · Gemini Flash tiers (specialists) |
| Data + auth | Supabase (Postgres) |
| Web research | Firecrawl |
| Coding-agent bridge | Hosted **MCP** (Streamable HTTP), key-authed, served by the API |
| Infra | Google Cloud Run · Secret Manager · LangSmith tracing |

### A note on model choice

Maya runs on **Gemini 3.1 Pro with dynamic thinking**. In our own A/B benchmark against 3.5 Flash (same scenario, identical specialists), the larger orchestrator was **more reliable** (3/3 vs 2/3 clean completions), **more complete**, and — counterintuitively — **~35% cheaper per turn**, because better orchestration means fewer wasted steps and lower token burn. Reproduce it yourself: [`apps/api/scripts/bench_compare.py`](apps/api/scripts/bench_compare.py).

## Project structure

```
ProductSense/
├── apps/
│   ├── web/     React founder UI (chat + PRD / Sprint / Decisions / Screens tabs)
│   ├── api/     FastAPI — Maya coordinator, the specialist team, domain tools,
│   │            the coherence graph, and the hosted MCP endpoint
│   └── mcp/     MCP server bits for the coding-agent bridge
├── packages/
│   ├── prompts/        specialist system prompts (markdown)
│   └── shared-types/   shared TypeScript types
├── supabase/migrations/   schema (projects, artifacts, decisions, sprints, …)
├── docs/                  architecture, MCP, design notes
└── pnpm-workspace.yaml
```

## Getting started

> Requires Node 20+, pnpm, Python 3.12, a Supabase project, a Google Cloud project with Vertex AI, and a Firecrawl key.

```bash
# 1. install JS workspace deps
pnpm install

# 2. configure environment (never commit real keys — .env is gitignored)
cp .env.example .env        # then fill in Supabase / Vertex / Firecrawl values

# 3. backend  (http://localhost:8000)
cd apps/api && pip install -r requirements.txt && uvicorn main:app --reload

# 4. frontend (http://localhost:5173)
pnpm --filter web dev
```

The backend authenticates to Vertex AI via Application Default Credentials (`gcloud auth application-default login`). See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/MCP.md`](docs/MCP.md) for the full picture.

## Status

Live and running end-to-end on Google Cloud Run (single-tenant). Active development — the audience is **non-technical, first-time founders**; "experienced shippers" are explicitly out of scope for v1.

## License

Not yet licensed — © the authors, all rights reserved until a license is chosen.

---

<p align="center"><i>Bring an idea, leave with a sprint board your coding agent can build from.</i></p>
