import { NextResponse } from "next/server";

import { getSubscriptionRow, LIVE_STATUSES, priceIdFor, stripe } from "@/lib/billing";
import { planById } from "@/lib/plans";
import { createClient } from "@/lib/supabase/server";

/**
 * /billing/checkout?plan=light → Stripe Checkout for that plan. Signed-out visitors are
 * sent to /login first by the proxy and come back here. Someone who already has a plan
 * goes to the billing portal instead, where they can switch plans without paying twice.
 */
export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url);
  const fail = (message: string) =>
    NextResponse.redirect(`${origin}/pricing?error=${encodeURIComponent(message)}`, 303);

  const plan = planById(searchParams.get("plan"));
  if (!plan) return fail("Pick a plan to continue.");

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    const next = `/billing/checkout?plan=${plan.id}`;
    return NextResponse.redirect(`${origin}/login?next=${encodeURIComponent(next)}`, 303);
  }

  try {
    const row = await getSubscriptionRow(user.id);
    if (row?.stripe_subscription_id && LIVE_STATUSES.has(row.status)) {
      return NextResponse.redirect(`${origin}/billing/portal`, 303);
    }
    const session = await stripe().checkout.sessions.create({
      mode: "subscription",
      line_items: [{ price: await priceIdFor(plan), quantity: 1 }],
      ...(row?.stripe_customer_id ? { customer: row.stripe_customer_id } : { customer_email: user.email }),
      client_reference_id: user.id,
      metadata: { user_id: user.id, plan: plan.id },
      subscription_data: { metadata: { user_id: user.id, plan: plan.id } },
      allow_promotion_codes: true,
      success_url: `${origin}/billing/success?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${origin}/pricing`,
    });
    if (!session.url) return fail("Checkout couldn't start. Please try again.");
    return NextResponse.redirect(session.url, 303);
  } catch (e) {
    console.error("checkout failed", e);
    return fail("Checkout is unavailable right now. Please try again in a moment.");
  }
}
