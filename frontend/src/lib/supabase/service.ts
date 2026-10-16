/**
 * Calls Supabase's REST and Auth APIs with the project's secret key (SUPABASE_SECRET_KEY,
 * never NEXT_PUBLIC_), which bypasses row-level security. Server-only: import it from
 * Route Handlers, Server Components and Server Actions, never from client code.
 */
export async function supabaseAdmin<T>(path: string, init: { method?: string; body?: unknown; prefer?: string } = {}): Promise<T> {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL?.replace(/\/+$/, "");
  const key = process.env.SUPABASE_SECRET_KEY;
  if (!url || !key) throw new Error("SUPABASE_SECRET_KEY is not set on the server.");
  const headers: Record<string, string> = { apikey: key, "Content-Type": "application/json" };
  // New sb_secret_ keys go in `apikey` only; legacy service_role JWTs also go in Authorization.
  if (!key.startsWith("sb_")) headers.Authorization = `Bearer ${key}`;
  if (init.prefer) headers.Prefer = init.prefer;
  const res = await fetch(`${url}${path}`, {
    method: init.method ?? "POST",
    headers,
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
    cache: "no-store",
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const err = new Error(data?.message ?? data?.msg ?? data?.error_description ?? `Supabase error ${res.status}`);
    Object.assign(err, { status: res.status, code: data?.error_code ?? data?.code });
    throw err;
  }
  return data as T;
}
