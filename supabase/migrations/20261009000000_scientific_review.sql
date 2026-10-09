-- Scientific review and refinement state for each project (backend/app/refine.py).
-- NULL means the paper was never reviewed. The backend's _add_missing_columns adds the
-- same nullable column on startup; this migration keeps the schema files in sync with
-- backend/app/db.py. Row Level Security on projects already covers the new column.

alter table public.projects add column if not exists review jsonb;
