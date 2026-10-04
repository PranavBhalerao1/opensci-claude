-- Private beta: per-user access approval and a USD spending cap, plus durable
-- per-user attribution of the cost OpenScientist already tracks (usage, gpu_usage).
--
-- Admin interface is the Supabase table editor on public.beta_users:
--   approved  false → true   grants access
--   cap_usd   e.g. 5         spending cap in USD; NULL = unlimited
-- Enforcement lives in backend/app/beta.py; the database is the source of truth, so
-- changes take effect on the user's next request (no token refresh needed).
--
-- Apply this before deploying the backend that reads beta_users: the backend's
-- create_all would otherwise create an empty beta_users table and every user would
-- appear pending until this migration runs.

-- ── beta_users ──────────────────────────────────────────────────────────────

create table if not exists public.beta_users (
  user_id uuid primary key references auth.users (id) on delete cascade,
  approved boolean not null default false,
  cap_usd double precision,
  created_at timestamptz not null default now()
);
-- Idempotent: if the backend created the table first (without server defaults), the
-- signup trigger below still inserts pending rows.
alter table public.beta_users alter column approved set default false;
alter table public.beta_users alter column created_at set default now();

-- Everyone who already has an account keeps access, uncapped.
insert into public.beta_users (user_id, approved, cap_usd)
select id, true, null from auth.users
on conflict (user_id) do nothing;

-- Every new signup starts pending (approved = false, cap_usd = NULL).
create or replace function public.create_pending_beta_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.beta_users (user_id) values (new.id) on conflict (user_id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created_beta on auth.users;
create trigger on_auth_user_created_beta
  after insert on auth.users
  for each row execute function public.create_pending_beta_user();

-- Users may read their own beta status. There are deliberately no insert/update/delete
-- policies: only the backend (which bypasses RLS) and the dashboard change access, so
-- nobody can approve themselves or raise their own cap through the Data API.
alter table public.beta_users enable row level security;

drop policy if exists "Users read their own beta status" on public.beta_users;
create policy "Users read their own beta status" on public.beta_users
  for select to authenticated
  using (auth.uid() = user_id);

-- ── Cost attribution ────────────────────────────────────────────────────────

alter table public.usage add column if not exists user_id uuid references auth.users (id) on delete set null;
alter table public.gpu_usage add column if not exists user_id uuid references auth.users (id) on delete set null;
create index if not exists usage_user_id_idx on public.usage (user_id);
create index if not exists gpu_usage_user_id_idx on public.gpu_usage (user_id);

-- Backfill from project ownership. Rows whose project no longer exists (or never had
-- one) stay unattributed rather than guessed.
update public.usage u set user_id = p.user_id
from public.projects p
where u.project_id = p.id and u.user_id is null;

update public.gpu_usage g set user_id = p.user_id
from public.projects p
where g.project_id = p.id and g.user_id is null;

-- Deleting a project used to cascade-delete its cost rows (`on delete cascade` in the
-- baseline schema), erasing spend history. Keep the rows instead and just detach them
-- from the deleted project; user_id keeps them attributable. The constraint is found by
-- what it references rather than by name, so a differently named FK is replaced too.
do $$
declare
  r record;
begin
  for r in
    select c.conname, c.conrelid::regclass as tbl
    from pg_constraint c
    where c.contype = 'f'
      and c.confrelid = 'public.projects'::regclass
      and c.conrelid in ('public.usage'::regclass, 'public.gpu_usage'::regclass)
  loop
    execute format('alter table %s drop constraint %I', r.tbl, r.conname);
  end loop;
end $$;

alter table public.usage
  add constraint usage_project_id_fkey
  foreign key (project_id) references public.projects (id) on delete set null;
alter table public.gpu_usage
  add constraint gpu_usage_project_id_fkey
  foreign key (project_id) references public.projects (id) on delete set null;
