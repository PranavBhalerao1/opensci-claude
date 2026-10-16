import { NextResponse } from "next/server";

import { getSubscriptionRow, stripe } from "@/lib/billing";
import { createClient } from "@/lib/supabase/server";

/** /billing/portal → Stripe's billing portal: change or cancel the plan, cards, invoices. */
export async function GET(request: Request) {
  const { origin } = new URL(request.url);
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.redirect(`${origin}/login?next=${encodeURIComponent("/billing/portal")}`, 303);

  try {
    const row = await getSubscriptionRow(user.id);
    if (!row?.stripe_customer_id) return NextResponse.redirect(`${origin}/pricing`, 303);
    const session = await stripe().billingPortal.sessions.create({
      customer: row.stripe_customer_id,
      return_url: `${origin}/`,
    });
    return NextResponse.redirect(session.url, 303);
  } catch (e) {
    console.error("billing portal failed", e);
    const message = "Billing is unavailable right now. Please try again in a moment.";
    return NextResponse.redirect(`${origin}/pricing?error=${encodeURIComponent(message)}`, 303);
  }
}
