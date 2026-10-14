-- Helpers for the /admin page (and the `beta` command): list approved members with
-- what they have spent, and set a cap explicitly (including back to unlimited, which
-- approve_beta can't do because a NULL cap there means "keep the current one").
-- Like the other beta admin functions, only service_role (and the dashboard) may run them.

create or replace function public.beta_members()
returns table (email text, cap_usd double precision, spent_usd double precision, invited boolean, joined timestamptz)
language sql
stable
security definer
set search_path = ''
as $$
  select
    u.email::text,
    b.cap_usd,
    coalesce((select sum(x.cost) from public.usage x where x.user_id = b.user_id), 0)
      + coalesce((select sum(g.cost) from public.gpu_usage g where g.user_id = b.user_id), 0),
    u.invited_at is not null,
    b.created_at
  from public.beta_users b
  join auth.users u on u.id = b.user_id
  where b.approved
  order by b.created_at desc;
$$;

create or replace function public.set_beta_cap(p_email text, p_cap_usd double precision)
returns text
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_user uuid;
begin
  select id into v_user from auth.users where lower(email) = lower(trim(p_email));
  if v_user is null then
    raise exception 'No account with email %', p_email;
  end if;

  update public.beta_users set cap_usd = p_cap_usd where user_id = v_user;
  return lower(trim(p_email)) || coalesce(' now has a $' || p_cap_usd || ' cap', ' now has no cap');
end;
$$;

revoke all on function public.beta_members() from public, anon, authenticated;
revoke all on function public.set_beta_cap(text, double precision) from public, anon, authenticated;
grant execute on function public.beta_members() to service_role;
grant execute on function public.set_beta_cap(text, double precision) to service_role;
