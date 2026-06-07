-- ProductSense initial schema
-- Tables: projects, prds, prd_sections, decisions, sprints, tasks,
--         research, messages, clarifications, agent_runs

-- ─── Enums ────────────────────────────────────────────────────────────────

create type decided_by_enum as enum (
  'maya_autonomous',
  'agent_with_user',
  'maya_with_user',
  'user',
  'agent_flagged'
);

create type decision_status_enum as enum ('open', 'decided');
create type decision_open_type_enum as enum ('escalated');

create type task_status_enum as enum ('todo', 'in_progress', 'done');

create type research_category_enum as enum (
  'problem', 'users', 'competitors', 'failure_modes', 'tech'
);
create type research_status_enum as enum ('fresh', 'stale', 'running');

create type message_role_enum as enum ('user', 'assistant', 'system');

create type clarification_status_enum as enum ('open', 'answered', 'cancelled');

-- ─── Tables ───────────────────────────────────────────────────────────────

create table projects (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users(id) on delete cascade,
  name          text not null,
  icon          text,
  entry_type    text not null default 'fresh_idea',
  created_at    timestamptz default now(),
  updated_at    timestamptz default now()
);
create index projects_user_id_idx on projects (user_id);

create table prds (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references projects(id) on delete cascade,
  version       int not null,
  status        text not null default 'draft',
  body_md       text,
  created_at    timestamptz default now(),
  unique (project_id, version)
);
create index prds_project_id_idx on prds (project_id);

create table prd_sections (
  id            uuid primary key default gen_random_uuid(),
  prd_id        uuid not null references prds(id) on delete cascade,
  section_id    text not null,
  title         text not null,
  body_md       text not null,
  order_index   int not null,
  unique (prd_id, section_id)
);
create index prd_sections_prd_id_idx on prd_sections (prd_id);

create table sprints (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references projects(id) on delete cascade,
  number        int not null,
  name          text not null,
  subtitle      text,
  status        text not null default 'active',
  unique (project_id, number)
);
create index sprints_project_id_idx on sprints (project_id);

create table tasks (
  id                    uuid primary key default gen_random_uuid(),
  project_id            uuid not null references projects(id) on delete cascade,
  sprint_id             uuid not null references sprints(id) on delete cascade,
  display_id            text not null,
  status                task_status_enum not null default 'todo',
  title                 text not null,
  goal                  text,
  description           text,
  acceptance            jsonb,
  prd_context           text,
  do_not                jsonb,
  blocked_by            jsonb,
  open_decision_id      uuid,
  agent_note            text,
  files_touched         jsonb,
  completion_summary    text,
  build_notes           jsonb,
  decisions_logged      jsonb,
  created_at            timestamptz default now(),
  updated_at            timestamptz default now(),
  unique (project_id, display_id)
);
create index tasks_project_status_idx on tasks (project_id, status);
create index tasks_sprint_id_idx on tasks (sprint_id);

create table decisions (
  id              uuid primary key default gen_random_uuid(),
  project_id      uuid not null references projects(id) on delete cascade,
  display_id      text not null,
  decided_by      decided_by_enum not null,
  status          decision_status_enum not null default 'decided',
  open_type       decision_open_type_enum,
  title           text not null,
  detail          text not null,
  why             text not null,
  related_task_id uuid references tasks(id),
  tag             text,
  pinned          boolean default false,
  affects         jsonb,
  created_at      timestamptz default now(),
  resolved_at     timestamptz,
  unique (project_id, display_id)
);
create index decisions_project_status_idx on decisions (project_id, status);

-- backfill the FK from tasks.open_decision_id now that decisions exists
alter table tasks
  add constraint tasks_open_decision_id_fkey
  foreign key (open_decision_id) references decisions(id) on delete set null;

create table research (
  id              uuid primary key default gen_random_uuid(),
  project_id      uuid not null references projects(id) on delete cascade,
  category        research_category_enum not null,
  question        text not null,
  status          research_status_enum not null default 'fresh',
  finding         text,
  bullets         jsonb,
  sources         jsonb,
  tool            text not null,
  affects         jsonb,
  created_at      timestamptz default now(),
  refreshed_at    timestamptz default now()
);
create index research_project_category_idx on research (project_id, category);

create table messages (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references projects(id) on delete cascade,
  role          message_role_enum not null,
  agent         text,
  content       text not null,
  tool_call     jsonb,
  quoted        text,
  created_at    timestamptz default now()
);
create index messages_project_created_idx on messages (project_id, created_at);

create table clarifications (
  id              uuid primary key default gen_random_uuid(),
  project_id      uuid not null references projects(id) on delete cascade,
  related_task_id uuid not null references tasks(id) on delete cascade,
  decision_id     uuid references decisions(id) on delete set null,
  question        text not null,
  status          clarification_status_enum not null default 'open',
  answer          text,
  decided_by      decided_by_enum,
  created_at      timestamptz default now(),
  resolved_at     timestamptz
);
create index clarifications_project_status_idx on clarifications (project_id, status);

create table agent_runs (
  id              uuid primary key default gen_random_uuid(),
  project_id      uuid references projects(id) on delete cascade,
  agent           text not null,
  invoked_by      text not null,
  input_summary   text,
  output_summary  text,
  tokens_used     int,
  duration_ms     int,
  status          text,
  created_at      timestamptz default now()
);
create index agent_runs_project_created_idx on agent_runs (project_id, created_at);

-- ─── Updated-at triggers ──────────────────────────────────────────────────

create or replace function set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger projects_updated_at
  before update on projects
  for each row execute function set_updated_at();

create trigger tasks_updated_at
  before update on tasks
  for each row execute function set_updated_at();
