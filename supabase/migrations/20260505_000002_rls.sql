-- Row-Level Security policies
-- Every table is scoped per project; projects scoped per user.
-- Service role bypasses RLS automatically — used by the FastAPI backend.

-- ─── projects ─────────────────────────────────────────────────────────────
alter table projects enable row level security;

create policy "users can read their own projects"
  on projects for select
  using (auth.uid() = user_id);

create policy "users can create projects"
  on projects for insert
  with check (auth.uid() = user_id);

create policy "users can update their own projects"
  on projects for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "users can delete their own projects"
  on projects for delete
  using (auth.uid() = user_id);

-- ─── Helper: scope-by-project policy template ─────────────────────────────
-- Every other table follows the pattern below: access is granted iff the
-- row's project_id belongs to a project owned by the current user.

-- prds
alter table prds enable row level security;
create policy "scope by project (read)"
  on prds for select
  using (project_id in (select id from projects where user_id = auth.uid()));
create policy "scope by project (write)"
  on prds for all
  using (project_id in (select id from projects where user_id = auth.uid()))
  with check (project_id in (select id from projects where user_id = auth.uid()));

-- prd_sections
alter table prd_sections enable row level security;
create policy "scope by prd"
  on prd_sections for all
  using (prd_id in (
    select prds.id from prds
    join projects on projects.id = prds.project_id
    where projects.user_id = auth.uid()
  ))
  with check (prd_id in (
    select prds.id from prds
    join projects on projects.id = prds.project_id
    where projects.user_id = auth.uid()
  ));

-- sprints
alter table sprints enable row level security;
create policy "scope by project"
  on sprints for all
  using (project_id in (select id from projects where user_id = auth.uid()))
  with check (project_id in (select id from projects where user_id = auth.uid()));

-- tasks
alter table tasks enable row level security;
create policy "scope by project"
  on tasks for all
  using (project_id in (select id from projects where user_id = auth.uid()))
  with check (project_id in (select id from projects where user_id = auth.uid()));

-- decisions
alter table decisions enable row level security;
create policy "scope by project"
  on decisions for all
  using (project_id in (select id from projects where user_id = auth.uid()))
  with check (project_id in (select id from projects where user_id = auth.uid()));

-- research
alter table research enable row level security;
create policy "scope by project"
  on research for all
  using (project_id in (select id from projects where user_id = auth.uid()))
  with check (project_id in (select id from projects where user_id = auth.uid()));

-- messages
alter table messages enable row level security;
create policy "scope by project"
  on messages for all
  using (project_id in (select id from projects where user_id = auth.uid()))
  with check (project_id in (select id from projects where user_id = auth.uid()));

-- clarifications
alter table clarifications enable row level security;
create policy "scope by project"
  on clarifications for all
  using (project_id in (select id from projects where user_id = auth.uid()))
  with check (project_id in (select id from projects where user_id = auth.uid()));

-- agent_runs — read-only for users (telemetry); backend writes via service role
alter table agent_runs enable row level security;
create policy "scope by project (read)"
  on agent_runs for select
  using (project_id in (select id from projects where user_id = auth.uid()));
