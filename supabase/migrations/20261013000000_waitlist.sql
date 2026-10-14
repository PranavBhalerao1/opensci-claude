-- Public waitlist with referrals for the OpenScientist website.
--
-- The browser never touches the table: RLS is on with no policies, so the
-- publishable key cannot list or read signups. The site calls two SECURITY DEFINER
-- functions instead, which return only a code, a queue position and counts; never
-- anyone's email.
--
-- Queue order: signup order, minus 10 places per person you referred.

create table if not exists public.waitlist (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,
  code text not null unique,
  referred_by text,
  created_at timestamptz not null default now()
);
create index if not exists waitlist_referred_by_idx on public.waitlist (referred_by);
alter table public.waitlist enable row level security;

create or replace function public.waitlist_status(p_code text)
returns json
language sql
stable
security definer
set search_path = public
as $$
  with refs as (
    select referred_by as code, count(*) as n
    from waitlist where referred_by is not null group by referred_by
  ),
  ranked as (
    select w.code,
           row_number() over (order by w.created_at, w.id) - 1 as idx,
           coalesce(r.n, 0) as n
    from waitlist w left join refs r on r.code = w.code
  ),
  ordered as (
    select code, n, row_number() over (order by idx - 10 * n, idx) as pos from ranked
  )
  select json_build_object(
    'code', o.code, 'position', o.pos, 'total', (select count(*) from waitlist),
    'referrals', o.n, 'boost', 10)
  from ordered o where o.code = lower(trim(p_code));
$$;

create or replace function public.join_waitlist(p_email text, p_ref text default null)
returns json
language plpgsql
volatile
security definer
set search_path = public
as $$
declare
  v_email text := lower(trim(p_email));
  v_ref text := nullif(lower(trim(coalesce(p_ref, ''))), '');
  v_code text;
  v_existing text;
  alphabet constant text := 'abcdefghjkmnpqrstuvwxyz23456789';
begin
  if v_email is null or length(v_email) > 254 or v_email !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' then
    raise exception 'Enter a valid email address' using errcode = '22023';
  end if;

  select code into v_existing from waitlist where email = v_email;
  if v_existing is not null then
    return (waitlist_status(v_existing)::jsonb || '{"already": true}')::json;
  end if;

  -- Unknown referral codes are ignored rather than rejected.
  if v_ref is not null and not exists (select 1 from waitlist where code = v_ref) then
    v_ref := null;
  end if;

  loop
    v_code := (
      select string_agg(substr(alphabet, 1 + floor(random() * length(alphabet))::int, 1), '')
      from generate_series(1, 7)
    );
    exit when not exists (select 1 from waitlist where code = v_code);
  end loop;

  insert into waitlist (email, code, referred_by) values (v_email, v_code, v_ref)
  on conflict (email) do nothing;
  select code into v_code from waitlist where email = v_email;  -- concurrent duplicate signup
  return (waitlist_status(v_code)::jsonb || '{"already": false}')::json;
end;
$$;

revoke all on function public.waitlist_status(text) from public;
revoke all on function public.join_waitlist(text, text) from public;
grant execute on function public.waitlist_status(text) to anon, authenticated;
grant execute on function public.join_waitlist(text, text) to anon, authenticated;
