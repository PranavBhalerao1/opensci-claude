"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import AuthShell from "@/components/auth/AuthShell";
import { meApi, type Me } from "@/lib/api";
import { planById, toCredits } from "@/lib/plans";

/**
 * Stripe Checkout returns here. The plan is switched on by Stripe's webhook, which can
 * land a few seconds after the redirect, so this waits for /api/me to show it.
 */
export default function BillingSuccess() {
  const [me, setMe] = useState<Me | null>(null);
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    let stop = false;
    const started = Date.now();
    const poll = async () => {
      const m = await meApi.get().catch(() => null);
      if (stop) return;
      if (m?.plan) return setMe(m);
      if (Date.now() - started > 45_000) setSlow(true);
      setTimeout(poll, 2000);
    };
    void poll();
    return () => {
      stop = true;
    };
  }, []);

  const plan = planById(me?.plan);
  if (me && plan) {
    return (
      <AuthShell title={`You're on ${plan.name}.`} subtitle="Thanks for subscribing. Your credits are ready.">
        <div className="border border-ink px-4 py-4">
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-faint">Credits this month</div>
          <div className="mt-1 font-serif text-[34px] leading-none">
            {toCredits(me.remaining_usd ?? me.cap_usd ?? 0).toLocaleString("en-US")}
          </div>
        </div>
        <Link
          href="/"
          className="mt-5 block bg-ink px-4 py-3 text-center font-mono text-[12px] uppercase tracking-[0.12em] text-paper hover:opacity-85"
        >
          Start researching →
        </Link>
      </AuthShell>
    );
  }

  return (
    <AuthShell title="Setting up your plan" subtitle="Payment received. This takes a few seconds.">
      <div className="font-mono text-[12px] text-faint">{slow ? "Still working on it…" : "Activating…"}</div>
      {slow && (
        <p className="mt-4 text-[14px] leading-relaxed text-muted">
          This is taking longer than usual. Your payment went through, and your plan will appear on your{" "}
          <Link href="/" className="text-ink underline underline-offset-2">
            dashboard
          </Link>{" "}
          as soon as it&apos;s active.
        </p>
      )}
    </AuthShell>
  );
}
