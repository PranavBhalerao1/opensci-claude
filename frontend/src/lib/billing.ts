import Stripe from "stripe";

import { CREDITS_PER_USD, planByLookupKey, type Plan } from "@/lib/plans";
import { supabaseAdmin } from "@/lib/supabase/service";

/**
 * Server-only Stripe helpers. Needs STRIPE_SECRET_KEY (and STRIPE_WEBHOOK_SECRET for
 * the webhook). The subscriptions table is written here and read by the backend,
 * which grants access and credits from it (backend/app/beta.py).
 */

let client: Stripe | null = null;

export function stripe(): Stripe {
  const key = process.env.STRIPE_SECRET_KEY;
  if (!key) throw new Error("STRIPE_SECRET_KEY is not set on the server.");
  client ??= new Stripe(key);
  return client;
}

export interface SubscriptionRow {
  user_id: string;
  plan: string;
  status: string;
  credits_usd: number;
  period_start: string | null;
  period_end: string | null;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
}

export async function getSubscriptionRow(userId: string): Promise<SubscriptionRow | null> {
  const rows = await supabaseAdmin<SubscriptionRow[]>(
    `/rest/v1/subscriptions?user_id=eq.${encodeURIComponent(userId)}&select=*`,
    { method: "GET" },
  );
  return rows[0] ?? null;
}

async function findRowByCustomer(customerId: string): Promise<SubscriptionRow | null> {
  const rows = await supabaseAdmin<SubscriptionRow[]>(
    `/rest/v1/subscriptions?stripe_customer_id=eq.${encodeURIComponent(customerId)}&select=*`,
    { method: "GET" },
  );
  return rows[0] ?? null;
}

/** Statuses that still owe or hold a plan; anything else means the user can subscribe afresh. */
export const LIVE_STATUSES = new Set(["active", "trialing", "past_due", "unpaid", "incomplete"]);

const priceIds = new Map<string, string>();

export async function priceIdFor(plan: Plan): Promise<string> {
  const cached = priceIds.get(plan.lookupKey);
  if (cached) return cached;
  const { data } = await stripe().prices.list({ lookup_keys: [plan.lookupKey], active: true, limit: 1 });
  if (!data[0]) throw new Error(`No active Stripe price with lookup key ${plan.lookupKey}.`);
  priceIds.set(plan.lookupKey, data[0].id);
  return data[0].id;
}

const iso = (seconds: number | null | undefined) => (seconds ? new Date(seconds * 1000).toISOString() : null);

/** Mirrors a Stripe subscription into the subscriptions table. Returns what it did, for logs. */
export async function syncSubscription(sub: Stripe.Subscription): Promise<string> {
  const customerId = typeof sub.customer === "string" ? sub.customer : sub.customer.id;
  const existing = sub.metadata?.user_id ? null : await findRowByCustomer(customerId);
  const userId = sub.metadata?.user_id || existing?.user_id;
  if (!userId) return `skipped ${sub.id}: no user_id`;

  const current = existing ?? (await getSubscriptionRow(userId));
  // An old subscription ending must not overwrite a newer one the user has since started.
  if (current?.stripe_subscription_id && current.stripe_subscription_id !== sub.id && !LIVE_STATUSES.has(sub.status)) {
    return `skipped ${sub.id}: superseded by ${current.stripe_subscription_id}`;
  }

  const item = sub.items.data[0];
  const plan = planByLookupKey(item?.price.lookup_key);
  if (!plan) return `skipped ${sub.id}: unknown price ${item?.price.lookup_key ?? "?"}`;

  await supabaseAdmin("/rest/v1/subscriptions?on_conflict=user_id", {
    prefer: "resolution=merge-duplicates,return=minimal",
    body: {
      user_id: userId,
      plan: plan.id,
      status: sub.status,
      credits_usd: plan.credits / CREDITS_PER_USD,
      period_start: iso(item.current_period_start),
      period_end: iso(item.current_period_end),
      stripe_customer_id: customerId,
      stripe_subscription_id: sub.id,
      updated_at: new Date().toISOString(),
    },
  });
  return `${userId}: ${plan.id} ${sub.status}`;
}
