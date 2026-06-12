# MCP — "Connect your coding agent" plan

> Status: **BUILT (2026-06-11), as the hosted variant.** We went straight to
> Option 2 — a key-authed MCP endpoint mounted at `/mcp` on the API service
> (`app/mcp_remote.py`) — because per-project `ps_live_` keys in a header made
> multi-tenant auth simple WITHOUT OAuth, and it removes the local-install
> problem entirely (we never published a helper package). Everything else
> happened as planned: `mcp_keys` table (hash-only), paste-prompt onboarding
> from the per-project **Agent** button (`AgentControl.tsx`), last-seen
> indicator, agent powers = read + task updates + flagged `add_task` +
> `request_next_sprint` (never creates sprints). `apps/mcp/server.py` remains
> as a local/dev variant. The notes below are the original brainstorm.

## What the MCP is for
ProductSense is the **architect** (it produces the blueprints: sprint board, PRD,
screens). The founder's coding tool (Claude Code / Cursor) is the **builder**. The
MCP is the **phone line between them** so the builder can: pull the next task, mark
tasks done + log files touched, ask Maya a clarifying question, and record
decisions — keeping the product record live instead of a dead printout.

The tools already exist in `apps/mcp/server.py` (it calls the backend API via the
`/projects/{id}/...` mcp_proxy routes). What's missing is **how a founder connects.**

## The decision: local helper first, paste-a-prompt onboarding
Two ways to deliver the connection:
- **Option 1 — local helper (CHOSEN for v1).** A small `productsense-mcp` helper
  runs on the founder's machine; their coding tool launches it. Simple + cheap for
  us, secure (credentials stay local), works in every MCP client. Functionally it
  does **100%** of what the MCP needs — capability is identical to the hosted
  option; only setup convenience differs.
- **Option 2 — hosted link (LATER).** One shared MCP server on Cloud Run that
  founders reach by pasting a URL. Nicer UX, but needs multi-tenancy + real auth
  (per-project keys or OAuth 2.1). Build this only once founders ask for it; the
  underlying tools don't change, so v1 isn't wasted.

### What removes the friction: the Supabase-style paste-prompt
Non-technical founders shouldn't edit config files. So the **"Connect your coding
agent" screen** in the web app gives a **Copy** button that copies a ready-made,
plain-English instruction (with the founder's details already filled in). They
paste it into their coding agent's **chat**, and the agent does the setup itself
(installs the helper, writes the config, connects, pulls the first task). Mirrors
the pattern Supabase/Vercel use.

Example of the copied prompt (illustrative):
> "Set up the ProductSense connection for me. Add an MCP server called
> 'productsense' using `npx productsense-mcp`, with project ID `<id>`, key
> `ps_live_<…>`, and address `<api-url>`. Then confirm it's connected and show me
> my open tasks."

Offer a **raw config snippet** underneath as a fallback for tools that can't
self-configure.

## The three details a connection needs
1. **API address** — where the backend lives (the Cloud Run API URL).
2. **Project ID** — which project's blueprints to talk about.
3. **A personal key** (`ps_live_…`) — proves "this is my project." Long-lived +
   revocable (the founder's Supabase login token expires hourly, so it can't be
   used for a days-long builder connection).

## What we'd build (v1)
1. **Key system** — a `mcp_keys` table in Supabase (store a *hash* of the key →
   project_id, created_at, revoked_at). Backend endpoints to mint + revoke. Keys
   scoped to ONE project and only the MCP tools.
2. **"Connect your coding agent" screen** — generates the key, shows the copy
   prompt + fallback snippet, with regenerate/revoke.
3. **Package the helper** — make `apps/mcp/server.py` runnable as a published
   helper (e.g. `npx productsense-mcp` or a pinned command) that takes the 3
   details and talks to the backend. It's already single-tenant-per-process, which
   fits the local model almost as-is.

## Security must-haves
- Founder never holds the Supabase **service-role** key — only their scoped
  `ps_live_` key.
- Keys are **revocable**, **scoped to one project**, and limited to the MCP tools.
- Keep the Origin check already in `server.py`; rate-limit + log per key.

## Later (v2): hosted link + OAuth
- Make the server multi-tenant (project comes from the request's key/identity, not
  env), host on Cloud Run (`productsense-mcp`), founders paste a URL + key.
- Then add OAuth 2.1 for one-click "Connect" (browser login, no key copy-paste).

## Open questions for when we build
1. Helper distribution: npm (`npx`), pipx, or a small downloadable binary?
2. Exact key format + the `mcp_keys` schema.
3. Which coding tools to officially support first (Claude Code, Cursor) + test the
   paste-prompt against each.
