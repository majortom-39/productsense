# ProductSense — Implementation Progress

> Single source of truth for build status and remaining work.
> Memory files stay authoritative for *design intent*; this file tracks *execution*.

**Last updated:** 2026-05-15
**Status:** ✅ **Production-ready.** All 10 phases of the Dynamic Artifacts redesign + all 6 phases of the Asset Manager + GitHub integration complete on top of the previously-shipped P0–P7 build, hardening pass, and LangGraph migration. **78/78 unit + integration tests passing.** Web production bundle 162 KB main / 44 KB gzipped (code-split vendor chunks for recharts/markdown/supabase). API + MCP both load cleanly.

---

## Current architecture (one paragraph)

Maya is a LangGraph state graph (`build_graph` → ChatVertexAI bound to 15 StructuredTools → conditional ToolNode). She runs on **Gemini 3.1 Pro Preview** (no extended thinking — disabled because Pro + thinking + streaming + tools is unreliable for structured tool calls). Sub-agents run on tiered Gemini (Pro+HIGH for Theo/Kai, Pro+MEDIUM for Nora/Hugo, Flash for Iris/Aiden/Zara/Wes). Each sub-agent invocation is recorded in `agent_runs` with a structured `output_payload` containing `render_kind` + `payload` + finding + bullets + sources. The chat's `AgentCallCard` renders that payload **inline via the same `<ArtifactRenderer>` dispatcher the dashboard uses** — actual table / bar chart / persona cards / matrix / etc., not JSON. Maya curates the dashboard's Research tab through 4 explicit tools (`pin_artifact`, `create_artifact`, `update_artifact`, `delete_artifact`). She owns artifact freshness behaviorally — no auto-staleness flags. **The asset manager (Phase 11) gives the founder a paperclip in chat + a GitHub Settings page** to attach files / link a repo; the asset manager auto-digests each into a markdown summary that gets prepended to Maya's prompt as a "Project context layer" — not a sub-agent, just background reading. Frontend is React + Vite + shadcn on port 5176, talking to FastAPI on 8000 (SSE for chat) and a separate FastMCP server on 8765 for outbound coding-agent integration.

---

## Live infrastructure (verified working)

| | |
|---|---|
| Supabase project | `productsense-v1` (`sghdrmmceovqzrjtouej.supabase.co`, us-east-1) |
| Migrations applied | 5 (init, rls, enrich_for_coding_agents, dynamic_artifacts, asset_manager) |
| Tables | 14 (projects, prds, prd_sections, sprints, tasks, decisions, messages, clarifications, **agent_runs**, **research_artifacts**, **project_assets**, **github_connections**, **project_repo_links**) |
| Auth | ES256 JWKS verification working against real user tokens (HS256 supported as fallback) |
| Vertex AI | `gemini-3.1-pro-preview` for Maya/Theo/Kai/Nora/Hugo, `gemini-3-flash-preview` for Iris/Aiden/Zara/Wes — `location=global` |
| Firecrawl | `web_search`, `crawl_website`, `reddit_research` |
| Service role + anon keys | in `.env`, working |
| API surface | 36 routes registered |
| MCP surface | 11 tools registered |
| Maya tool surface | 15 StructuredTools (11 sub-agent/synthesis + 4 dashboard curation) |
| Asset ingestors | 5 typed (text, pdf, code, csv, image) + 1 repo (GitHub tree + key files) |

---

## Phase ledger

### Done

- **P0 — Bootstrap** ✅ — workspace, Python deps, .env scaffolding
- **P1 — API foundation** ✅ — FastAPI + Supabase auth (ES256 JWKS) + project CRUD
- **P2 — Maya streaming chat** ✅ — Vertex client, MayaSession, SSE route, web chat UI
- **P3 — Sub-agents + tool calls** ✅ — 8 agents, agent_runner, tool router, SSE event types
- **P4 — Frontend tabs** ✅ — Research / PRD / Sprint / Decisions tabs, RightPanel shell
- **P5 — MCP server** ✅ — FastMCP + Streamable HTTP, 10 tools, Tier 1/3 clarification routing
- **P6 — Sync CLI** ⛔ removed (2026-05-15) — was a 10-second polling daemon that mirrored 4 markdown files to disk. Redundant once the MCP server became the canonical coding-agent bridge: MCP is fresher (on-demand), bidirectional (status updates flow back), and complete (research artifacts included via `get_session_context`). The disk-files approach also missed the new dynamic Research artifacts entirely. The "Sync to Repo" sidebar block was UI theatre — no daemon was actually running in the web flow. Killed cleanly: workspace package deleted, sidebar block removed, docs swept.
- **P7 — Tests + hardening** ✅ — auth, rate limiting, security headers, MCP origin validation, structured JSON logs
- **Hardening pass (2026-05-09)** ✅ — Vertex parallel-call fix (`function_responses_turn`), JWKS auth, rate limits, MCP spec compliance, Supabase project provisioning
- **LangGraph migration** ✅ — Replaced hand-rolled Gemini-streaming Maya orchestrator with LangGraph + LangChain `bind_tools`. Verified empirically: structured `tool_calls: 1` from Pro through `bind_tools`. New files: `maya_graph.py`, `maya_tools_lc.py`. Maya runs without extended thinking; narrates reasoning in prose.

### Dynamic Artifacts (Phases 1–10, 2026-05-14 → 2026-05-15) ✅

The big shift: sub-agent runs no longer auto-persist to a `research` table. Sub-agents pick a `render_kind` per finding (text / table / matrix / bar_chart / line_chart / graph / persona_cards / stack_diagram); their output flows back to Maya as a tool result AND renders **in the chat** via an artifact dispatcher. Maya curates the dashboard via 4 explicit tools. No founder-facing refresh button; no auto-staleness flagging. Maya owns artifact freshness behaviorally.

| # | Phase | Status |
|---|---|---|
| 1 | **Schema migration** — `agent_runs` rebuilt, `research_artifacts` new, `research` dropped | ✅ |
| 2 | **Backend sub-agent flow** — no auto-persist, dedup against agent_runs, output carries render_kind+payload | ✅ |
| 3 | **Artifacts service + Maya tools** (pin/create/update/delete) — 4 StructuredTools added, total surface 15 | ✅ |
| 4 | **Frontend renderers + recharts** — 8 components (TextCard/TableCard/MatrixCard/BarChartCard/LineChartCard/GraphCard/PersonaCardsCard/StackDiagramCard) + ArtifactRenderer dispatcher | ✅ |
| 5 | **Chat inline rendering** — AgentCallCard uses ArtifactRenderer; CompactToolChip for housekeeping; "Pinned ✓" badge derived from session items | ✅ |
| 6 | **Dashboard wired to new schema** — ResearchTab fully rewritten; ResearchItem legacy type dropped; categories/staleness/refresh removed | ✅ |
| 7 | **"Add to chat" action** on every dashboard card — unified through `onAskMaya` → ChatPanel prefillText | ✅ |
| 8 | **Maya prompt update** — Dashboard curation section, "You own freshness" rule, render_kind guidance, parallel-call examples | ✅ |
| 9 | **Tests** — test_agentic_e2e updated for agent_runs; new test_dynamic_artifacts.py (23 tests, 19s) | ✅ |
| 10 | **Cleanup + production-ready** — orphan sweep clean; vite chunk splitting (148 KB main vs 1037 KB before); cross-app integrity verified | ✅ |

### Asset Manager + GitHub (Phases 11A–11F, 2026-05-15) ✅

Founder-contributed context layer. Files (PDF, markdown, code, CSV, images), URLs, and a linked GitHub repo flow into per-project digests that Maya reads as part of her prompt — not a sub-agent, not a tool she invokes. Driving principle: Maya stays dynamic, no hardcoded `entry_type` enums; she figures out the situation from chat + the attached context.

| # | Phase | Status |
|---|---|---|
| 11A | **Schema + asset service + ingestors framework** — 3 new tables (project_assets, github_connections, project_repo_links); 5 typed ingestors (text/pdf/code/csv/image) routing via mime-type detection; per-asset 3000 token cap | ✅ |
| 11B | **Maya context layer integration** — `asset_svc.load_digests_for_maya()` builds the "Project context layer" block prepended as SystemMessage per turn; 8000 token total budget, newest-first packing, truncation footer | ✅ |
| 11C | **File upload UI + endpoint** — `POST /projects/{pid}/assets` multipart upload (10 MB cap); fire-and-forget ingestion via `asyncio.create_task`; paperclip + drag-drop in ChatPanel; asset chips with live status (pending/processing/ready/error) auto-polled every 4s | ✅ |
| 11D | **GitHub OAuth + repo ingestion** — Fernet-encrypted access tokens; `RepoIngestor` produces a digest from tree summary + 4 priority files (README, package.json, etc.); upsert semantics on re-connect | ✅ |
| 11E | **Settings page + repo linking** — `/settings` route, GitHub connection card, per-project repo picker with live status; cog icon in sidebar to access | ✅ |
| 11F | **Polish + tests + docs** — Maya prompt teaches her about the context layer (no theatrical "let me check your files"); .env.example updated; full test suite 78/78 green | ✅ |

**Maya's prompt now teaches:** the asset manager is a **layer**, not a teammate. She reads digests as background like a PRD section; she does NOT say *"let me look at your uploaded files"*. When the founder attaches something mid-conversation, the next-turn digest is just there. If a key file is missing from the repo digest, she calls it out and asks the founder to attach it or have the coding agent share it via MCP.

---

## Schema state

### Untouched core (from earlier phases)
`projects` (+ project_brief, north_star), `prds`, `prd_sections`, `sprints` (+ tech_stack, data_models, repo_layout, conventions, existing_files), `tasks` (+ tech_decisions, data_contracts, verification, pitfalls, complexity, secrets_required, refs, prompt_brief), `decisions`, `messages`, `clarifications`.

### Built by the Dynamic Artifacts migration (`20260514_000001_dynamic_artifacts.sql`)

```
agent_runs (rebuilt — clean break from telemetry-only schema)
  id, project_id, agent_name, invoked_by,
  query, query_hash,                 -- dedup key (sha256, 24h freshness window)
  status,                            -- agent_run_status_enum: running|complete|error|clarification_needed
  output_payload (jsonb),            -- {render_kind, payload, finding, bullets, sources, confidence, clarifying_question}
  error_text,
  message_id,                        -- FK → messages (chat replay)
  tokens_in, tokens_out, cost_usd, duration_ms,
  started_at, ended_at

research_artifacts (new)
  id, project_id, title, summary,
  render_kind,                       -- enum: text|table|matrix|bar_chart|line_chart|graph|persona_cards|stack_diagram
  payload (jsonb),                   -- shape depends on render_kind
  source_run_ids (uuid[]),           -- provenance: which agent_runs fed this card
  created_by,                        -- enum: maya_pinned | maya_synthesized
  created_at, updated_at, deleted_at -- soft delete (chat history may still reference)
```

### Dropped
`research` table, `research_category_enum`, `research_status_enum`, `_STALENESS_MAP`, `mark_stale_by_category`, `find_fresh_research`, `save_research`, `research_to_agent_output`, `apiRefreshResearch` (frontend), Refresh button + RotateCcw imports.

---

## Per-agent model tiers ([_tiers.py](apps/api/app/agents/_tiers.py))

| Agent | Model | Thinking | Why |
|---|---|---|---|
| Maya (orchestrator) | `gemini-3.1-pro-preview` | OFF | Reliable structured tool-call dispatch via LangChain `bind_tools` |
| Theo (Tech Advisor) | `gemini-3.1-pro-preview` | HIGH | Engineering judgment |
| Kai (Sprint Planner) | `gemini-3.1-pro-preview` | HIGH | Sprint breakdown w/ enriched task fields |
| Nora (PRD Writer) | `gemini-3.1-pro-preview` | MEDIUM | Synthesis of canonical artifact |
| Hugo (Risk Researcher) | `gemini-3.1-pro-preview` | MEDIUM | Pattern recognition across failure modes |
| Iris (Problem Validator) | `gemini-3-flash-preview` | — | Web-bound evidence gathering |
| Aiden (Competitor Mapper) | `gemini-3-flash-preview` | — | Web-bound landscape mapping |
| Zara (User Researcher) | `gemini-3-flash-preview` | — | Persona formulation |
| Wes (Guardrail Compiler) | `gemini-3-flash-preview` | — | One-line "do not" rules from existing research |

---

## Maya's tool surface (15 total)

| Family | Tools |
|---|---|
| Research sub-agents | `invoke_iris`, `invoke_aiden`, `invoke_hugo`, `invoke_zara`, `invoke_theo` |
| PRD | `invoke_nora`, `update_prd_section` |
| Sprint | `invoke_kai`, `update_sprint_with_diff` |
| Guardrails / decisions | `invoke_wes`, `log_decision` |
| **Dashboard curation** | **`pin_artifact`, `create_artifact`, `update_artifact`, `delete_artifact`** |

---

## Test surface

| File | Tests | Coverage | Status |
|---|---|---|---|
| `test_imports.py` | 4 | Routes registered, agents import, tools registered, prompts load | ✅ |
| `test_maya_session.py` | 5 | LangGraph orchestration; pin_artifact artifact_hint; project context layer (asset digests as SystemMessage); empty-context skip | ✅ |
| `test_edge_cases.py` | 8 | Auth failures; security headers; X-Request-Id; Maya recovers from sub-agent error payload; agent_runner JSON coercion + budget enforcement; cross-user 404 | ✅ |
| `test_dynamic_artifacts.py` | 23 | Service: pin/create/update/delete + soft-delete + render_kind coercion + cross-project enforcement. Maya tools return structured `{status: ok\|error}` JSON. | ✅ |
| `test_asset_ingestors.py` | 16 | Each ingestor (text/pdf/code/csv/image) with fixture inputs; token cap enforcement; mime-type routing; image ingestor mocks Vertex | ✅ |
| `test_assets_service.py` | 14 | Dispatcher routing (5 types + fallback); CRUD; soft-delete; end-to-end inline ingest pending→processing→ready; error path | ✅ |
| `test_github_client.py` | 8 | Fernet round-trip; OAuth code exchange (mocked HTTP); save_connection upsert; repo digest builder; error path | ✅ |
| `test_smoke_live.py` | 2 | Real Supabase: temp user, login, project CRUD, RLS scoping | live-only |
| `test_agentic_e2e.py` | 2 | Real Maya greeting + meal-tracking prompt → parallel sub-agent dispatch → asserts against agent_runs | live-only |
| `test_dummy_coding_agent.py` | 4 | Dummy MCP coding agent — full tool surface incl. `request_clarification` | live-only |

**Unit + integration (offline):** **78 / 78 passing in 52s.**

---

## Build outputs (production)

**Web** (`pnpm build`):
- `index.html` — 0.89 KB / 0.46 KB gzip
- `index-*.js` — 162 KB / 44 KB gzip (main app — slightly larger now: Settings + GithubCallback pages + asset UI)
- `recharts-*.js` — 515 KB / 155 KB gzip (lazy-loaded vendor chunk for charts)
- `supabase-*.js` — 207 KB / 53 KB gzip (Supabase client)
- `markdown-*.js` — 165 KB / 50 KB gzip (markdown rendering)
- `index-*.css` — 49 KB / 9 KB gzip
- **Initial page load: ~152 KB gzipped.** No chunk-size warnings.

**API** (`uvicorn main:app`):
- 36 routes registered on cold start (24 prior + 8 asset/integration routes).

**MCP** (`apps/mcp/server.py`):
- 11 tools registered.


---

## Live infrastructure setup notes

| | |
|---|---|
| Supabase URL | https://sghdrmmceovqzrjtouej.supabase.co |
| GCP project | `project-edf64ffe-6f3d-4e13-979` (gcloud authed as `instakreate@gmail.com`) |
| Vertex location | `global` |
| Firecrawl | key in `.env` |
| `.env` (root) + `apps/web/.env` | written, working |
| Web dev server | `pnpm dev:web` → http://localhost:5176 |
| API dev server | `uvicorn main:app --reload` → http://localhost:8000 |
| MCP server | `python apps/mcp/server.py` → http://localhost:8765 |

---

## New environment variables (Asset Manager)

| Var | Purpose | Required? |
|---|---|---|
| `GITHUB_OAUTH_CLIENT_ID` | GitHub OAuth App client ID | Optional (feature disabled if blank) |
| `GITHUB_OAUTH_CLIENT_SECRET` | GitHub OAuth App secret | Optional |
| `GITHUB_OAUTH_REDIRECT_URI` | Callback URL on the web app | Defaults to `http://localhost:5176/integrations/github/callback` |
| `ASSET_ENCRYPTION_KEY` | Fernet key for at-rest token encryption (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`) | Optional in dev (plaintext fallback); **required in production** |

To enable GitHub integration: register an OAuth App at https://github.com/settings/developers, set the callback URL, paste the credentials into `.env`, restart the API.

---

## v2 items (out of scope for current build)

These are deliberately deferred — none block production use, but each is worth considering for the next iteration.

- **Chat replay of sub-agent runs.** On page reload, `/maya/messages` rehydrates chat text only — `agent_runs` aren't replayed inline. Means a returning founder sees Maya's prose but not the table/chart she rendered in the agent-call card. Fix: bundle `agent_runs` (filtered by `message_id`) into the messages hydration response, and have `useMayaSession.start()` reconstruct AgentCallEntry items from them.
- **Per-project MCP keys.** Today the MCP server takes the user's Supabase JWT; a `mcp_keys` table + project-scoped tokens issued from web UI is cleaner.
- **Supabase Realtime in web + CLI.** Web hook patches state on Maya SSE event hints; CLI polls every 10s. Realtime subscriptions on `prds`, `tasks`, `decisions`, `research_artifacts` would make the cross-window experience snappier.
- **Token-streaming Maya text.** Currently emits one `message` event per assistant turn. LangGraph supports it via `on_chat_model_stream`; the chat hook needs to consume `text_delta` events that already fire.
- **`agent_runs` cost dashboard.** Telemetry is now richer (per-run tokens + cost_usd + duration_ms); nothing reads it back yet. Worth a small admin view.
- **Coding agent permissions enforcement.** The MCP surface has no server-side check that the agent can't (e.g.) edit the PRD. Today there's no PRD-edit MCP tool, so it's enforced by absence — but a denylist on the server is more robust.
- **Web app pages still empty:** Settings, Project deletion confirmation modal, MCP setup screen.
- **LangGraph deprecation warning.** `JsonPlusSerializer` import will deprecate `allowed_objects` default — single-line fix when the next LangGraph release lands.

---

## File map (current, as of 2026-05-15)

```
ProductSense/
├── PROGRESS.md                              ← this file
├── README.md
├── package.json (workspaces)
├── pnpm-workspace.yaml
├── .env.example
├── docs/
│   ├── ARCHITECTURE.md, AGENTS.md, MCP.md, DESIGN.md
├── packages/
│   ├── prompts/
│   │   ├── maya.md                          ← updated with curation rules + dashboard ownership
│   │   ├── _contract.md, _dialog_rules.md
│   │   ├── iris.md, aiden.md, hugo.md, zara.md, theo.md
│   │   └── nora.md, kai.md, wes.md
│   └── shared-types/                        (still empty — types are inline)
├── supabase/
│   └── migrations/
│       ├── 20260505_000001_init.sql
│       ├── 20260505_000002_rls.sql
│       ├── 20260510_000001_enrich_for_coding_agents.sql
│       └── 20260514_000001_dynamic_artifacts.sql
└── apps/
    ├── api/
    │   ├── main.py
    │   ├── pyproject.toml
    │   ├── tests/
    │   │   ├── conftest.py
    │   │   ├── test_imports.py
    │   │   ├── test_edge_cases.py
    │   │   ├── test_maya_session.py
    │   │   ├── test_dynamic_artifacts.py    ← new (23 tests)
    │   │   ├── test_smoke_live.py
    │   │   ├── test_agentic_e2e.py
    │   │   └── test_dummy_coding_agent.py
    │   └── app/
    │       ├── config.py, db.py, middleware.py
    │       ├── routes/                       (health, projects, maya, artifacts, mcp_proxy)
    │       ├── services/
    │       │   ├── auth, projects, gemini, prompts, messages
    │       │   ├── maya (LangGraph driver), maya_graph, maya_tools_lc
    │       │   ├── maya_tools, maya_clarify (legacy clarify path)
    │       │   ├── agent_runner (rebuilt for agent_runs schema)
    │       │   ├── research_artifacts        ← new service
    │       │   ├── firecrawl, artifacts
    │       └── agents/
    │           ├── _runs.py                  ← replaces _research_helpers.py
    │           ├── _tiers.py
    │           ├── iris, aiden, hugo, zara, theo, nora, kai, wes
    ├── mcp/
    │   ├── server.py                         ← FastMCP, 11 tools — coding-agent bridge
    │   └── pyproject.toml
    └── web/
        ├── package.json                      (+ recharts)
        ├── vite.config.ts                    ← updated: manualChunks for recharts/markdown/supabase
        └── src/
            ├── App.tsx, main.tsx
            ├── context/AuthContext
            ├── hooks/                        (useMayaSession, useProjectArtifacts)
            ├── lib/                          (api, supabase, utils)
            ├── pages/                        (Login, Index)
            └── components/
                ├── ChatPanel.tsx             ← AgentCallCard renders via ArtifactRenderer; CompactToolChip; "Pinned ✓" badge
                ├── ResearchTab.tsx           ← rewritten for ResearchArtifact + ArtifactRenderer
                ├── PrdViewer.tsx, SprintBoard.tsx (+ "Add to chat" on task cards)
                ├── DecisionsTab.tsx, RightPanel.tsx, Sidebar.tsx
                └── artifacts/                ← new
                    ├── ArtifactRenderer.tsx
                    ├── TextCard.tsx, TableCard.tsx, MatrixCard.tsx
                    ├── BarChartCard.tsx, LineChartCard.tsx, GraphCard.tsx
                    ├── PersonaCardsCard.tsx, StackDiagramCard.tsx
                    ├── types.ts              ← defensive payload validators
                    └── index.ts              ← barrel export
```
