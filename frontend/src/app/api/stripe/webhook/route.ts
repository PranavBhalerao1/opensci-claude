import type Stripe from "stripe";

import { stripe, syncSubscription } from "@/lib/billing";

/**
 * Stripe → subscriptions table. Every event that can change a plan re-reads the
 * subscription from Stripe and mirrors it, so events arriving out of order or twice
 * still leave the latest state. Public (no session); the signature is the auth.
 */
const SUBSCRIPTION_EVENTS = new Set([
  "customer.subscription.created",
  "customer.subscription.updated",
  "customer.subscription.deleted",
  "customer.subscription.paused",
  "customer.subscription.resumed",
]);

export async function POST(request: Request) {
  const secret = process.env.STRIPE_WEBHOOK_SECRET;
  const signature = request.headers.get("stripe-signature");
  if (!secret || !signature) return new Response("Webhook not configured", { status: 400 });

  let event: Stripe.Event;
  try {
    event = await stripe().webhooks.constructEventAsync(await request.text(), signature, secret);
  } catch {
    return new Response("Bad signature", { status: 400 });
  }

  let subscriptionId: string | null = null;
  if (SUBSCRIPTION_EVENTS.has(event.type)) {
    subscriptionId = (event.data.object as Stripe.Subscription).id;
  } else if (event.type === "checkout.session.completed") {
    const s = event.data.object as Stripe.Checkout.Session;
    subscriptionId = typeof s.subscription === "string" ? s.subscription : (s.subscription?.id ?? null);
  } else if (event.type === "invoice.paid") {
    const sub = (event.data.object as Stripe.Invoice).parent?.subscription_details?.subscription;
    subscriptionId = typeof sub === "string" ? sub : (sub?.id ?? null);
  }
  if (!subscriptionId) return Response.json({ received: true, ignored: event.type });

  try {
    const sub = await stripe().subscriptions.retrieve(subscriptionId);
    const result = await syncSubscription(sub);
    console.log(`stripe ${event.type}: ${result}`);
    return Response.json({ received: true, result });
  } catch (e) {
    console.error(`stripe ${event.type} failed`, e);
    return new Response("Sync failed", { status: 500 }); // Stripe retries
  }
}
