-- Execution spend (backend/app/execution/orchestrator.py spent()) sums usage.cost over the
-- project's execution runs: WHERE run_id IN (SELECT id FROM runs ...). The ORM declares an index on
-- usage.run_id, but the tables were created by these migrations, so it never existed in Postgres.
-- Query planning only: it changes no data and no egress.
create index if not exists usage_run_id_idx on public.usage (run_id);
