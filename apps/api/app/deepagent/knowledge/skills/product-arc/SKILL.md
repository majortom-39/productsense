---
name: product-arc
description: The recommended path through product discovery for a non-technical founder — understanding (the problem, who the users are, their current journey and friction, and where it matters: positioning, success signals, riskiest assumptions) then converging and building (solutions, features, an explicit MVP cut, the UX screens, the PRD, guardrails, and an intent-level sprint board). Read this when you need orientation on what to do next, which specialist to call, or what a change ripples into. It is guidance you adapt, never a fixed sequence you must follow.
---

# Product Arc — the discovery playbook

This is the *recommended* way to take a founder from a raw idea to a sprint board
their coding agent can build from. It is a map, not a railway. You decide the
route based on the product and the founder in front of you — skip, reorder, or
loop back whenever the situation calls for it. Your judgment is the point; this
playbook just keeps you oriented.

## The arc

```
UNDERSTAND                                          CONVERGE & BUILD
PROBLEM → USERS → FRICTION → (POSITIONING,    →    SOLUTIONS → FEATURES → MVP CUT
                              SUCCESS, RISKS)        → SCREENS → PRD → GUARDRAILS → SPRINT
```

Two halves. **Understand** is the research a real PM does before proposing
anything — who hurts, how they cope today, what "better" even means. **Converge
& build** turns that understanding into a scoped, spec'd, buildable board. The
first three understand-steps are nearly always worth doing; the bracketed three
are judgment calls — do them when they earn their keep.

**Not every product needs every step.** Read the founder and the idea, pick the
steps that pay for themselves, and skip the rest — but if you skip something
load-bearing, say so and record why (an `open_question` or a one-line note in a
decision). A tiny utility may go problem → solution → MVP; a regulated B2B idea
may need users, friction, risks and guardrails early.

Each step below says: what it's for, which specialist (if any) does the heavy
lifting, what you produce, and what a change here ripples into.

### 1. PROBLEM — is this real and worth solving?
- **Goal:** confirm there's a genuine pain, felt by real people, worth building for.
- **Specialists:** Iris (problem validator); Zara for user texture/quotes.
- **You produce:** a problem artifact (`create_artifact`) stating the pain in
  plain language — *"users forget to mark food as eaten and it goes off"*, not
  *"out-take inefficiency."*
- **Push back here.** If the founder describes a solution before a problem, drag
  them back to the problem. If the pain is thin, say so.
- **Ripples into:** everything downstream. A changed problem destabilises the
  users, friction, solutions, features, MVP, PRD and sprint built on it.

### 2. USERS & SEGMENTS — who exactly is this for?  (usually do this)
- **Goal:** name the real people who feel the pain. Primary user first; note
  secondary users only if they change what you'd build. Vague "everyone" is a
  red flag — push for a sharp primary.
- **Specialist:** Zara (user researcher).
- **You produce:** a users artifact (`create_artifact`, often `persona_cards`)
  `derived_from` the problem — who they are, what they're trying to get done,
  what they care about, in their own words where you have them.
- **Ripples into:** solutions and features (a different primary user reshapes
  both).

### 3. CURRENT JOURNEY & FRICTION — how do they cope today, and where does it break?  (usually do this)
- **Goal:** map how the user solves this *now* (a workaround, a spreadsheet, a
  rival app, nothing) and the exact points where it hurts. This is the "why now /
  why this" evidence — the friction you remove is the value you add.
- **Specialists:** Zara (the lived journey); Hugo (where it fails / costs them).
- **You produce:** a friction artifact (`create_artifact`, e.g. `text` or
  `table` of step → friction) `derived_from` the users and problem.
- **Ripples into:** solutions (each should kill named friction) and the MVP cut
  (cut toward the sharpest friction).

### 4. POSITIONING & WEDGE — how is this different, and where does it land first?  (judgment call)
- **Goal:** if there are alternatives, be honest about how this is meaningfully
  different and the narrow wedge where it wins first. Skip for a private tool
  with no real alternatives.
- **Specialist:** Aiden (competitor mapper).
- **You produce:** a positioning artifact (`create_artifact`, e.g. `matrix` of
  you-vs-alternatives, or `text`) `derived_from` the problem/users.

### 5. SUCCESS CRITERIA — what does "working" look like?  (judgment call)
- **Goal:** agree, in plain language, what outcome means the product is doing its
  job — the signal you'd point to. Keep it to a couple of honest signals, not a
  metrics dashboard.
- **You produce:** a success artifact, or fold it into a decision.
- **Hard rule:** **no time or estimation as a metric.** No deadlines, no "X by
  week N", no story points, no velocity, no effort sizing — those are forbidden
  everywhere the founder sees. Success is an *outcome* signal (e.g. *"a user logs
  a meal without being told how"*), never a schedule.

### 6. RISKIEST ASSUMPTIONS — what must be true for this to work?  (judgment call)
- **Goal:** name the one or two beliefs the whole thing rests on, and which to
  de-risk first. The point is to build the risky thing early, not last.
- **Specialist:** Hugo (risk researcher).
- **You produce:** a risks artifact, or `open_question`s for the founder where a
  belief is theirs to confirm.

### 7. SOLUTIONS — what are the ways to solve it?  (diverge)
- **Goal:** generate more than one candidate way to solve the validated problem,
  with honest trade-offs. There is almost always more than one.
- **You produce:** `create_solution` per candidate, each `derived_from` the
  problem artifact. Mark one `recommended=True` once you have a view.
- **Coach move:** show the founder the trade-offs, then give a recommendation.
  Don't present a menu and go quiet — have an opinion.

### 8. FEATURES — shape the chosen solution into concrete capabilities
- **Goal:** turn the chosen solution(s) into concrete features a builder could act on.
- **You produce:** `create_feature` per feature, each `derived_from` its solution.
  Leave `in_mvp=False` for now — scope happens at the next step, deliberately.

### 9. MVP CUT — ruthlessly cut to the smallest thing that delivers the core value  (converge)
- **This is the heart of the work and where you earn your keep.**
- **Goal:** force an explicit scope decision. Not everything ships in v1.
- **How to run it:** lay out the features, recommend an in/out split with reasons,
  and make the founder *choose*. Refuse "all of it." Be honest about the cost of
  scope.
- **You produce:** a scope **decision** (`log_decision`, `tag="scope"`) whose
  `constrains` list names the features that make the cut. Then mark each kept
  feature with `update_feature(feature_id, in_mvp=True, reason=…)` — and
  `in_mvp=False` for any you drop back out. That in-MVP set is exactly what fills
  the PRD's "what we're building" list, so the cut isn't real until you set it.
  The decision constraining the features is what keeps scope honest later — if the
  cut changes, those features get flagged for review.
- **When the founder must decide, use `ask_founder`.** The MVP cut is exactly the
  kind of choice that needs their brain.

### 10. SCREENS / UX FLOWS — design the screens for the cut  (judgment call; UI products only)
- **Goal:** turn the in-MVP features into the screens and flows the founder — and
  the coding agent — can see. This is the visual half of the spec.
- **When to do it:** products with a real interface. Skip for a CLI, an API, a
  backend automation, or a script — say so and move on. Don't force pixels onto
  something that has no screens.
- **Discuss BEFORE you draw.** First propose the flow in chat: which screens, what
  each screen is *for*, and for every element which feature it serves and which
  friction/pain it removes. Get the founder's sign-off with `ask_founder`. Only
  *then* draw. A button no feature or pain stands behind doesn't belong on the screen.
- **You draw them yourself:** a `create_artifact` with `render_kind="wireframe_flow"`
  (greyscale, mid-fidelity mockups), `derived_from` the in-MVP features + the
  friction/persona cards. Compose each screen from typed **blocks** (heading, text,
  input, button, list, card, hero, metricRow, media, …) plus an optional `appBar`
  and a pinned `bottomBar` — never raw HTML; the renderer owns the layout so screens
  come out clean and consistent. Put primary actions in the `bottomBar`, keep each
  screen to a handful of focused blocks, and use each screen's `derived_from` + the
  flow's `informed_by` to keep the research → UX trail intact. (See the
  create_artifact `wireframe_flow` shape for the full block list.)
- **Ripples into:** the PRD (the screens are what Nora specs around) and the sprint.

### 11. PRD — write the spec for the MVP
- **Goal:** a right-sized spec for the features in the cut. Not a 1,300-line tome.
- **Specialists:** Nora (PRD writer); Theo for tech shape, Hugo for risks, Aiden
  for market/competitors.
- **Brief Nora well:** `gather_context` anchored on the **in-MVP features** (add
  any binding guardrails or the success criteria) and paste the block into her
  task — she's forgetful, so the anchors' trail is how she sees the problem and
  users behind those features.
- **You produce + PERSIST it:** Nora's draft is only chat text until you save it.
  Call `write_prd(body_md)` with the full spec as markdown (use `## ` headings per
  section). That's what populates the PRD tab — the MVP feature list and the
  guardrails are wrapped around your body automatically.
- **Remember the boundary:** you own *what* and *why*. The coding agent owns *how*.
  No data contracts, repo layout, or step-by-step implementation in the PRD.

### 12. GUARDRAILS — compile the non-negotiables
- **Goal:** capture the hard constraints every feature and task must respect —
  *"no user data leaves the EU,"* *"auth is magic-link only,"* *"B2B only."*
- **You compile these yourself — no specialist.** Read the risks + key decisions
  (`gather_context` / `get_node` if you need to re-ground) and write the
  non-negotiables down. The founder confirms them. They surface inside the PRD as
  a Constraints section.
- **You produce:** guardrail decisions (`log_decision`, `tag="guardrail"`). These
  are upstream constraints — `constrains` the features/tasks they bind, so
  changing a guardrail flags everything that inherited it.

### 13. SPRINT — the intent-level board the coding agent picks up
- **Goal:** a backlog of tasks describing intent, not implementation.
- **Specialist:** Kai (sprint planner).
- **Brief Kai well:** `gather_context` anchored on the **PRD sections** (add the
  guardrails so tasks inherit them) — the trail brings the features and why
  behind each section.
- **Each task is a small vertical slice.** The coding agent works from a fixed
  context window and is blind to whatever you leave out — so a task must be
  something it can build AND verify on its own, in one pass. "Add a contact form"
  beats "rebuild the contact page." Keep every task self-contained and
  intent-level.
- **Each task carries (intent only — never the how):**
  - **goal** — the outcome in one line.
  - **why** (in `description`) — the user problem it solves; keeps the agent grounded.
  - **acceptance** — the testable "done" conditions. *This is the single biggest
    quality lever — vague tasks get built wrong.*
  - **verification** — how we'll know it works, in plain language ("a user logs a
    meal without being told how").
  - **do_not** — the non-goals: what this task must not do or touch. Stops the
    agent making sweeping, confident, wrong changes.
  - **prd_context** — which feature / PRD section it serves (traceability).
  - **blocked_by** — its prerequisites; order tasks **bottom-up** so no-dependency
    slices come first and each can be tested as it lands.
  - **prompt_brief** — a self-contained brief the agent can act on without the chat.
  It does **not** carry tech stack, file paths, data shapes, or code design — the
  coding agent owns the *how*, or reads it from the repo. **Guardrails aren't
  copied onto each task** — the agent inherits them from the decisions you logged.
- **You produce + PERSIST it:** Kai's plan is only chat text until you save it.
  Call `create_sprint(name, tasks=[…])` with each task carrying the fields above.
  That's what populates the Sprint tab the coding agent picks up.
- **Then keep it living.** Re-planning is editing, not re-creating. To change the
  board, amend it in place: `add_task` for a new task, `update_task` to revise one
  (content or status), `remove_task` to drop one, `update_sprint` to rename or
  close it. Only call `create_sprint` again to start a genuinely separate next
  sprint — don't recreate the same one.

## Dependencies — what a change ripples into

Wire every node `derived_from` what it came from, so the graph stays coherent:

- problem ← (users, friction, solutions all derive from it)
- users ← (friction and solutions derive from them)
- friction ← (solutions should address named friction)
- solution ← (features derive from it)
- feature ← (screens + PRD sections derive from it); MVP-cut decision **constrains** features
- friction/persona ← (screens derive from them — every element traces to a pain)
- guardrail **constrains** features and tasks
- feature/PRD ← (tasks derive from them)

`derived_from` only accepts refs that **actually exist** — a made-up ref is
rejected, not silently wired. So when you wire to earlier work, get the real ref
first with `list_nodes` / `get_node`; don't reconstruct an id from memory. Run
`list_orphans` now and then to catch anything you created without wiring it back.

When you materially change a node, the system flags its **direct** dependents
`needs_review` and stops there (lazy — it won't repaint the whole graph). Check
`list_open_reviews`, then exercise judgment per flag: re-run a specialist, ask the
founder, or `resolve_review` if there's genuinely no impact. Never ignore a flag.

When something is wrong or obsolete, don't leave it lying around: `archive_node`
to retire it, or `supersede_node` when a newer node replaces it. Both are soft —
nothing is ever destroyed.

## Briefing a specialist (they're forgetful)

A specialist sees **only the task you write** — no chat history, no cards, nothing
else. So before you delegate, especially to the synthesis team (Nora, Kai):

1. `gather_context` with the **anchor** cards the job is about. Anchors can span
   any steps — e.g. anchor Nora on the in-MVP features *and* a binding guardrail.
2. Paste the block it returns into the `task` description, alongside your
   instructions.
3. Delegate.

The trail behind your anchors (problem, users, friction…) comes along
automatically, so the specialist's work is grounded — you don't hand-copy it. The
default anchors above are a starting habit, not a rule: add or drop anchors to fit
the product in front of you.

## How to use this playbook

1. Work out where the founder actually is in the arc — they rarely start at step 1.
2. **Read before you reason.** The database is your real memory — the chat scrolls
   away. Use `list_nodes` to see the whole record and `get_node` to inspect one
   node (with its provenance and dependents) before referencing or editing it.
3. Plan your path with `write_todos`, tailored to *this* product. Revise it as
   discovery changes the picture.
4. Delegate research and drafting to specialists; you synthesise and coach.
5. Record decisions and wire dependencies as you go — coherence is the moat.
6. Adapt freely. Pick the steps that earn their keep and skip the rest; the arc
   serves the product, not the other way round.
