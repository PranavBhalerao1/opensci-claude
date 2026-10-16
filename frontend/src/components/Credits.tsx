import Link from "next/link";

import type { Me } from "@/lib/api";
import { planById, toCredits } from "@/lib/plans";

const fmt = (n: number) => n.toLocaleString("en-US");

function summary(me: Me) {
  const plan = planById(me.plan);
  const total = me.cap_usd === null ? null : toCredits(me.cap_usd);
  const left = me.remaining_usd === null ? null : toCredits(me.remaining_usd);
  const renews = me.period_end
    ? new Date(me.period_end).toLocaleDateString("en-US", { month: "short", day: "numeric" })
    : null;
  return { plan, total, left, renews, low: total !== null && left !== null && left <= total * 0.1 };
}

/** Plain <a>: /billing/* are route handlers that redirect to Stripe. */
function BillingLinks({ me, compact }: { me: Me; compact?: boolean }) {
  const { plan } = summary(me);
  const btn = compact
    ? "font-mono text-[10px] uppercase tracking-[0.12em] underline underline-offset-2 hover:text-ink"
    : "px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.12em] transition-colors";
  return (
    <>
      {plan && (
        <a href="/billing/portal" className={compact ? btn : `${btn} border border-rule text-muted hover:border-ink hover:text-ink`}>
          Manage
        </a>
      )}
      {plan?.id !== "ultra" && !me.unlimited && (
        <Link href="/pricing" className={compact ? btn : `${btn} bg-ink text-paper hover:opacity-85`}>
          Upgrade
        </Link>
      )}
    </>
  );
}

/** Credits block at the bottom of the sidebar. */
export function CreditsPanel({ me }: { me: Me }) {
  const { plan, total, left, renews, low } = summary(me);
  const label = me.unlimited ? "Team access" : plan ? `${plan.name} plan` : "Beta credits";
  return (
    <div className="border-t border-rule px-4 pt-3.5 pb-3">
      <div className="flex items-center justify-between gap-2">
        <span className="whitespace-nowrap font-mono text-[10px] uppercase tracking-[0.14em] text-faint">{label}</span>
        <span className="flex gap-1.5">
          <BillingLinks me={me} />
        </span>
      </div>
      {me.unlimited ? (
        <div className="mt-1.5 font-serif text-[20px] leading-none">Unlimited credits</div>
      ) : (
        <>
          <div className="mt-1.5 flex items-baseline gap-1.5">
            <span className={`font-serif text-[24px] leading-none ${low ? "italic" : ""}`}>{fmt(left ?? 0)}</span>
            <span className="font-mono text-[11px] text-faint">/ {fmt(total ?? 0)} credits</span>
          </div>
          <div className="mt-2 h-[3px] w-full bg-rule" aria-hidden>
            <div className="h-full bg-ink" style={{ width: `${total ? Math.min(100, ((left ?? 0) / total) * 100) : 0}%` }} />
          </div>
          <div className="mt-1.5 font-mono text-[10px] text-faint">
            {left === 0 ? "Out of credits" : low ? "Running low" : "Remaining"}
            {renews ? ` · renews ${renews}` : ""}
          </div>
        </>
      )}
    </div>
  );
}

/** One-line balance for the workspace header on small screens, where the sidebar is hidden. */
export function CreditsChip({ me }: { me: Me }) {
  const { left } = summary(me);
  return (
    <span className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted md:hidden">
      {me.unlimited ? "Unlimited" : `${fmt(left ?? 0)} credits`}
      <BillingLinks me={me} compact />
    </span>
  );
}
