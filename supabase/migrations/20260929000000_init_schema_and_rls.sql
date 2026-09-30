-- Baseline schema for OpenScientist's application data, moved from a local SQLite
-- file to this Supabase Postgres project so Row Level Security can protect it.
-- Column names/types mirror backend/app/db.py; keep the two in sync by hand, since
-- the Python models are still the source of truth for the app's own reads/writes.

create table if not exists public.projects (
  id text primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  title text not null default 'Untitled research',
  stage text not null default 'clarify',
  autonomous boolean not null default false,
  settings jsonb not null default '{}'::jsonb,
  brief jsonb,
  chosen_gap jsonb,
  plan jsonb,
  blueprint jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists projects_user_id_idx on public.projects (user_id);
create index if not exists projects_updated_at_idx on public.projects (updated_at desc);

create table if not exists public.messages (
  id text primary key,
  project_id text not null references public.projects (id) on delete cascade,
  role text not null,
  kind text not null default 'text',
  content text not null,
  payload jsonb,
  created_at timestamptz not null default now()
);
create index if not exists messages_project_id_idx on public.messages (project_id);

-- Global literature cache shared by every project and every user (see Paper in
-- db.py): titles/abstracts/citation counts of published papers, never scoped to
-- one user, so once a paper is read by anyone it is never re-fetched.
create table if not exists public.papers (
  id text primary key,
  title text not null,
  norm_title text not null,
  abstract text,
  tldr text,
  year integer,
  venue text,
  authors jsonb not null default '[]'::jsonb,
  citation_count integer not null default 0,
  doi text,
  arxiv_id text,
  s2_id text,
  openalex_id text,
  url text,
  pdf_url text,
  notes jsonb,
  "references" jsonb,
  updated_at timestamptz not null default now()
);
create index if not exists papers_norm_title_idx on public.papers (norm_title);
create index if not exists papers_doi_idx on public.papers (doi);
create index if not exists papers_arxiv_id_idx on public.papers (arxiv_id);
create index if not exists papers_s2_id_idx on public.papers (s2_id);
create index if not exists papers_openalex_id_idx on public.papers (openalex_id);

create table if not exists public.project_papers (
  id text primary key,
  project_id text not null references public.projects (id) on delete cascade,
  paper_id text not null references public.papers (id) on delete cascade,
  origin text not null default 'search',
  score double precision not null default 0,
  relevance integer,
  reason text,
  included boolean not null default false
);
create index if not exists project_papers_project_id_idx on public.project_papers (project_id);
create index if not exists project_papers_paper_id_idx on public.project_papers (paper_id);

-- Global search-result cache keyed by query; not scoped to a project or user.
create table if not exists public.search_cache (
  key text primary key,
  paper_ids jsonb not null default '[]'::jsonb,
  fetched_at timestamptz not null default now()
);

create table if not exists public.runs (
  id text primary key,
  project_id text not null references public.projects (id) on delete cascade,
  kind text not null,
  status text not null default 'running',
  phase text not null default 'starting',
  counts jsonb not null default '{}'::jsonb,
  log jsonb not null default '[]'::jsonb,
  result jsonb,
  error text,
  started_at timestamptz not null default now(),
  finished_at timestamptz
);
create index if not exists runs_project_id_idx on public.runs (project_id);

create table if not exists public.task_states (
  id text primary key,
  project_id text not null references public.projects (id) on delete cascade,
  blueprint_run_id text not null,
  task_id text not null,
  agent text not null,
  status text not null default 'pending',
  attempts integer not null default 0,
  cost double precision not null default 0,
  summary text,
  artifacts jsonb not null default '[]'::jsonb,
  checks jsonb not null default '[]'::jsonb,
  issues jsonb not null default '[]'::jsonb,
  events jsonb not null default '[]'::jsonb,
  note text,
  feedback text,
  started_at timestamptz,
  finished_at timestamptz
);
create index if not exists task_states_project_id_idx on public.task_states (project_id);
create index if not exists task_states_blueprint_run_id_idx on public.task_states (blueprint_run_id);

-- A credential the user supplied for one project's sandbox, exposed only to that
-- project's agent runs as an env var; never returned by the API after saving.
create table if not exists public.secrets (
  id text primary key,
  project_id text not null references public.projects (id) on delete cascade,
  name text not null,
  value text not null,
  created_at timestamptz not null default now()
);
create index if not exists secrets_project_id_idx on public.secrets (project_id);

create table if not exists public.gpu_usage (
  id text primary key,
  project_id text references public.projects (id) on delete cascade,
  run_id text,
  gpu text not null,
  job text not null,
  seconds double precision not null default 0,
  cost double precision not null default 0,
  created_at timestamptz not null default now()
);
create index if not exists gpu_usage_project_id_idx on public.gpu_usage (project_id);

create table if not exists public.usage (
  id text primary key,
  project_id text references public.projects (id) on delete cascade,
  run_id text,
  model text not null,
  input_tokens integer not null default 0,
  cached_tokens integer not null default 0,
  output_tokens integer not null default 0,
  web_searches integer not null default 0,
  cost double precision not null default 0,
  created_at timestamptz not null default now()
);
create index if not exists usage_project_id_idx on public.usage (project_id);

-- ── Row Level Security ──────────────────────────────────────────────────────
--
-- OpenScientist's FastAPI backend connects with this project's full Postgres
-- credentials (a trusted server, never exposed to the browser) and enforces
-- per-user ownership in application code on every route (see backend/app/auth.py
-- and backend/app/routes/projects.py) — it does not depend on these policies to
-- isolate its own queries.
--
-- What RLS actually protects here: Supabase auto-exposes every table in this
-- schema over its REST/GraphQL Data API and Realtime, reachable straight from
-- the browser with the publishable ("anon") key already shipped in the frontend
-- bundle. Without RLS, that API would let anyone read or write every user's
-- research data directly, bypassing FastAPI entirely. These policies close that
-- hole and are scoped to `authenticated` only (never `anon`), so a signed-out
-- visitor gets nothing.

alter table public.projects enable row level security;
alter table public.messages enable row level security;
alter table public.papers enable row level security;
alter table public.project_papers enable row level security;
alter table public.search_cache enable row level security;
alter table public.runs enable row level security;
alter table public.task_states enable row level security;
alter table public.secrets enable row level security;
alter table public.gpu_usage enable row level security;
alter table public.usage enable row level security;

create policy "Users manage their own projects" on public.projects
  for all to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "Users manage their own project messages" on public.messages
  for all to authenticated
  using (exists (select 1 from public.projects p where p.id = messages.project_id and p.user_id = auth.uid()))
  with check (exists (select 1 from public.projects p where p.id = messages.project_id and p.user_id = auth.uid()));

create policy "Users manage their own project paper links" on public.project_papers
  for all to authenticated
  using (exists (select 1 from public.projects p where p.id = project_papers.project_id and p.user_id = auth.uid()))
  with check (exists (select 1 from public.projects p where p.id = project_papers.project_id and p.user_id = auth.uid()));

create policy "Users manage their own project runs" on public.runs
  for all to authenticated
  using (exists (select 1 from public.projects p where p.id = runs.project_id and p.user_id = auth.uid()))
  with check (exists (select 1 from public.projects p where p.id = runs.project_id and p.user_id = auth.uid()));

create policy "Users manage their own project task states" on public.task_states
  for all to authenticated
  using (exists (select 1 from public.projects p where p.id = task_states.project_id and p.user_id = auth.uid()))
  with check (exists (select 1 from public.projects p where p.id = task_states.project_id and p.user_id = auth.uid()));

create policy "Users manage their own project secrets" on public.secrets
  for all to authenticated
  using (exists (select 1 from public.projects p where p.id = secrets.project_id and p.user_id = auth.uid()))
  with check (exists (select 1 from public.projects p where p.id = secrets.project_id and p.user_id = auth.uid()));

create policy "Users read their own project gpu usage" on public.gpu_usage
  for select to authenticated
  using (exists (select 1 from public.projects p where p.id = gpu_usage.project_id and p.user_id = auth.uid()));

create policy "Users read their own project usage" on public.usage
  for select to authenticated
  using (exists (select 1 from public.projects p where p.id = usage.project_id and p.user_id = auth.uid()));

-- Papers and search_cache hold no per-user data (published-paper metadata and
-- cached query results), so any signed-in user may read them; only the backend
-- (which bypasses RLS on its own connection) writes them.
create policy "Authenticated users read the shared paper cache" on public.papers
  for select to authenticated using (true);

create policy "Authenticated users read the shared search cache" on public.search_cache
  for select to authenticated using (true);
