-- Per-project MCP keys (ps_live_…) for the founder's coding agent.
-- Only the sha256 hash is stored; the plaintext is shown once at generation.
create table if not exists mcp_keys (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id) on delete cascade,
  key_hash text not null unique,
  key_prefix text not null,            -- display only, e.g. 'ps_live_a1b2…'
  label text,
  created_at timestamptz not null default now(),
  last_seen_at timestamptz,            -- stamped on every authed MCP request
  revoked_at timestamptz
);
create index if not exists mcp_keys_project_idx on mcp_keys(project_id);
alter table mcp_keys enable row level security;
-- Service-role only (the API mediates all access; no direct client reads).
