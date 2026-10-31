-- Email subscribers to company updates (/news).
--
-- Like the waitlist, the browser never touches the table: RLS is on with no policies,
-- and the site calls one SECURITY DEFINER function that returns nothing but a flag.
-- People with an account receive updates without subscribing here.

create table if not exists public.news_subscribers (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,
  created_at timestamptz not null default now()
);
alter table public.news_subscribers enable row level security;

create or replace function public.subscribe_news(p_email text)
returns json
language plpgsql
volatile
security definer
set search_path = public
as $$
declare
  v_email text := lower(trim(p_email));
begin
  if v_email is null or length(v_email) > 254 or v_email !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' then
    raise exception 'Enter a valid email address' using errcode = '22023';
  end if;
  if exists (select 1 from news_subscribers where email = v_email) then
    return json_build_object('already', true);
  end if;
  insert into news_subscribers (email) values (v_email) on conflict (email) do nothing;
  return json_build_object('already', false);
end;
$$;

revoke all on function public.subscribe_news(text) from public;
grant execute on function public.subscribe_news(text) to anon, authenticated;
