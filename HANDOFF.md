# ProductSense — Handoff to next chat

Paste this entire file (or read it from the path above) into a fresh chat to spin up with full context. Last updated end-of-session `2026-05-18` — **discovery flow v2 redesign Phases A+B+C complete; Phase D (end-to-end verification) pending. See section 11.**

---

## 1. What this product is

**ProductSense** is an AI product manager called Maya that helps non-technical founders build products with a coding agent (Claude Code / Cursor / Lovable). She runs the entire product-discovery → spec → sprint flow:

- **Discovery**: 5-layer scaffold (problem reality → people/ICP → competitive context → friction/seeking → tech feasibility), enforced structurally
- **Spec output**: PRD (via Nora) + sprint backlog (via Kai) + guardrails (founder-approved drafts via Wes) + UX wireframe flows (via `wireframe_flow` artifacts)
- **Research surface**: 5 sub-agents (Iris/Aiden/Hugo/Zara/Theo) for problem validation, competitor mapping, failure modes, persona research, and tech feasibility — each is a real persona with skepticism habits, mandatory citation rules
- **Quality gates**: `verify` tool for grounded Gemini fact-checks; tool wrappers enforce source counts on verifiable claims; Nora refuses to draft until all 5 discovery layers are covered AND no unaddressed low-confidence sub-agent runs remain

The coding agent reads the resulting PRD + sprint + guardrails + Screens via an MCP server and builds. Maya's whole purpose is to make sure they can build without needing to ask the founder product questions.

---

## 2. Repo layout

```
C:\Majortom\Proojects\ProductSense\
├── apps/
│   ├── api/                       FastAPI + LangGraph backend
│   │   ├── app/
│   │   │   ├── services/          Most of the orchestration logic
│   │   │   │   ├── maya.py        SSE session driver, emits chat events
│   │   │   │   ├── maya_graph.py  LangGraph orchestrator + context compression + project_state injection
│   │   │   │   ├── maya_tools_lc.py  All Maya tools (StructuredTool registrations + runtimes)
│   │   │   │   ├── agent_runner.py    Sub-agent loop (Firecrawl + Gemini)
│   │   │   │   ├── agent_runs_store.py Read helpers for agent_runs table
│   │   │   │   ├── artifacts.py   PRD/sprint/task/decision writes
│   │   │   │   ├── research_artifacts.py  Maya-curated Research cards
│   │   │   │   ├── discovery_state.py  5-layer scaffold tracking (NEW)
│   │   │   │   ├── followup_state.py   Low-confidence run detection (NEW)
│   │   │   │   ├── gemini.py      Vertex AI wrapper + grounded_search
│   │   │   │   └── ...
│   │   │   ├── agents/            Per-sub-agent files (iris.py, theo.py, etc.)
│   │   │   ├── routes/            FastAPI route handlers
│   │   │   └── db.py
│   │   └── main.py
│   ├── web/                       React + Vite + shadcn frontend
│   │   ├── src/
│   │   │   ├── components/
│   │   │   │   ├── ChatPanel.tsx  Main chat surface
│   │   │   │   ├── RightPanel.tsx Workspace tabs (Research/Screens/PRD/Decisions/Guardrails/Sprint)
│   │   │   │   ├── ScreensTab.tsx Top-tabs + detail layout for wireframe flows
│   │   │   │   └── artifacts/     Renderers for each render_kind
│   │   │   │       ├── WireframeFlowCard.tsx
│   │   │   │       ├── MermaidCard.tsx
│   │   │   │       └── wireframe-template.ts  (Mid-fi CSS + icon library)
│   │   │   ├── hooks/
│   │   │   │   ├── useMayaSession.ts    SSE event reducer + delta queue
│   │   │   │   └── useProjectArtifacts.ts  Dashboard data
│   │   │   ├── pages/Index.tsx    Main shell + collapse buttons
│   │   │   └── lib/api.ts         API client + shared types
│   └── mcp/                       FastMCP server for coding-agent integration
├── packages/prompts/              The agent prompts (md files)
│   ├── maya.md                    THE BIG ONE — orchestrator behaviour
│   ├── iris.md, aiden.md, hugo.md, zara.md, theo.md   Sub-agent personas
│   ├── nora.md                    PRD writer
│   ├── kai.md                     Sprint planner
│   └── wes.md                     Guardrail proposer
└── supabase/migrations/           Schema (apply via Supabase MCP)
```

---

## 3. How to run

**Backend** (uvicorn with hot-reload watching both code AND prompt files):
```bash
cd C:\Majortom\Proojects\ProductSense\apps\api
PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 python -u -X utf8 -m uvicorn main:app \
  --host 0.0.0.0 --port 8000 --reload \
  --reload-dir . --reload-dir ../../packages/prompts > /tmp/api.log 2>&1
```

**Frontend** (Vite, port 5176):
```bash
cd C:\Majortom\Proojects\ProductSense\apps\web
pnpm dev > /tmp/web.log 2>&1
```

**Host gotcha**: must use `0.0.0.0` not `127.0.0.1` (Windows IPv6 quirk; `curl localhost:8000` fails on 127.0.0.1).

**Health probe**: `curl -s http://127.0.0.1:8000/health` returns `{status: "ok", code_revision: {...}}`. If `stale_research_helpers_loaded: true` something is wrong.

**Kill servers cleanly**:
```bash
cmd //c "taskkill /F /IM python.exe"
cmd //c "taskkill /F /IM node.exe"
```

**Hot reload covers**: backend code, prompt edits. NOT: migrations (apply via Supabase MCP), Vite config.

---

## 4. Architecture at a glance — what makes this system specific

**Maya orchestration**: LangGraph with `bind_tools` (ChatVertexAI on Gemini 3 Pro Preview). Every Maya turn:
1. `maya_graph._project_state_block(project_id)` builds a markdown summary of CURRENT state (discovery layers, decisions, research artifact IDs, wireframe flows, flagged runs) — prepended to the system prompt
2. `_compress_tool_messages` rewrites ToolMessages older than 2 user turns to compact markers (full payload stays in `agent_runs`; Maya re-expands via `read_artifact(run_id)`)
3. LLM call → returns AIMessage (with or without tool_calls)
4. If tool_calls: ToolNode dispatches in parallel, loops back to maya_node
5. If no tool_calls: turn ends, final message emitted via SSE

**SSE events** (in `apps/api/app/services/maya.py`):
- `message` — Maya's text. Carries `awaiting_input: false` for preambles, `true` for final
- `text_delta` — token streaming (reserved, not used)
- `thinking` — Maya's reasoning trace
- `agent_start` / `agent_result` — sub-agent dispatch lifecycle
- `artifact_hint` — emitted after any mutating tool. For research+decisions, carries the FULL new row inline (`op: upsert|delete|upsert_batch`, `id`, `item`) so frontend merges directly without refetch

**Frontend dashboard**:
- `useMayaSession` — SSE event reducer, queue-backed `artifactDeltas` (survives bursty events)
- `useProjectArtifacts` — dashboard data + `mergeArtifact`, `mergeDecision`, `mergeDecisionsBatch` for inline-delta merging
- `Index.tsx` — drains delta queue per artifact_hint, falls back to refetch when no delta

**Discovery gate flow** (the structural enforcement):
1. Maya works through layers (1=problem reality, 2=people, 3=competitive, 4=friction, 5=tech)
2. Calls `mark_layer_covered(layer=N, rationale, evidence_run_ids?)` as she's done with each
3. Founder can `waive_layer(layer=N, why)` for skips (Maya should not waive on her own)
4. `invoke_nora` refuses with `status='needs_more_discovery'` if any layer is unhandled
5. `invoke_nora` ALSO refuses with `status='needs_followup'` if any sub-agent run has thin sources / low confidence / `needs_sources` flag AND hasn't been addressed (by a verify call or a re-dispatch with `previous_run_id`)

**Wireframe research linkage**:
- `wireframe_flow` payload supports `informed_by: [research_artifact_id, ...]` (flow-level) and `screens[].derived_from: string` (per-screen prose)
- Renderer surfaces them as chips/footers
- Maya's prompt strongly encourages both

---

## 5. What just shipped this session (the 8 fixes)

| # | Fix | What it does |
|---|---|---|
| 1 | Pin race queue | Parallel artifact pins survive React batching via ref-backed queue |
| 2 | Decisions inline | Same inline-delta pattern as research; no PostgREST race for newly-logged decisions |
| 3 | Verify telemetry + label | Verify writes an `agent_runs` row (rehydrates on reload, has run_id); chat label is "Fact-checking · Result:" not "Sub-agent replied" |
| 4 | Decision-aware generation | `project_state_block` prepended to every Maya turn — active decisions / research IDs / wireframe IDs / flagged runs |
| 5 | Wireframe dedup gate | `create_artifact(render_kind='wireframe_flow')` checks token-overlap against existing flow names; demotes to `needs_update` if duplicate |
| 6 | Discovery state | New `projects.discovery_state` jsonb + `discovery_state.py` service + `mark_layer_covered` + `waive_layer` + Nora gate |
| 7 | Follow-up gate | `followup_state.py` flags low-confidence runs; Nora refuses if any unaddressed |
| 8 | Context compression + `read_artifact` | Older ToolMessages compressed to markers (run_id preserved); `read_artifact(run_id)` for expand-on-demand |

**All migrations applied to live Supabase** via the Supabase MCP. Latest: `20260518_000001_projects_discovery_state`.

---

## 6. Conventions to honor

- **Clean architecture, no patch-ups.** When fixing something, look for the structural cause and fix it there. Examples of past patch-ups we've intentionally avoided: cron-job to clean dupes (we put dedup gates in tool wrappers), client-side filtering for stale rows (we used supersession columns), delay-then-retry (we inlined data in SSEs).
- **No rigid pipelines.** Maya's discovery flow is a SCAFFOLD she reasons against, not a checklist. The 5-layer model + top-3-killers principle replaced an earlier 10-item dimension checklist explicitly because checklists were too rigid.
- **No hardcoded examples.** Prompts have meta-rule "examples illustrate shape, not content" — when Maya is testing on (say) the alarm-app domain, prompts should never reference debate-app or alarm-app specifically.
- **"v1" → always "MVP".** Founder-facing copy, decision titles, PRD sections, prompts — never use "v1" for the first ship.
- **Sub-agents are EXPERTS with skepticism, not search wrappers.** Each has a real persona (Theo as "15-year platform engineer who distrusts marketing pages", Hugo as "startup postmortem archeologist", etc.) and is REQUIRED to cite sources or say "I don't know". Never fabricate.
- **Maya can't quote unverified.** Every load-bearing claim (number, version, vendor) must be verified via `verify` tool OR re-dispatched with `previous_run_id`. This is structurally enforced for Nora drafts.
- **Decisions feed back into reasoning.** The project_state injection means Maya literally sees current decisions on every turn — she can't accidentally draw a wireframe contradicting a logged decision.
- **Wireframes are mid-fi**, not Balsamiq-style and not Figma-style. Greyscale, real icons, rounded corners. The aesthetic is deliberate (see `wireframe-template.ts`).

---

## 7. Tools available in the chat environment

- **Supabase MCP** — direct SQL access to the live DB. Project ID: `sghdrmmceovqzrjtouej`. Use `mcp__16ca8b08-9e6b-48df-9469-b8bf707d2813__execute_sql` for diagnostics, `_apply_migration` for schema changes, `_get_advisors` after DDL.
- **Web search + fetch** (`WebSearch`, `WebFetch`) for researching libraries, current API specs, etc.
- **Explore agents** — for read-only codebase investigation (don't have them write code; just explore)
- **Plan agents** — for designing implementation plans before coding

---

## 8. How I (the user) like to work

- **Diagnose from live data, not from screenshots alone.** Before proposing fixes, pull the actual DB state via Supabase MCP.
- **Lay out trade-offs explicitly** before coding. Ask 2-4 sharp decision questions before executing a substantial change, then ship.
- **Be opinionated**. When asked for a recommendation, give one — don't equivocate.
- **Plain English, no jargon dumps.** I'm a non-technical founder; explain in flowing prose with concrete examples. When I say "I don't understand", that's literal — re-explain plainly.
- **Surface real failures + scorer bugs separately.** Don't blame Maya for what was actually a harness/scoring artefact, and vice versa.
- **Honor explicit user decisions.** If I said "skip workspace-only mode", don't re-add it. If I said "replace the 10-item checklist", don't keep it as a side reference.
- **Track work with TodoWrite** for multi-step tasks. Mark items in-progress / completed in real time.

---

## 9. Known concerns / open items to watch for

- **Compression hasn't been tested end-to-end in a real long session yet.** Logic verified in a smoke test but not in a live conversation. If Maya seems to lose track of older context, check `_compress_tool_messages` behaviour in `maya_graph.py`.
- **`read_artifact` is brand new** — Maya hasn't been observed using it. If long sessions break because she can't recall an older finding, the prompt might need stronger nudges toward calling it.
- **Discovery-state UI** — there's no founder-facing visualization of layer status yet. It's currently visible only via Maya's prose. If you want a 5-dot indicator on the dashboard, that's an open work item (Plan #6 mentioned a dashboard surface; we shipped the data layer + Maya-side, skipped the UI).
- **The "previous test run" issues** that triggered the last fix round were on project `c25844bd-671b-4539-8992-5c7288adeb2b` (Untitled project 12). Pull it via Supabase MCP for diagnostic baseline.
- **No follow-up-gate on `log_decision` yet** (only on `invoke_nora`). If thin-sourced research is being baked into individual decisions, extend `_log_decision` with the same `fu_svc.has_unaddressed_flags` check.

---

## 11. Discovery flow v2 — current status (read first)

### TL;DR — where things stand 2026-05-19

- **12-stage state machine live + code-enforced.** Maya cannot skip stages; sub-agent evidence is required to confirm each one.
- **Founder-approval gate live.** Every state-mutating tool requires a `founder_quote: str` that the server verifies against recent user messages — autonomous mutations are structurally impossible.
- **Decision dedup gate live.** `log_decision` refuses near-duplicate titles unless `supersedes` is set.
- **State block is directive** — every Maya turn ends with an explicit "Required next action" naming the exact tool to call.
- **Verify is a slim expandable chip**, not a full sub-agent card.
- **Diagnostic visibility just shipped (2026-05-19 15:22 UTC):** all sub-agent failure paths now capture raw model output into `agent_runs.output_payload._diagnostic`. `agent_run_status_enum` extended with `empty_result` + `needs_sources` so cleanup writes succeed.
- **Open issue:** Iris (and possibly other sub-agents) periodically emit un-parseable output that surfaces as "couldn't be parsed" in chat. Root cause unconfirmed — next failure will populate `_diagnostic.raw_text` so cause becomes visible. Probable architectural fix: response_schema enforcement (Pydantic schema as Vertex `response_schema` in a second-pass call after the tool-calling loop) + disable extended thinking for sub-agents. Diagnostic data captured first, then targeted fix.
- **Operational watchout:** uvicorn WatchFiles silently stalls on Windows after the first reload event. After any backend file change, run `grep "WatchFiles detected" /tmp/api.log` — if no recent event for the file, restart per §3.

**Status: Phases A+B+C done; multiple post-launch arch-level rounds shipped.** All code paths for the 12-stage state machine are wired backend→prompts→frontend. System runs a new project through the full flow end-to-end. No old 5-layer API references remain in the codebase.

**Plan file:** `C:\Users\vaish\.claude\plans\1-where-does-the-parallel-bubble.md`

### Why the redesign

Project 13 (alarm-app session, 2026-05-18) exposed structural failures: Maya skipped discovery stages, marked layers covered without evidence, drafted PRD before failure-mode research, produced a 6-task sprint with zero deployment tasks. Root cause: ordering was prompt-only with structural gate only at `invoke_nora`. The redesign replaces the 5-layer scaffold with a 12-stage linear state machine that code refuses to skip.

### The 12 stages

1. `problem_framing` — Iris run + founder confirms problem statement
2. `people_competitive` — Zara + Aiden parallel + founder confirms positioning
3. `tech_feasibility` — Theo (show-stoppers only) + founder ack
4. `friction_failure` — Hugo (expanded: failure modes + user-reported friction) + founder ack
5. `user_stories` — Maya drafts, founder approves, locked as `user_stories` render_kind research_artifact
6. `screens` — one flow at a time, explicit per-flow approval
7. `dev_environment` — NEW: device, coding agent, credits, deploy target, server/serverless, db — stored in `projects.dev_environment` jsonb
8. `spec_lock` — founder recap confirmation
9. `prd_draft` — Nora (10-section template incl. user stories + per-feature acceptance + edge cases + risks)
10. `prd_review` — founder approves PRD
11. `sprint` — Kai (mandatory: setup, build, verify, deploy, first-user smoke)
12. `guardrails` — Wes proposes from Hugo, founder approves

Linear ordering enforced by `discovery_state.can_enter()`. Re-visits to earlier stages cascade downstream stages to `stale` status.

### Phase A shipped

- **Migration `stage_state_redesign_v2` applied.** Hard reset of all 13 prior projects + cascaded data (founder pre-authorized). `projects.discovery_state` renamed to `stage_state`. New columns: `dev_environment` jsonb, `flow_version` text default 'v2'. New enum value `user_stories` on `render_kind_enum`.
- **`discovery_state.py` fully rewritten** (file path retained to minimize import churn) — 12-stage state machine with code-enforced ordering, agent-evidence validation against `agent_runs` (must be complete + sources≥1), stale cascading on re-visit. New API: `get`, `stage_status`, `current_stage`, `can_enter`, `confirm_stage`, `mark_stale`, `mark_in_progress`, `is_ready_to_draft_prd`, `is_ready_to_generate_sprint`.
- **`agent_runner.py` hardening.** Pydantic `SubAgentOutput` schema (in-process validation). Prose-leak detector demotes confidence ≤0.4 when `finding` matches debug-trace patterns ("let's refine", "decisive over comprehensive", excessive length+structure). Replaces leaked monologue with an explicit "malformed answer" note before chat surfaces it. Full traceback logging on top-level exceptions.
- **`gemini.py` `call()`** accepts `response_schema` + `response_mime_type` params (clean addition; available for future two-pass refinement where the final sub-agent turn is schema-enforced after research tools complete).

### Phase B shipped

- **B.1 — `maya_graph._project_state_block` + `maya_tools_lc`.** State block renders the 12-stage timeline with COMPLETE/in-progress/stale markers, surfaces founder-confirmed outputs (problem statement, positioning summary, etc.), and includes stage-specific reminders for `user_stories`/`screens`/`dev_environment`. `maya_tools_lc.py` lost the old `mark_layer_covered` and `waive_layer` tools; gained `confirm_problem_statement`, `confirm_positioning`, `confirm_tech_constraints`, `confirm_friction`, `lock_user_stories`, `confirm_screens_done`, `record_dev_environment`, `confirm_spec`, `confirm_prd`, `mark_stage_stale`. `_invoke_nora` and `_invoke_kai` now gate on `is_ready_to_draft_prd()` and `is_ready_to_generate_sprint()` respectively; success of either marks the matching downstream stage complete automatically. `commit_guardrails` marks stage 12 complete on success. Refusals carry human-readable `finding` text.
- **B.2 — `maya.py` SSE taxonomy.** New `_TOOL_CLASS` dict classifies every tool as `research` | `writer` | `state`. State tools emit a new `state_update` SSE event (slim chip on the frontend); research and writer tools continue emitting `agent_start`/`agent_result` with a `kind` discriminator. Fixes the "Asked mark_layer_covered" sub-agent-card pollution bug.
- **B.3 — `maya.md` rewrite.** "How you work" section replaced with the 12-stage flow including per-stage entry/exit conditions and code-enforced ordering. New "Re-visits and the `mark_stage_stale` tool" section. Discovery-state gate section rewritten around the new 12-stage gate (Nora at 1-8 complete, Kai at 1-10 complete). All old layer language stripped. Generic — no domain examples.
- **B.4 — sub-agent + writer prompts.**
  - `hugo.md` — dual-track: failure modes (postmortem) + user-reported friction (review mining of active competitors). Output tags each pattern `[failure]` or `[friction]`.
  - `theo.md` — stripped "Decisive over comprehensive" leak phrase; replaced with "One default + one alternative." Added "Output discipline" section explicitly forbidding planning prose in the `finding` field.
  - `nora.md` — 10-section template (was 7). New sections: per-feature acceptance criteria, edge cases derived from Hugo, risks & open questions. User stories section renders the locked `user_stories` artifact verbatim.
  - `kai.md` — "Pantry Hub" / "ClerkIQ" product-named project_brief examples replaced with abstract shape templates. New "Mandatory task categories" section: setup, build, verify, deploy (adapted to `projects.dev_environment.deployment_preference`), first-user smoke test. If the sprint output lacks deploy or smoke, the job has failed.
  - `wes.md` — minor: explicitly sources from Hugo's expanded dual-track output (failure modes + user-reported friction).

### Phase C shipped

- **`research_artifacts.py`** — `user_stories` added to `VALID_RENDER_KINDS`. New `upsert_user_stories(project_id, stories, informed_by)` function (one artifact per project; idempotent upsert).
- **`nora.py`** — now reads the locked `user_stories` artifact AND `projects.dev_environment` into its user_msg before calling Gemini. PRD section 4 (user stories) renders the locked stories verbatim with their IDs; section 8 (tech stack) reflects founder dev-environment answers.
- **`kai.py`** — reads `projects.dev_environment` into its user_msg. Deploy + secrets tasks are generated from these answers (not invented).
- **Frontend SSE** — `useMayaSession.ts` has a new `StateUpdateEntry` ChatItem type and a `state_update` event handler. Chips appear inline in the chat stream, between messages, with status colors (gray=ok, amber=stage_refused, rose=error).
- **`ChatPanel.tsx`** — new `StateUpdateChip` component renders state_updates as a slim inline chip (matches the existing "Logging decision" chip aesthetic). The `items.map` has a new `state_update` branch.
- **New `UserStoriesCard.tsx`** — renders the locked user_stories artifact as a list of stories with role/goal/value/acceptance, an "approved" lock chip with date. Registered in `ArtifactRenderer.tsx`. `parseUserStories` added to `types.ts`.

### Phase D — smoke-verified; live e2e pending founder use

Static smoke tests passed end of session 2026-05-18:
- **Backend `/health`** returns OK; uvicorn hot-reload picked up every file edit (discovery_state, agent_runner, gemini, maya_graph, maya_tools_lc, maya, kai, nora) with no traceback. Imports load cleanly.
- **stage_state API** verified via Python smoke: 12 stages registered in canonical order; `STAGE_ORDER['user_stories']` = 5; `REQUIRED_AGENTS['friction_failure']` = `('hugo',)`; `can_enter()` refuses out-of-order calls with human-readable reason; first stage accepts.
- **Maya tool surface** verified: all 10 new stage-confirm tools (`confirm_problem_statement`, `confirm_positioning`, `confirm_tech_constraints`, `confirm_friction`, `lock_user_stories`, `confirm_screens_done`, `record_dev_environment`, `confirm_spec`, `confirm_prd`, `mark_stage_stale`) are registered. Old `mark_layer_covered` + `waive_layer` correctly absent. 28 tools total.
- **Frontend Vite HMR** happy on `ChatPanel.tsx`, `ArtifactRenderer.tsx`, `useMayaSession.ts`, `types.ts`, `UserStoriesCard.tsx` — no compile errors.

**The remaining e2e step is a real session** — the founder creates a new project, walks Maya through the 12 stages, watches stage gates refuse out-of-order calls, and confirms Nora produces a 10-section PRD + Kai produces deploy + first-user-smoke tasks. The 12-step checklist is in the plan file (`C:\Users\vaish\.claude\plans\1-where-based-the-parallel-bubble.md`).

### Post-launch arch-level fix round (2026-05-18, after first live test)

First live session on project `c1e1b0e5...` (Untitled project 1) surfaced three issues. **All three have been re-fixed at the architectural level** (initial round was prompt-only patches; founder pushed back per HANDOFF §6 "Clean architecture, no patch-ups"):

**(a) Truncation detection — code-enforced.** Aiden's response was cut off at the 4000-token cap mid-string, leaving invalid JSON. The fallback path dumped the raw envelope into `finding`, which rendered as JSON syntax in the chat. **Architectural fix:**
- New `gemini.was_max_tokens_truncated(response)` helper inspects `candidate.finish_reason` for `MAX_TOKENS`.
- `agent_runner.run_agent` checks this after every Gemini call. On truncation: breaks the inner loop, skips JSON parsing entirely, returns a clean `AgentOutput(status='empty_result', finding="...ran out of room...")`. The raw envelope can never leak to the chat surface from a truncation.
- Budget also bumped 4000 → 8000 tokens for headroom; the detection is the real fix, the bump is incidental.
- Files: [gemini.py](apps/api/app/services/gemini.py), [agent_runner.py](apps/api/app/services/agent_runner.py)

**(b) Chip ordering — render-layer enforcement.** Maya's state-update chips were landing between sentences of the same paragraph. **Architectural fix:** the chat panel groups items into Maya-turns (boundary = the next user message) and reorders within each turn so all `state_update` chips render AFTER prose + agent_call cards. Maya can split her prose around tool calls all she likes; the render layer enforces the contract. Data in state stays in temporal arrival order (correct for replay/audit); only the rendering is reordered.
- Files: [ChatPanel.tsx](apps/web/src/components/ChatPanel.tsx)

**(c) Founder-approval gate — server-side, code-enforced.** Maya was creating decisions and pinning research cards without founder authorization. **Architectural fix:**
- New service [approval_gate.py](apps/api/app/services/approval_gate.py) with `verify_founder_quote(project_id, founder_quote)` — returns `(ok, reason)`. The quote must be a contiguous substring (case-insensitive, whitespace-normalized) of one of the last 12 user messages, ≥6 chars, ≥2 words. Faking the quote is structurally impossible — the substring check is against actual stored user messages.
- Every state-mutating tool now requires a `founder_quote: str` Pydantic field. `_gate(tool, founder_quote, proposed_action)` helper in [maya_tools_lc.py](apps/api/app/services/maya_tools_lc.py) calls into the gate at the very top of each handler. On refusal: returns standardized `status='needs_founder_approval'` payload with a human-readable next-step message.
- Gated tools: `log_decision`, `pin_artifact`, `create_artifact`, `update_artifact`, `delete_artifact`, `commit_guardrails`, every `confirm_*` (all 6 stage confirmations), `lock_user_stories`, `record_dev_environment`, `mark_stage_stale` — 14 tools total.
- Un-gated (intentional): `verify`, `read_artifact`, all research dispatches (`invoke_iris/aiden/hugo/zara/theo`), writer dispatches (`invoke_nora/kai/wes`). These either have no dashboard side effect or have their own gates (stage-state for Nora/Kai).
- Smoke-tested: no-quote refuses, too-short refuses, single-token refuses, valid-shape against fake project refuses (no recent messages). Live Maya cannot bypass.

The corresponding [maya.md](packages/prompts/maya.md) section was rewritten to **describe the structural contract** ("the server rejects calls that don't match a recent founder quote") rather than ask Maya nicely to follow a rule.

**The pattern this codifies:** Maya proposes in chat → founder replies with affirming words → Maya calls the tool next turn with `founder_quote` = the exact words. The dashboard becomes the founder's authorized spec record, not Maya's autonomous curation.

Anything that fails on the next live session is feedback for another patch round. If Maya cannot find an authorizing quote, the gate's refusal `finding` tells her exactly what to do (ask the founder, then retry next turn).

### Second arch-level round (2026-05-19 03:00 UTC, after second live test)

Live test on project `8d27b24a` exposed that **uvicorn's hot reload had silently stopped** several hours earlier. Only ONE WatchFiles event fired the entire session; ~12 file changes after that never landed in the live process. Result: Maya was still operating on the OLD 5-layer prompt + OLD `discovery_state.py` querying the renamed column. The "column projects.discovery_state does not exist" error, the `mark_layer_covered` calls, the missing approval_gate enforcement — all explained by stale code.

**Restart + 6 architectural fixes shipped:**

1. **uvicorn clean restart.** `taskkill /F /IM python.exe` then fresh launch per HANDOFF §3. Fresh `process_started_at` confirmed. Smoke-tested via Python imports: `mark_layer_covered` gone, `confirm_*` tools present, `founder_quote` required in Pydantic schemas, `approval_gate` loaded, `stage_state` column correct.
2. **Truncation detection in `gemini.grounded_search`** (matches the agent_runner pattern). The verify tool's grounded-search response now short-circuits on MAX_TOKENS — no more half-table dumps. Budget also bumped 1500 → 4096 tokens. [gemini.py](apps/api/app/services/gemini.py).
3. **Verify reclassified as `state` SSE class.** [maya.py](apps/api/app/services/maya.py) `_TOOL_CLASS` now puts `verify` in the state-update class. Frontend `StateUpdateChip` ([ChatPanel.tsx](apps/web/src/components/ChatPanel.tsx)) special-cases verify to be expandable — click chevron to reveal grounded finding + sources inline. Stays unobtrusive in chat flow but the result is still accessible. [useMayaSession.ts](apps/web/src/hooks/useMayaSession.ts) carries the full `result` payload through to the chip.
4. **Three new prompt rules in maya.md**:
   - **When to use `verify` vs sub-agent**: verify is for quick narrow-claim fact-checks (one model version, one pricing tier); sub-agents are for deep domain research. Don't conflate them.
   - **No pre-commit to platforms / stack before stage 7**: tech feasibility (stage 3) is about show-stoppers only. Stack / platform / deploy / db choices belong at stage 7 (`dev_environment`). Maya was assuming iOS / Mac before asking the founder.
   - Plus a clarification on autonomous fact-checking: it's good and expected in deep founder ↔ Maya conversations; the UI renders it as a slim chip so it doesn't dominate.
5. **Theo's "model + service snapshot"** ([theo.md](packages/prompts/theo.md)): a curated reference block listing current Gemini / OpenAI / Anthropic / open-source model names + deploy/db options, with the explicit instruction that **the snapshot may be stale and Theo must verify before recommending**. Founders kept hearing about Gemini 1.5 / 2.0 instead of 3.1 Flash Live; this gives Theo a known-good starting point and forces him to confirm.
6. **Token-overlap dedup gate on `log_decision`** ([maya_tools_lc.py](apps/api/app/services/maya_tools_lc.py)). Same pattern as the existing `wireframe_flow` dedup. If a new decision's title overlaps ≥0.55 with an existing active decision and `supersedes` isn't set, the tool refuses with `status: 'needs_supersede'` + the existing display_id to use. The Gemini 2.0 → 3.1 Flash Live double-log scenario is now structurally prevented.
7. **State-block "Required next action" directive** ([maya_graph.py](apps/api/app/services/maya_graph.py)). Every Maya turn now ends with an explicit per-stage instruction naming the exact tool to call and what to pass. The founder asked *"does she lack a checklist?"* — the checklist (12-stage state machine) existed but was passive; this makes it directive. Each stage has its own next-action text covering dispatch + propose-then-confirm + which `founder_quote` to capture.

**Verified live** via Python imports against the running uvicorn worker:
- `_NEXT_ACTION` block in `maya_graph._project_state_block` ✓
- `needs_supersede` dedup in `_log_decision` ✓
- `was_max_tokens_truncated` check in `grounded_search` ✓
- `verify` reclassified to `state` ✓

**Watch out for the watchfiles silent-stall.** On Windows, uvicorn's WatchFiles reload has stopped picking up changes after the first event in this codebase. Workaround: after any backend file change, manually verify with `grep "WatchFiles detected" /tmp/api.log` — if you see only one or two events covering hours of edits, restart uvicorn. Long-term fix candidates: switch to `--reload-include`/`--reload-exclude` flags, swap to `watchgod`, or add a server-side reload diagnostic endpoint.

### Diagnostic visibility round (2026-05-19 15:22 UTC, in response to Iris truncation killing UX)

Live test surfaced repeated "couldn't be parsed" failures on Iris dispatches. Two stacked bugs were hiding the real cause:

**Bug 1: DB enum rejecting cleanup writes.** `agent_runs.status` enum only accepted `running | complete | error | clarification_needed`. The agent_runner code was emitting `empty_result` on parse failures + truncation, which Postgres rejected with error 22P02. Result: failed sub-agent runs stayed stuck at `status='running'` forever; `output_payload` was never written; no diagnostic data was saved.

**Bug 2: Raw model text discarded on parse failure.** When `_parse_output` failed to parse Gemini's response as JSON, my prior fix surfaced a clean error message to chat but threw away the actual text. So even if Bug 1 were fixed, we'd save an empty payload. Zero diagnostic data either way.

**Fix shipped:**
- Migration `agent_run_status_diagnostic_values` — adds `empty_result` and `needs_sources` to `agent_run_status_enum`. Cleanup writes succeed; rows record the actual outcome.
- [agent_runner.py](apps/api/app/services/agent_runner.py) — all four failure paths (`no_text_returned`, `max_tokens_truncated`, `json_parse_failed`, `empty_envelope`) now capture diagnostic data into `output_payload._diagnostic`:
  - `failure_mode` — which of the four it was
  - `raw_text` — up to 8000 chars of what Gemini actually wrote
  - `raw_text_full_length` — actual length (if huge → truncation; if short → prose contamination)
  - For JSON failures: `parse_error`, `cleaned_head`, `cleaned_tail` for fence-stripper debugging
- Backend restarted cleanly (`process_started_at: 2026-05-19T15:22:40`).

**How to use it:** After the next sub-agent failure, query:
```sql
select id, agent_name, status, output_payload->'_diagnostic' as diag
from agent_runs
where agent_name = 'iris' and status = 'empty_result'
order by started_at desc limit 1;
```
The `failure_mode` + `raw_text` reveal the actual cause in one look. Then apply targeted fix instead of guessing.

**The architecturally correct fix (deferred until diagnostic data lands):**

Even if Iris IS truly truncating, "bump the cap" is a patch. The real architectural fix is **forcing Gemini's output into a structurally bounded shape** via three levers:

1. **Vertex `response_schema` + `response_mime_type='application/json'`** — pass a Pydantic schema with per-field `maxLength` / `maxItems` constraints. Vertex's schema enforcement physically blocks over-generation. The plumbing exists (`gemini.call()` accepts `response_schema`) but isn't wired into sub-agent calls yet.
2. **Two-pass orchestration** — tool-calling loop (research) → final-answer call with NO tools BUT WITH `response_schema`. Schema enforcement and function-calling don't always cooperate in the same Vertex call; the second pass guarantees structured output.
3. **Disable extended thinking for sub-agents** — Theo / Hugo on `_DEEP` tier have `thinking_level="HIGH"`. Thinking tokens count against the output budget invisibly. Sub-agents research (Firecrawl), they don't deep-reason; thinking should be off (or split to a separate budget).

After these: truncation becomes structurally impossible regardless of how verbose the model wants to be. Defer until `_diagnostic.failure_mode` confirms whether truncation is the actual problem or something else (prose contamination, malformed fences, safety filter, etc.).

### Decisions locked this session

- **Hard reset** of existing projects (no migration of old 5-layer state). All 13 prior projects wiped.
- **Verify-tool hardening deferred** to a separate round. The "Gemini 3.1 Flash Live" hallucination scare from project 13 turned out to be a real model that shipped after my training cutoff — verify was correct.
- **No save/resume logic** — founder closes the app, reopens later, DB state persists naturally.
- **System stays generic** — no domain examples in any prompt. Final grep pass on prompts before B/C merge.

### What's intentionally killed from v1

- 5-layer `discovery_state` API (`mark_layer_covered`, `waive_layer`, `covered_layers`, `LAYERS`, `LAYER_LABELS`, `is_ready_to_draft`, `missing_layers`)
- Free-form stage ordering (Maya was free to skip — now code-enforced linear)
- Single `agent_start`/`agent_result` event class for ALL tools (now split into research/writer/state_update)
- Pantry Hub / ClerkIQ product-named examples in `kai.md`

---

## 10. Suggested first prompt for the new chat

> I'm continuing work on **ProductSense** at `C:\Majortom\Proojects\ProductSense`.
>
> Read `HANDOFF.md` at the repo root first — **start with section 11 (TL;DR at the top)** for current architecture state. The v2 12-stage flow + approval_gate + diagnostic visibility are all live. There's one known open issue (Iris truncation root cause pending — `_diagnostic` capture is wired so the next failure will reveal it).
>
> Verify both servers are running:
> - `curl http://127.0.0.1:8000/health` — expect `status: ok` and `stale_research_helpers_loaded: false`
> - `grep "ready in" /tmp/web.log` — expect Vite up on :5176
>
> **Operational watchout:** uvicorn WatchFiles silently stalls on Windows. After any backend file change, before debugging behaviour, check `grep "WatchFiles detected" /tmp/api.log` — if no recent reload event for the file you edited, restart per HANDOFF §3. Treat this as default expectation, not edge case.
>
> What I want to do next is: **[describe what you want]**.

That's the whole prompt. Paste it + your task description into a fresh chat and the next Claude has everything.
