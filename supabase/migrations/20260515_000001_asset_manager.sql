-- Asset manager: founder-contributed context layer.
--
-- Files, repos, URLs, integrations get summarized into structured digests
-- Maya reads as part of her project context (NOT as a sub-agent — these
-- are preprocessing outputs, like a PRD section).
--
-- Three tables:
--   project_assets       — any attached/ingested item (files + repos + urls)
--   github_connections   — per-user OAuth tokens for GitHub
--   project_repo_links   — joins a project to one GitHub repo

-- ─── Enums ────────────────────────────────────────────────────────────────

create type asset_type_enum as enum (
  'file',       -- founder uploaded a file
  'repo',       -- linked GitHub repo digest
  'url'         -- web URL ingested
);

create type asset_status_enum as enum (
  'pending',         -- queued, not yet processed
  'processing',      -- ingestor running
  'ready',           -- digest available
  'error'            -- ingestion failed; see error_text
);

-- ─── project_assets ───────────────────────────────────────────────────────

create table project_assets (
  id              uuid primary key default gen_random_uuid(),
  project_id      uuid not null references projects(id) on delete cascade,

  asset_type      asset_type_enum not null,
  source_kind     text not null,           -- 'upload' | 'github_repo' | 'web_url'
  source_ref      text,                    -- file mime path / repo full_name / URL

  display_name    text not null,
  mime_type       text,
  size_bytes      bigint,

  status          asset_status_enum not null default 'pending',
  digest_md       text,                    -- the summary Maya reads
  digest_tokens   int,                     -- token count (capped)
  metadata        jsonb not null default '{}'::jsonb,
  error_text      text,

  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  deleted_at      timestamptz
);

create index project_assets_project_live_idx
  on project_assets (project_id, created_at desc)
  where deleted_at is null;

create index project_assets_status_idx
  on project_assets (status)
  where status in ('pending', 'processing');

create trigger project_assets_updated_at
  before update on project_assets
  for each row execute function set_updated_at();

-- ─── github_connections ───────────────────────────────────────────────────
-- One row per (user, github account). Access tokens are encrypted at the
-- app layer using a Fernet key from env. Service role bypasses RLS for
-- writes; users only read their own connections.

create table github_connections (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null references auth.users(id) on delete cascade,
  github_user_login   text not null,
  access_token_enc    text not null,       -- Fernet-encrypted
  scope               text,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  unique (user_id, github_user_login)
);

create index github_connections_user_idx on github_connections (user_id);

create trigger github_connections_updated_at
  before update on github_connections
  for each row execute function set_updated_at();

-- ─── project_repo_links ───────────────────────────────────────────────────
-- One repo per project (1:1). Latest digest is referenced via asset_id.

create table project_repo_links (
  id                      uuid primary key default gen_random_uuid(),
  project_id              uuid not null references projects(id) on delete cascade,
  github_connection_id    uuid not null references github_connections(id) on delete cascade,
  repo_full_name          text not null,   -- 'owner/repo'
  branch                  text not null default 'main',
  asset_id                uuid references project_assets(id) on delete set null,
  last_synced_at          timestamptz,
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now(),
  unique (project_id)              -- enforce 1 repo per project
);

create index project_repo_links_project_idx on project_repo_links (project_id);

create trigger project_repo_links_updated_at
  before update on project_repo_links
  for each row execute function set_updated_at();

-- ─── RLS ──────────────────────────────────────────────────────────────────

alter table project_assets enable row level security;
create policy "scope by project (read)"
  on project_assets for select
  using (project_id in (select id from projects where user_id = auth.uid()));

alter table github_connections enable row level security;
create policy "users read own github connections"
  on github_connections for select
  using (user_id = auth.uid());

alter table project_repo_links enable row level security;
create policy "scope by project (read)"
  on project_repo_links for select
  using (project_id in (select id from projects where user_id = auth.uid()));
