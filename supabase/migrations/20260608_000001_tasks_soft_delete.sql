-- Tasks become soft-deletable so Maya's remove_task never hard-destroys a
-- planned task (mirrors the deleted_at pattern on discovery_artifacts /
-- solutions / features). The task stays in the DB for provenance + history;
-- the live board read (services/artifacts.list_tasks) filters deleted_at null.
alter table tasks add column if not exists deleted_at timestamptz;
