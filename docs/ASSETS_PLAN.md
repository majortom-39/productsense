# Asset Manager — Implementation Plan

> Founder-contributed context layer. Files, repos, and integrations get summarized into structured digests Maya reads as part of her project context. Not a sub-agent; not a Maya tool; a preprocessing pipeline that runs automatically when something is attached.

**Why:** Maya today only knows what's in chat + the artifacts she's built. Founders showing up half-deep into a build (or shipped, or pivoting) need Maya to be grounded in **what already exists** — codebase, existing PRD, user feedback, screenshots. Without that, advice stays generic.

**Design principle:** Maya is dynamic. No hardcoded entry-type enums. She figures out the situation from conversation + attached context. The asset manager just makes that context available.

---

## Architecture

```
┌─ Founder attaches: file | github repo | URL ─┐
│                                              │
└──────────────► Asset Manager (background) ──┘
                       │
                       ├─ detects type (mime / extension / source kind)
                       ├─ routes to typed ingestor
                       │     ├─ TextIngestor    (md, txt)
                       │     ├─ PdfIngestor     (pdf)
                       │     ├─ ImageIngestor   (png/jpg → Vertex vision caption)
                       │     ├─ CodeIngestor    (py/ts/js/... → structural summary)
                       │     ├─ CsvIngestor     (csv → headers + sample + stats)
                       │     └─ RepoIngestor    (github → tree + key files digest)
                       ├─ caps digest at 3000 tokens
                       └─ stores in project_assets table

┌─ Maya turn ──────────────────────────────────┐
│                                              │
│  System prompt (Maya's main)                 │
│  + Project context layer  ←─── loaded here   │
│      (PRD + decisions + asset digests,       │
│       total capped at 8000 tokens)           │
│  + Conversation history                      │
│                                              │
└──────────────────────────────────────────────┘
```

## Data model

```sql
project_assets
  id, project_id, asset_type ('file'|'repo'|'url'),
  source_kind, source_ref,
  display_name, mime_type, size_bytes,
  status enum ('pending'|'processing'|'ready'|'error'),
  digest_md text,           -- the summary Maya reads
  digest_tokens int,        -- cap-tracked
  metadata jsonb,
  error_text,
  created_at, updated_at, deleted_at

github_connections
  id, user_id (auth.users),
  github_user_login, access_token_enc, scope,
  created_at, updated_at

project_repo_links
  id, project_id, github_connection_id,
  repo_full_name, branch,
  last_synced_at, asset_id (FK project_assets for the digest),
  created_at
```

All RLS-protected. Tokens encrypted at the app layer using Fernet (key in env).

---

## Phase ledger

### Phase 11A — Asset infrastructure
- Migration: `project_assets`, `github_connections`, `project_repo_links` + enums + RLS
- `app/services/assets.py` — CRUD + ingestion dispatcher
- `app/services/ingestors/` framework — base protocol + 5 typed ingestors (text/pdf/image/code/csv)
- Tests: each ingestor with fixture inputs

### Phase 11B — Maya context layer
- Update `maya.py:_handle` to load ready asset digests + prepend as SystemMessage
- Token budget: 8000 tokens total, newest-first ordering
- Tests: digests reach Maya's prompt; budget enforced

### Phase 11C — File upload UI + endpoint
- `POST /projects/{id}/assets` — multipart upload, kicks off background ingestion
- `GET /projects/{id}/assets` — list with status
- `DELETE /projects/{id}/assets/{id}` — soft delete
- ChatPanel paperclip + drag-drop + asset chips with status
- Tests: upload → ingestion → digest available

### Phase 11D — GitHub OAuth + repo ingestion
- Env vars: `GITHUB_OAUTH_CLIENT_ID`, `GITHUB_OAUTH_CLIENT_SECRET`, `ASSET_ENCRYPTION_KEY`
- Routes: `/integrations/github/start`, `/integrations/github/callback`, `/integrations/github/repos`
- Service: `app/services/github_client.py` — REST wrapper
- `RepoIngestor`: tree + README + package files + entry-point detection
- Tests: mock OAuth round-trip + digest generation

### Phase 11E — Settings page + repo linking
- `/settings` route in web app
- GitHub connection card (connect/disconnect/show login)
- Per-project repo link picker
- Asset list per project (view/delete)

### Phase 11F — Polish + final tests + docs
- Full test suite green
- PROGRESS.md updated
- README + ARCHITECTURE.md updated

---

## Token budget rationale

| Surface | Cap | Reasoning |
|---|---|---|
| Single asset digest | 3000 tokens | Big enough for a meaningful summary; small enough that 3-4 fit comfortably |
| Total context layer | 8000 tokens | Leaves ~120K for PRD + conversation + tools on Gemini Pro |
| Repo digest | 3000 tokens | Tree summary + 1-2 key files; full files via MCP if needed |

Newest-first ordering when over budget. If founder has a giant PDF + a repo + 5 screenshots, the oldest screenshots get truncated first.

---

## What this is NOT

- Not a sub-agent. Maya doesn't invoke "Atlas" or "AssetManager" via a tool call. The digests are background reading, not a conversational step.
- Not a codebase indexer. We don't try to be Greptile/Cursor for a full codebase. A digest is a curated summary, not a searchable index.
- Not real-time GitHub sync. Manual refresh + periodic re-sync; webhooks are v2.
- Not a file viewer. We store the digest, not the original file. Re-upload to re-process.
