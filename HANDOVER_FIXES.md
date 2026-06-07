# Handover — 11-Phase Fix Plan (post debate-analyzer diagnostic)

**Project root:** `C:\Majortom\Proojects\ProductSense`
**Date authored:** 2026-05-16
**Trigger:** Deep diagnostic of project `87f4b441-9c78-49e5-99f8-a468cafb33f8` (debate analyzer) — pulled DB rows for chat, PRDs, sprints, decisions, research artifacts, agent_runs. Verdict: output is **not** usable for a coding agent yet, and the founder experience over-indexes on PM opinions before scope is locked.

This doc is the canonical to-do list for the next session. Each phase is one PR-sized chunk. Phases are ordered by severity — the first three are blocking bugs; the rest are prompt/behaviour fixes.

---

## Severity legend

- 🔴 **Critical** — output is unusable for the coding agent without this.
- 🟠 **High** — Maya behaves like a noisy junior PM without this.
- 🟡 **Medium** — quality-of-life for founder + coding agent.
- 🔵 **UX** — small polish, but visible every session.

---

## Phase 1 — Block duplicate sprint generation 🔴

**Symptom in debate project:** Two `sprints` rows both titled "Sprint 1: MVP Core" — Kai's `generate_sprint` ran twice with no supersession. 15 tasks split across them; the coding agent reading via MCP can't tell which is canonical.

**Fix:**
- In `apps/api/app/agents/kai.py` → `generate_sprint`: query `artifacts.list_sprints(project_id)`. If any active sprint exists, refuse with `{"status":"error","finding":"Sprint already exists — call update_sprint_with_diff instead."}`.
- In `packages/prompts/maya.md`: add rule under "Sprint planning" — "Generate sprint ONCE per project. Subsequent changes go through `update_sprint_with_diff`. If founder asks to 'redo the sprint', call update_sprint_with_diff with reason='full restructure'."
- In `apps/api/app/services/maya_tools_lc.py`: tighten the `generate_sprint` tool description to "Use ONLY for first sprint. Updates go through update_sprint_with_diff."

**Acceptance:** spinning a project, asking Maya to "redo the sprint" twice yields one sprint row, not two.

---

## Phase 2 — Decision supersession 🔴

**Symptom:** 16 decisions in debate project — Tavily AND Firecrawl both logged as "search provider", never marked as superseded. The coding agent reading the decisions log sees contradictions.

**Fix:**
- Schema migration: `ALTER TABLE decisions ADD COLUMN supersedes uuid REFERENCES decisions(id), ADD COLUMN superseded_at timestamptz, ADD COLUMN superseded_by uuid REFERENCES decisions(id);`
- `apps/api/app/services/decisions.py` → extend `log_decision(...)` with `supersedes: str | None = None`. When provided, set superseded_by/superseded_at on the old row in the same transaction.
- `apps/api/app/services/maya_tools_lc.py` → expose `supersedes` arg on the `log_decision` tool with description "If this decision replaces a prior one (e.g. switching from Tavily → Firecrawl), pass the prior decision's id. Old row stays for audit, new row is canonical."
- `packages/prompts/maya.md` → under "When to log a decision", add: "If the founder changes their mind on something already logged, pass `supersedes=<prior_id>`. Never log a contradicting decision without it."
- `apps/web/src/components/DecisionsTab.tsx` → filter superseded rows by default; add toggle "Show superseded" to reveal them with strikethrough.
- MCP `get_session_context`: return only active decisions.

**Acceptance:** logging two decisions in same category with supersession yields one active row + one superseded row in dashboard.

---

## Phase 3 — PRD section_id drift 🔴

**Symptom:** Debate PRD has THREE rows titled "What we're building it with" (different section_ids). Nora's `update_section` is being called with fresh slug each time instead of resolving to existing section.

**Fix two ways (do both):**
- **Maya side:** When Maya calls `update_prd_section`, the tool should first list current sections (via `artifacts.list_prd_sections`) and pass them in the tool description as enum-ish hint: "Existing section_ids: [overview, target-user, mvp-scope, ...]. Reuse one if matching."
- **Nora side:** In `apps/api/app/agents/nora.py` → `update_section`, before insert, fuzzy-match `section_id` against existing sections (Levenshtein < 3 OR shared keyword > 60%) and reuse the existing id. Log a `synth_run` with `output_summary="merged into existing section X"` when fuzzy-matched.

**Acceptance:** in a project where Maya calls update_section with `tech-stack` then `what-were-building-it-with` then `tech`, all three resolve to one row, version-bumped each time.

---

## Phase 4 — Multi-sprint backlog 🟠

**Symptom:** Debate sprint is one fat "Sprint 1: MVP Core" with 8 tasks bundling auth + capture + diarization + scoring + UI. No notion of "Sprint 2: refinement" or "Sprint 3: polish".

**Fix:** `packages/prompts/kai.md`:
- Add a "Sprint shaping" section: "If MVP scope > 6 tasks, split across 2-3 sprints. Sprint 1 = vertical scaffold + one happy path. Sprint 2 = the differentiator. Sprint 3 = trust & polish. Each sprint is independently shippable."
- Update output shape to allow `"sprints": [...]` (array) instead of `"sprint": {...}`. Migrate Kai's writer to upsert N sprints; current `artifacts.upsert_sprint` already takes name+order so this is additive.
- Update Maya's prompt: "Kai returns N sprints. Pin Sprint 1 to chat by default; other sprints visible in Sprint tab."

**Acceptance:** debate-app-shaped scope produces 2-3 sprints, not one.

---

## Phase 5 — Deployment runtime constraints in breadth gate 🟠

**Symptom:** Debate PRD says "real-time STT during a 30-min debate" but no decision logged about Vercel's 10-min serverless cap or alternatives (Fly.io, Railway, persistent WebSocket).

**Fix:** `packages/prompts/maya.md` → in the 9-dimension breadth checklist, add a 10th dimension: **Deployment runtime constraints** — "If the product needs long-lived connections (WS, SSE > 5min), background jobs, or sub-100ms latency, surface deployment trade-offs (Vercel serverless 10min cap vs Fly/Railway/Render) BEFORE drafting PRD. Log the chosen host as a decision."

**Acceptance:** for a long-running-connection product Maya asks the deploy question before Nora drafts.

---

## Phase 6 — Acknowledge before slow tools 🟠

**Symptom:** Founder asks a question, Maya silently dispatches Theo (10s wait) without saying "let me check with Theo on that — back in a sec." Feels broken.

**Fix:** `packages/prompts/maya.md` → add to "Dispatch etiquette":
> Before invoking a research sub-agent (Iris/Aiden/Hugo/Zara/Theo), say one short sentence acknowledging the question and naming who you're asking. Examples (shape, not content): "Good question — let me ping Theo on STT latency." / "Want me to have Zara map who else does this?" Never dispatch silently when the wait is > 3 seconds.

**Acceptance:** every research dispatch in chat is preceded by a one-liner from Maya.

---

## Phase 7 — Pacing: breadth ≠ turn-1 checklist 🟠

**Symptom:** In debate project, Maya jumped to "let me describe the UI" by turn 2, before the founder confirmed the core mechanic.

**Fix:** `packages/prompts/maya.md` → revise the breadth gate section:
> Breadth is **coverage before PRD**, not a turn-1 checklist. Mirror the founder's pace: if they're still in problem-discovery, stay there. The 10 dimensions are what you must have ANSWERED before calling Nora — not what you must ASK in the first three turns. Drafting the UI sketch before the core mechanic is locked is a failure mode.

Add an explicit anti-pattern callout: "Don't describe the UI in turn 2. Lock the mechanic first."

**Acceptance:** in a fresh project, Maya does not propose UI shape until at least the problem + target user + core mechanic are confirmed.

---

## Phase 8 — Don't draft PRD until scope confirmed 🟠

**Symptom:** Debate project has PRD v1 drafted at turn 4 before key decisions (STT provider, deploy host, scoring approach) were made.

**Fix:** `packages/prompts/maya.md` → in "When to call Nora":
> Nora drafts only when ALL of these are true: (1) founder explicitly says "let's lock this in" / "write it up" / equivalent, OR (2) you have logged decisions on all 10 breadth dimensions AND the founder has confirmed each one in chat. Drafting earlier means rewriting later — and the rewrites stack as ghost sections.

Add: "If unsure, ASK the founder: 'I think we're ready to draft the PRD — want me to call Nora?' Never auto-draft."

**Acceptance:** fresh project, Nora doesn't fire until founder says "ok let's write it up" or equivalent.

---

## Phase 9 — Prune superseded research artifacts 🟡

**Symptom:** Debate dashboard has 2 copies of the Deepgram/Speechmatics comparison (Hugo + Theo both produced one; both pinned).

**Fix:**
- `apps/api/app/services/research_artifacts.py` → add `supersedes` arg to `pin()` and `create()`. When provided, set `status='superseded'` on the old row.
- `packages/prompts/maya.md` → when re-pinning a topic already on the dashboard, pass `supersedes=<old_id>`. Curate, don't accumulate.
- Dashboard query: filter `status='active'` by default; admin toggle to reveal superseded.

**Acceptance:** pinning a second Deepgram-vs-Speechmatics card with `supersedes` hides the old one from the dashboard.

---

## Phase 10 — Hide live indicator when AgentCallCard is visible 🔵

**Symptom:** "Theo · Tech Advisor…" appears TWICE on screen — once as the AgentCallCard (italic dispatch line under Maya), once as the live-streaming block at the bottom of the items list.

**Fix:** `apps/web/src/components/ChatPanel.tsx` → in the live-streaming block at end of items, gate the `{TOOL_PRETTY[activeAgent]}…` indicator: only render if NO `agent_call` item for the same agent is currently in `in_progress` status in the items array. (Track via `items.some(i => i.kind === 'agent_call' && i.agent === activeAgent && i.status === 'in_progress')` — if true, suppress.)

**Acceptance:** during a Theo dispatch only one "Theo · Tech Advisor…" line is on screen.

---

## Phase 11 — Remove guardrails from PRD body 🔵

**Symptom:** Guardrails appear in BOTH the PRD body (auto-rendered §Guardrails section) AND the new Guardrails tab. Duplicate surface.

**Fix:**
- `apps/api/app/services/artifacts.py` → `assemble_prd_with_guardrails()`: stop appending §Guardrails. Rename to `assemble_prd()` and just return body_md as-is.
- Audit all callers (nora.py draft + update_section paths).
- Verify MCP `get_session_context` still surfaces guardrails as a separate top-level field (it does — `decisions where tag='guardrail'`).
- `packages/prompts/nora.md` already says "Do NOT write a Guardrails section" — keep that.

**Acceptance:** PRD tab shows no Guardrails section; Guardrails tab is the only surface; MCP still returns guardrails separately.

---

## Execution order suggestion

1. **DB migrations first** (Phase 2 supersedes column, Phase 9 supersedes args). Run them together against local Supabase before any code changes.
2. **Blocking bugs (1, 2, 3, 11)** in one PR — these unblock the coding agent reading via MCP.
3. **Prompt-only phases (4, 5, 6, 7, 8)** in a second PR — pure `packages/prompts/*.md` edits, no schema risk. Re-run the debate scenario after this to verify behaviour shifts.
4. **Polish (9, 10)** last.

After each phase, smoke-test with a fresh project (not the existing debate one — its DB is contaminated with the bugs we're fixing).

---

## Files most-touched

- `packages/prompts/maya.md` — phases 1, 2, 5, 6, 7, 8, 9
- `packages/prompts/kai.md` — phase 4
- `packages/prompts/nora.md` — phase 11 (verify only)
- `apps/api/app/agents/kai.py` — phase 1
- `apps/api/app/agents/nora.py` — phase 3
- `apps/api/app/services/decisions.py` — phase 2
- `apps/api/app/services/research_artifacts.py` — phase 9
- `apps/api/app/services/artifacts.py` — phases 3, 11
- `apps/api/app/services/maya_tools_lc.py` — phases 1, 2
- `apps/web/src/components/ChatPanel.tsx` — phase 10
- `apps/web/src/components/DecisionsTab.tsx` — phase 2
- `supabase/migrations/` — phases 2, 9 (new files)

---

## Context the next session needs

- Stack: FastAPI + LangGraph + Gemini (Maya orchestration), React/Vite/shadcn frontend, Supabase DB, MCP via FastMCP+Streamable HTTP.
- 8 sub-agents: Iris/Aiden/Hugo/Zara/Theo (research) + Nora/Kai/Wes (synthesis). Per-agent tiers in `apps/api/app/agents/_tiers.py`.
- Debate project (`87f4b441-9c78-49e5-99f8-a468cafb33f8`) is the diagnostic baseline — DO NOT use it to validate fixes (its data is the symptom, not a clean test). Spin a fresh project for validation.
- Servers: backend uvicorn on `0.0.0.0:8000` (NOT 127.0.0.1 due to Windows IPv6), frontend Vite on `:5176`. CORS origins exclude 5173.
- Recent invariants:
  - "v1" → "MVP" everywhere (don't reintroduce "v1" language).
  - "Examples illustrate shape, not content" meta-rule already in maya.md + kai.md — preserve it.
  - Pin to Research requires `metadata` jsonb column (migration `20260516_000001`).
  - `tasks.secrets_setup` jsonb column (migration `20260516_000002`).

---

## Open question for the user before starting

- **Phase 4 (multi-sprint):** does the output shape change `{"sprint": {...}}` → `{"sprints": [...]}` break the MCP contract for coding agents already wired? If yes, support BOTH shapes for one release.
- **Phase 11 (guardrails out of PRD body):** are there any external readers (e.g. the founder's exported PRD markdown) that expect the §Guardrails section? If yes, gate behind a query param `?include_guardrails=true`.
