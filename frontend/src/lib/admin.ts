import { createClient } from "@/lib/supabase/server";
import { supabaseAdmin } from "@/lib/supabase/service";

/**
 * Server-only helpers for /admin. They call Supabase with the project's secret key
 * (SUPABASE_SECRET_KEY, never NEXT_PUBLIC_), so import them only from Server
 * Components and Server Actions. Admins are the emails listed in ADMIN_EMAILS; if
 * that variable is unset, nobody is an admin.
 */

export interface PendingRequest {
  email: string;
  signed_up: string;
  invited: boolean;
  confirmed: boolean;
}

export interface Member {
  email: string;
  cap_usd: number | null;
  spent_usd: number;
  invited: boolean;
  joined: string;
}

export interface Subscriber {
  email: string;
  plan: string;
  status: string;
  credits_usd: number;
  spent_usd: number;
  period_end: string | null;
}

export interface LabInquiry {
  name: string;
  email: string;
  organization: string | null;
  team_size: string | null;
  message: string | null;
  created_at: string;
}

export interface WaitlistEntry {
  email: string;
  created_at: string;
}

/** The signed-in admin's email, or null when the visitor isn't an admin. */
export async function getAdminEmail(): Promise<string | null> {
  const admins = (process.env.ADMIN_EMAILS ?? "")
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);
  if (!admins.length) return null;
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  const email = user?.email?.toLowerCase();
  return email && admins.includes(email) ? email : null;
}

const rpc = <T>(fn: string, args: Record<string, unknown> = {}) => supabaseAdmin<T>(`/rest/v1/rpc/${fn}`, { body: args });

export const listPending = () => rpc<PendingRequest[]>("beta_requests");
export const listMembers = () => rpc<Member[]>("beta_members");
export const listWaitlist = () =>
  supabaseAdmin<WaitlistEntry[]>("/rest/v1/waitlist?select=email,created_at&order=created_at.desc&limit=500", {
    method: "GET",
  });

export const listSubscribers = () => rpc<Subscriber[]>("billing_subscribers");
export const listLabInquiries = () =>
  supabaseAdmin<LabInquiry[]>(
    "/rest/v1/lab_inquiries?select=name,email,organization,team_size,message,created_at&order=created_at.desc&limit=200",
    { method: "GET" },
  );

export const approve = (email: string, cap: number | null) =>
  rpc<string>("approve_beta", { p_email: email, p_cap_usd: cap });
export const revoke = (email: string) => rpc<string>("revoke_beta", { p_email: email });
export const setCap = (email: string, cap: number | null) =>
  rpc<string>("set_beta_cap", { p_email: email, p_cap_usd: cap });

/** Emails an invite (the account starts approved), then applies the cap. Existing accounts are just approved. */
export async function invite(email: string, cap: number | null): Promise<string> {
  let sent = true;
  try {
    await supabaseAdmin("/auth/v1/invite", { body: { email } });
  } catch (e) {
    const { status, code } = e as { status?: number; code?: string };
    if (status !== 422 && code !== "email_exists") throw e;
    sent = false;
  }
  const approved = await approve(email, cap);
  return sent ? `Invite sent. ${approved}` : `${email} already had an account. ${approved}`;
}
