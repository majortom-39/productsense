-- Add 'mermaid' to render_kind_enum.
--
-- Maya's create_artifact offers a 'mermaid' render kind for diagram cards, and
-- the frontend already ships a MermaidCard renderer — but the enum was missing
-- the value, so a mermaid insert would fail. This closes that gap. Kept in its
-- own migration because ALTER TYPE ... ADD VALUE must not be used in the same
-- transaction that adds it.

alter type render_kind_enum add value if not exists 'mermaid';
