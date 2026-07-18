# Agents

There is exactly **one** agent.

| Agent | Role | Model | Tools |
|---|---|---|---|
| **Maya** | AI product manager — the only voice the founder hears | Gemini 3.1 Pro, dynamic thinking (HIGH) | `ask_founder` · ~30 domain tools · 3 research tools |

The former sub-agent team (Iris, Zara, Aiden, Hugo, Theo, Nora, Kai, Remy, Wes)
was removed in June 2026 — first the synthesis agents (Maya authors the PRD and
sprint herself), then the research agents (Maya holds the web tools directly).
Rationale + benchmarks: see [ARCHITECTURE.md](ARCHITECTURE.md) "Why no sub-agents".
The only entry left in the deepagents `subagents` list is a neutered
`general-purpose` placeholder whose sole job is to suppress the framework's
default all-tools agent.

## Maya's tools

- **`ask_founder`** — steering interrupt. Pauses the turn, puts a decision in
  front of the founder, resumes on answer (resumable via the Postgres
  checkpointer).
- **Domain tools (~30)** — `apps/api/app/deepagent/domain_tools.py`. Create/update
  artifacts, personas, solutions, features, PRD sections (`write_prd_section`),
  decisions, sprints, tasks; `read_attachment` for founder uploads. All write to
  Supabase and emit dashboard events.
- **Research tools (3)** — `apps/api/app/deepagent/research_tools.py`:
  `web_search`, `reddit_research`, `crawl_website` (Firecrawl). Hard budget of
  **5 searches per turn**; raw results are pruned from history after each turn.

## Behavioral invariants

- Maya is the only chat participant. Tool names and internals never surface in
  founder chat.
- **Think first, search rarely.** Maya defaults to her own knowledge; research
  tools are for claims that need live, real-world backing (evidence of demand,
  competitor facts, pricing) — never for things she already knows.
- One move per turn — she never runs the whole product arc in a single turn.
- Founder-facing language is plain English; every artifact must be readable by a
  non-technical founder.
- Maya pushes back: forces scope choices, refuses "all of it", names the riskiest
  assumption.
- Anything needing the founder's brain becomes an open question on the Decisions
  tab (or an `ask_founder` interrupt mid-turn) — not buried in prose.

## Where prompts live

- **Maya's system prompt** is code: `MAYA_SYSTEM_PROMPT` in
  `apps/api/app/deepagent/coordinator.py` — edit it there.
- `packages/prompts/*.md` holds persona/voice material loaded at startup
  (`app/services/prompts.py`) plus the legacy specialist prompts, which are kept
  only as reference and for the research A/B benchmark
  (`scripts/bench_research_ab.py`).
- The `product-arc` skill (how to run the idea → PRD → sprint arc) lives at
  `apps/api/app/deepagent/knowledge/skills/product-arc/SKILL.md` and is loaded
  read-only into the agent.
