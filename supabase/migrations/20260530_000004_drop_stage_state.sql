-- Remove the dead 12-stage discovery state machine.
--
-- The new Deep Agents architecture has no stage machine — the product arc is
-- guidance, not gated stages. Nothing writes `projects.stage_state` anymore
-- (its only writer was the deleted old-Maya layer), and `discovery_artifacts.stage`
-- is no longer set or read (the Discovery tab is a flat chronological feed).
--
-- The unused `render_kind_enum` labels (problem_statement, wireframe_flow,
-- user_stories, …) are deliberately LEFT: Postgres can't drop enum values
-- without recreating the type, and they're inert.

alter table projects drop column if exists stage_state;
alter table discovery_artifacts drop column if exists stage;
