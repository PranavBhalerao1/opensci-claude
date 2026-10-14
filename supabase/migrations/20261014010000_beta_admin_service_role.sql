-- Let the `beta` admin command (scripts/beta.mjs) call the beta admin functions.
-- It authenticates with the project's secret (service_role) key, which never leaves
-- the admin's machine. anon and authenticated stay revoked, so the site still can't.
grant execute on function public.beta_requests() to service_role;
grant execute on function public.approve_beta(text, double precision) to service_role;
grant execute on function public.revoke_beta(text) to service_role;
