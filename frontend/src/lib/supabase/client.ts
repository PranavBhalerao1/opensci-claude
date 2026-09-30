import { createBrowserClient } from "@supabase/ssr";

/** Browser-side Supabase client. Safe to call repeatedly; @supabase/ssr caches the instance. */
export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
  );
}
