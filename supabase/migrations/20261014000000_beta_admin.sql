-- Beta admin helpers, run from the Supabase SQL Editor.
--
--   select * from beta_requests();                 pending signups, newest first, with emails
--   select approve_beta('friend@lab.edu');         approve (keeps their current cap)
--   select approve_beta('friend@lab.edu', 5);      approve with a $5 spending cap
--   select revoke_beta('friend@lab.edu');          take access away again
--
-- People you invite (Authentication > Users > Send invitation) are approved
-- automatically: sending the invite is the decision.
--
-- None of these functions can be called through the Data API. They are revoked from
-- anon and authenticated, so only the dashboard (postgres) and the backend
-- (service_role) can run them, and nobody can approve themselves from the site.

-- ── Invited users start approved ────────────────────────────────────────────

-- Supabase sets auth.users.invited_at when it creates the user for an invite.
create or replace function public.create_pending_beta_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.beta_users (user_id, approved)
  values (new.id, new.invited_at is not null)
  on conflict (user_id) do nothing;
  return new;
end;
$$;

-- Anyone already invited but still pending gets the access the invite promised.
update public.beta_users b
set approved = true
from auth.users u
where u.id = b.user_id and u.invited_at is not null and not b.approved;

-- ── Pending requests, with emails ───────────────────────────────────────────

create or replace function public.beta_requests()
returns table (email text, signed_up timestamptz, invited boolean, confirmed boolean)
language sql
stable
security definer
set search_path = ''
as $$
  select u.email::text, b.created_at, u.invited_at is not null, u.email_confirmed_at is not null
  from public.beta_users b
  join auth.users u on u.id = b.user_id
  where not b.approved
  order by b.created_at desc;
$$;

-- ── Approve / revoke by email ───────────────────────────────────────────────

create or replace function public.approve_beta(p_email text, p_cap_usd double precision default null)
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

  insert into public.beta_users (user_id, approved, cap_usd)
  values (v_user, true, p_cap_usd)
  on conflict (user_id) do update
    set approved = true,
        cap_usd = coalesce(p_cap_usd, public.beta_users.cap_usd);

  return 'Approved ' || lower(trim(p_email))
    || coalesce(' with a $' || p_cap_usd || ' cap', '');
end;
$$;

create or replace function public.revoke_beta(p_email text)
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

  update public.beta_users set approved = false where user_id = v_user;
  return 'Revoked ' || lower(trim(p_email));
end;
$$;

revoke all on function public.beta_requests() from public, anon, authenticated;
revoke all on function public.approve_beta(text, double precision) from public, anon, authenticated;
revoke all on function public.revoke_beta(text) from public, anon, authenticated;
