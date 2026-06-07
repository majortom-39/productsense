-- Deep Agents coherence engine (clean_architecture.md §8, §11a).
--
-- Adds the single dependency graph that keeps every product node coherent, the
-- lazy dirty-marking columns, and the solutions→features→MVP node tables that
-- the product-arc loop (§6) produces. Clean break: the old `affects` jsonb on
-- decisions is retired in favor of the real `dependencies` edge table.
--
-- Node tables in this architecture: discovery_artifacts, decisions, tasks,
-- prd_sections, solutions, features. Each carries needs_review / version /
-- updated_at so a material change can flag its direct dependents (and only its
-- direct dependents — propagation is lazy, never silent).

-- ─── Relationship vocabulary ───────────────────────────────────────────────
do $$
begin
  if not exists (select 1 from pg_type where typname = 'dep_relationship_enum') then
    create type dep_relationship_enum as enum ('derives_from', 'constrains', 'supersedes');
  end if;
end $$;

-- ─── The dependency graph (one generic edge table) ─────────────────────────
-- dependent_id depends on depends_on_id. Types are free text (not an enum) so
-- adding a new node kind is a content change, not a migration:
--   'artifact' | 'decision' | 'prd_section' | 'task' | 'guardrail'
--   | 'solution' | 'feature'
create table if not exists dependencies (
  id              uuid primary key default gen_random_uuid(),
  project_id      uuid not null references projects(id) on delete cascade,
  dependent_type  text not null,
  dependent_id    uuid not null,
  depends_on_type text not null,
  depends_on_id   uuid not null,
  relationship    dep_relationship_enum not null,
  created_by      text not null,          -- 'maya' | 'founder' | '<specialist>'
  why             text,
  created_at      timestamptz not null default now()
);

-- "what depends on X?" (forward fan-out for dirty-marking)
create index if not exists dependencies_depends_on_idx
  on dependencies (project_id, depends_on_type, depends_on_id);
-- "what does X depend on?" (provenance)
create index if not exists dependencies_dependent_idx
  on dependencies (project_id, dependent_type, dependent_id);

alter table dependencies enable row level security;
drop policy if exists "scope by project (read)" on dependencies;
create policy "scope by project (read)"
  on dependencies for select
  using (project_id in (select id from projects where user_id = auth.uid()));
-- Writes go through Maya via the service role (bypasses RLS).

-- ─── Lazy dirty-marking columns on every node table ────────────────────────
alter table discovery_artifacts
  add column if not exists needs_review     boolean not null default false,
  add column if not exists needs_review_why text,
  add column if not exists version          int     not null default 1;

alter table decisions
  add column if not exists needs_review     boolean not null default false,
  add column if not exists needs_review_why text,
  add column if not exists version          int     not null default 1,
  add column if not exists updated_at       timestamptz not null default now();

alter table tasks
  add column if not exists needs_review     boolean not null default false,
  add column if not exists needs_review_why text,
  add column if not exists version          int     not null default 1;

alter table prd_sections
  add column if not exists needs_review     boolean not null default false,
  add column if not exists needs_review_why text,
  add column if not exists version          int     not null default 1,
  add column if not exists updated_at       timestamptz not null default now();

-- updated_at triggers for the tables that just gained the column
-- (set_updated_at() defined in the init migration).
drop trigger if exists decisions_updated_at on decisions;
create trigger decisions_updated_at
  before update on decisions
  for each row execute function set_updated_at();

drop trigger if exists prd_sections_updated_at on prd_sections;
create trigger prd_sections_updated_at
  before update on prd_sections
  for each row execute function set_updated_at();

-- ─── solutions → features → MVP nodes (§6) ─────────────────────────────────
-- Candidate ways to solve the validated problem. Maya diverges here, then
-- converges on a recommendation.
create table if not exists solutions (
  id               uuid primary key default gen_random_uuid(),
  project_id       uuid not null references projects(id) on delete cascade,
  display_id       text not null,            -- 'sol-1'
  title            text not null,
  summary          text,
  tradeoffs        jsonb not null default '{}'::jsonb,   -- {pros:[], cons:[]}
  recommended      boolean not null default false,
  needs_review     boolean not null default false,
  needs_review_why text,
  version          int     not null default 1,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  unique (project_id, display_id)
);

-- Concrete features shaped from the chosen solution(s). `in_mvp` is set by the
-- explicit MVP-cut decision (a decision row, tag='scope', that `constrains`
-- the features it keeps).
create table if not exists features (
  id               uuid primary key default gen_random_uuid(),
  project_id       uuid not null references projects(id) on delete cascade,
  display_id       text not null,            -- 'f-1'
  title            text not null,
  description      text,
  in_mvp           boolean not null default false,
  priority         int,
  needs_review     boolean not null default false,
  needs_review_why text,
  version          int     not null default 1,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  unique (project_id, display_id)
);

create index if not exists solutions_project_idx on solutions (project_id, created_at);
create index if not exists features_project_idx  on features  (project_id, priority);

alter table solutions enable row level security;
drop policy if exists "scope by project (read)" on solutions;
create policy "scope by project (read)"
  on solutions for select
  using (project_id in (select id from projects where user_id = auth.uid()));

alter table features enable row level security;
drop policy if exists "scope by project (read)" on features;
create policy "scope by project (read)"
  on features for select
  using (project_id in (select id from projects where user_id = auth.uid()));

drop trigger if exists solutions_updated_at on solutions;
create trigger solutions_updated_at
  before update on solutions
  for each row execute function set_updated_at();

drop trigger if exists features_updated_at on features;
create trigger features_updated_at
  before update on features
  for each row execute function set_updated_at();

-- ─── Retire the old per-row impact blob ────────────────────────────────────
-- Superseded by the `dependencies` edge table. No back-compat shim.
alter table decisions drop column if exists affects;
