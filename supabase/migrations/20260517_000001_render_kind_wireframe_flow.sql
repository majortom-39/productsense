-- Add 'wireframe_flow' to the render_kind_enum used by research_artifacts
-- and agent_runs.output_payload. Maya draws UX walkthroughs in this shape:
-- N screens in a device frame, with arrows between them. Sandboxed iframes
-- on the frontend render the HTML; sandbox + greyscale reset are enforced
-- client-side.
--
-- Has to be its own ALTER TYPE statement because enum-add must run outside
-- a transaction in older Postgres versions; Supabase 17 is fine but the
-- IF NOT EXISTS guard makes this idempotent across re-runs.

alter type render_kind_enum add value if not exists 'wireframe_flow';
