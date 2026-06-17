# Implementation Plan — Artifact Lifecycle + Conversational Maya

> Locked direction from the brainstorm sessions on 2026-05-10.
> Build now, not v2. Decision-logging discipline is parked separately
> for later brainstorm — see BRAINSTORM_NOTES.md.

## Workstream 1 — Section-aware PRD

**Today:** Nora rewrites the whole PRD body each turn (5 versions in 30 min in the
debate-app test). Wasteful; obscures real diffs.

**Target:** Nora can update one named section at a time. PRD versions become
meaningful diffs.

### Changes
1. **Schema:** `prd_sections` table already exists (`prd_id`, `section_id`,
   `title`, `body_md`, `order_index`). Start writing into it. Source of truth
   becomes the section rows; `prds.body_md` becomes a denormalised cache or is
   dropped.
2. **Nora's prompt:** new arg `target_section: str | "all"`. When set, she rewrites
   only that section and returns `{section_id, title, body_md}`. When "all", same
   as today.
3. **Maya's tool surface:** add `update_prd_section(section_id, change_summary)`
   alongside existing `invoke_nora`. Maya picks the right tool based on whether
   the change is local (section) or global (target user shift, scope reset).
4. **Versioning:** every section update writes a new `prds` version row that
   stores either `{kind: "full", body_md}` or
   `{kind: "section_update", section_id, before, after, reason}`. UI renders the
   change-history panel from these.
5. **Guardrails as §section:** Nora's draft includes a `## Guardrails` section
   that pulls live from `decisions where tag='guardrail'`. The section body in
   `prd_sections` is auto-rendered, never hand-written. One source of truth.

**Cost:** ~1.5 days. Big win on chat speed + cost + version legibility.

---

## Workstream 2 — Research lifecycle

**Today:** Research rows are write-once. No staleness, no dedup. Theo ran 3 times
with overlapping briefs in the test session.

**Target:** Research as an evidence ledger that knows when it's outdated and
won't be redundantly re-run.

### Changes
1. **Dedup at runner level:** before invoking a research sub-agent, hash the
   normalised query. If a `research` row with the same hash exists and is
   `fresh`, return it instead of re-running. Maya gets the cached finding with a
   note "(cached from {timestamp})".
2. **Staleness triggers:** when the founder changes a load-bearing answer
   (target user, core feature, scope), all research rows whose `affects` field
   touches the changed PRD section get auto-flipped to `stale`. Surface in UI.
3. **Refresh endpoint:** `POST /v2/.../research/{id}/refresh` — re-invokes the
   originating sub-agent with the original query. New row written; old row
   marked superseded. Wire the "Re-run" button in the UI.
4. **Affects tracking:** when Maya invokes a sub-agent, she passes
   `affects: { prd_sections, decisions, tasks }` so the row can be linked.
   Drives both UI ("Used in" chips) and staleness propagation.

**Cost:** ~1 day. Most of the schema is already there.

---

## Workstream 3 — Sprint as a living artifact

**Today:** Kai generates 8-20 tasks once, then they're frozen. PRD changes don't
flow into the sprint.

**Target:** Sprint stays in sync with PRD. Kai can re-plan in diff mode.

### Changes
1. **Kai diff mode:** new tool `update_sprint_with_diff(prd_section_changed,
   reason)` — Kai reads the PRD change + existing tasks, produces a diff:
   `{added: [], modified: [{display_id, ...}], stale: [display_id]}`. Tasks
   never silently lose data; "stale" surfaces a chip in the UI.
2. **Multi-sprint:** `sprints.number` already exists. Kai plans the next sprint
   when (a) founder asks, or (b) ≥80% of current sprint is `done`.
3. **Task staleness:** `tasks.status` enum gains `stale` (or use a separate
   boolean `is_stale`). Stale tasks render with a "stale — affected by D-014"
   chip linking to the change.
4. **Open decisions on tasks:** already wired in schema (`open_decision_id`).
   Make sure the chip shows in UI. **(Probably already works — verify.)**

**Cost:** ~1.5 days for Kai diff mode. The rest is wiring.

---

## Workstream 4 — Conversational Maya (mechanics)

Already captured in BRAINSTORM_NOTES.md. Pulled in here because it ships in the
same release window.

1. **Honor `clarification_needed` round-trip.** Sub-agents can ask Maya for
   clarification; Maya answers and re-invokes. Cap 2 rounds. _~half day._
2. **Rewrite Maya's prompt** for proposal-first conversational mode.
   Replace "force A/B" rule. Add "have an opinion, then check." _~half day._
3. **"Thinking out loud" idiom.** Maya emits a 1-line thought before any
   sub-agent call expected to take >5s. Prompt change. _~hour._
4. **Sub-agent prompt updates** — invite pushback, allow refinement.
   _~half day across all 8 prompts._
5. **UI for multi-turn agent dialog.** Today: brief → finding card. Target:
   brief → clarifying-Q → answer → finding thread inside the same expandable.
   _~half day._

---

## Workstream 5 — Telemetry fixes (cleanup)

1. `agent_runs.agent` should log the sub-agent name (`theo`, `iris`), not the
   inner tool name (`web_search`). One-line fix in `agent_runner._record_run`.
2. Synthesisers (Nora/Kai/Wes) don't record into `agent_runs` because they call
   `gemini.call` directly. Add a `_record_run` wrapper for them too.
3. Maya's prose still leaks sub-agent names ("I just had Nora…"). Tighten the
   prompt; add anti-examples. The expandable card already shows who ran.

---

## Sequencing

Round 1 (this push): Workstream 5 (cleanup), then Workstream 4 (Maya conversational mode), then Workstream 1 (section-aware Nora).

Round 2: Workstream 2 (research lifecycle) and Workstream 3 (sprint living artifact) in parallel.

---

## Out of scope for this round (parked)

- Decision logging discipline (Maya's "what counts as a decision" rule). Pending separate brainstorm.
- Sprint enrichment for coding-agent context (see SPRINT_BOARD_NOTES.md).
- Real-time updates (Supabase Realtime in web + CLI). Polling is fine for now.
