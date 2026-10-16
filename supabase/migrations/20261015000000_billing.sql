-- Paid plans (Stripe) and lab sales inquiries.
--
-- subscriptions: one row per user, written only by the website's Stripe webhook
-- (frontend/src/app/api/stripe/webhook) with the secret key. The backend reads it to
-- grant access and each billing period's credits (backend/app/beta.py). Browsers never
-- read it: RLS is on with no policies; users see their plan through /api/me.
--
-- lab_inquiries: the "Contact us" form for the Lab plan on /pricing, listed on /admin.

create table if not exists public.subscriptions (
  user_id uuid primary key references auth.users (id) on delete cascade,
  plan text not null,
  status text not null,
  credits_usd double precision not null default 0,
  period_start timestamptz,
  period_end timestamptz,
  stripe_customer_id text,
  stripe_subscription_id text,
  updated_at timestamptz not null default now()
);
create index if not exists subscriptions_customer_idx on public.subscriptions (stripe_customer_id);
alter table public.subscriptions enable row level security;

create table if not exists public.lab_inquiries (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  email text not null,
  organization text,
  team_size text,
  message text,
  created_at timestamptz not null default now()
);
alter table public.lab_inquiries enable row level security;

revoke all on public.subscriptions from anon, authenticated;
revoke all on public.lab_inquiries from anon, authenticated;
grant all on public.subscriptions to service_role;
grant all on public.lab_inquiries to service_role;

-- For /admin: paying users with their email and this period's spend.
create or replace function public.billing_subscribers()
returns table (email text, plan text, status text, credits_usd double precision,
               spent_usd double precision, period_end timestamptz)
language sql
stable
security definer
set search_path = ''
as $$
  select
    u.email::text,
    s.plan,
    s.status,
    s.credits_usd,
    coalesce((select sum(x.cost) from public.usage x
              where x.user_id = s.user_id and x.created_at >= coalesce(s.period_start, '-infinity')), 0)
      + coalesce((select sum(g.cost) from public.gpu_usage g
                  where g.user_id = s.user_id and g.created_at >= coalesce(s.period_start, '-infinity')), 0),
    s.period_end
  from public.subscriptions s
  join auth.users u on u.id = s.user_id
  order by s.updated_at desc;
$$;

revoke all on function public.billing_subscribers() from public, anon, authenticated;
grant execute on function public.billing_subscribers() to service_role;
