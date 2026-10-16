import type { Metadata } from "next";
import Link from "next/link";

import SubmitButton from "@/app/admin/SubmitButton";
import { SiteFooter, SiteHeader } from "@/components/Site";
import { LAB_FEATURES, PLANS } from "@/lib/plans";
import { contactLab } from "./actions";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "OpenScientist plans: Light at $80, Intensive at $350 and Ultra at $950 a month, each with monthly research credits. Labs and teams, contact us.",
  alternates: { canonical: "/pricing" },
};

const NOTES: [string, string][] = [
  ["Credits pay for the work", "Reading papers, running code, training models on cloud GPUs. Each step draws credits as it runs, and you always see your balance."],
  ["Renewed every month", "Your credits refill at the start of each billing period. Unused credits don't roll over."],
  ["Change or cancel any time", "Upgrading adds the bigger allowance straight away. Cancelling keeps your plan until the period ends."],
];

const LAB_MESSAGES: Record<string, [string, boolean]> = {
  sent: ["Thanks, we got your message and will reply within a couple of days.", true],
  invalid: ["Please add your name and a valid email.", false],
  failed: ["That didn't go through. Please try again in a moment.", false],
};

function Label({ children }: { children: React.ReactNode }) {
  return <div className="font-mono text-[11px] uppercase tracking-[0.16em] text-faint">{children}</div>;
}

function Features({ items, dark }: { items: string[]; dark?: boolean }) {
  return (
    <ul className={`mt-7 space-y-2.5 border-t pt-6 text-[14px] leading-snug ${dark ? "border-paper/25" : "border-rule"}`}>
      {items.map((f) => (
        <li key={f} className="flex gap-3">
          <span className={`font-mono ${dark ? "text-paper/50" : "text-faint"}`}>—</span>
          <span>{f}</span>
        </li>
      ))}
    </ul>
  );
}

const input =
  "w-full border border-ink bg-paper px-3 py-2.5 text-[15px] outline-none placeholder:text-faint focus:bg-wash";

export default async function PricingPage({ searchParams }: PageProps<"/pricing">) {
  const { error, lab } = await searchParams;
  const labMessage = typeof lab === "string" ? LAB_MESSAGES[lab] : undefined;

  return (
    <div className="flex min-h-full flex-col bg-paper text-ink">
      <section className="graph-paper relative">
        <SiteHeader />
        <div className="mx-auto flex max-w-6xl flex-col items-center px-6 pt-14 pb-16 text-center">
          <Label>Pricing</Label>
          <h1 className="mt-6 max-w-4xl font-serif text-[76px] leading-[1] tracking-[-0.02em] max-md:text-[52px] max-sm:text-[40px]">
            Pay for the <span className="italic">research</span>, not the seat.
          </h1>
          <p className="mt-7 max-w-xl text-[17px] leading-relaxed text-muted">
            Every plan runs the full investigation, from question to paper. Plans differ in how many credits you get
            each month.
          </p>
        </div>
      </section>

      <section className="mx-auto w-full max-w-6xl px-6 pb-24">
        {typeof error === "string" && (
          <div className="mb-6 border border-ink bg-ink px-4 py-3 text-[14px] text-paper">{error}</div>
        )}
        <div className="grid border-t border-l border-ink md:grid-cols-2 lg:grid-cols-4">
          {PLANS.map((plan) => {
            const featured = plan.id === "intensive";
            return (
              <div
                key={plan.id}
                className={`relative flex flex-col border-r border-b border-ink px-6 py-8 ${featured ? "bg-ink text-paper" : ""}`}
              >
                <div className="flex items-center justify-between">
                  <span className={`font-mono text-[11px] uppercase tracking-[0.16em] ${featured ? "text-paper/60" : "text-faint"}`}>
                    {plan.name}
                  </span>
                  {featured && (
                    <span className="-my-1 border border-paper/40 px-2 py-0.5 font-mono text-[9px] uppercase leading-none tracking-[0.14em]">
                      Most chosen
                    </span>
                  )}
                </div>
                <div className="mt-6 flex items-baseline gap-1.5">
                  <span className="font-serif text-[56px] leading-none tracking-tight">${plan.price}</span>
                  <span className={`font-mono text-[11px] ${featured ? "text-paper/60" : "text-faint"}`}>/ month</span>
                </div>
                <p className={`mt-4 min-h-[44px] text-[14px] leading-relaxed ${featured ? "text-paper/75" : "text-muted"}`}>
                  {plan.tagline}
                </p>
                <Link
                  href={`/billing/checkout?plan=${plan.id}`}
                  prefetch={false}
                  className={`mt-6 block px-4 py-3 text-center font-mono text-[11px] uppercase tracking-[0.12em] transition-opacity hover:opacity-85 ${
                    featured ? "bg-paper text-ink" : "bg-ink text-paper"
                  }`}
                >
                  Choose {plan.name} →
                </Link>
                <Features items={plan.features} dark={featured} />
              </div>
            );
          })}
          <div className="flex flex-col border-r border-b border-ink bg-wash px-6 py-8">
            <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-faint">Lab</span>
            <div className="mt-6 font-serif text-[56px] leading-none tracking-tight">
              <span className="italic">Custom</span>
            </div>
            <p className="mt-4 min-h-[44px] text-[14px] leading-relaxed text-muted">
              For labs, departments and R&amp;D teams.
            </p>
            <a
              href="#lab"
              className="mt-6 block border border-ink bg-paper px-4 py-3 text-center font-mono text-[11px] uppercase tracking-[0.12em] transition-colors hover:bg-ink hover:text-paper"
            >
              Contact us →
            </a>
            <Features items={LAB_FEATURES} />
          </div>
        </div>
        <p className="mt-4 font-mono text-[11px] text-faint">Prices in USD. Taxes may apply. Billed monthly.</p>

        <div className="mt-16 grid gap-px border border-ink bg-ink md:grid-cols-3">
          {NOTES.map(([title, text], i) => (
            <div key={title} className="bg-paper px-7 py-8">
              <div className="font-mono text-[11px] text-faint">{String(i + 1).padStart(2, "0")}</div>
              <h3 className="mt-4 font-serif text-[24px] leading-snug">{title}</h3>
              <p className="mt-3 text-[14px] leading-relaxed text-muted">{text}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="lab" className="scroll-mt-6 border-t border-ink bg-wash">
        <div className="mx-auto grid max-w-6xl gap-12 px-6 py-24 md:grid-cols-2">
          <div>
            <Label>Lab plan</Label>
            <h2 className="mt-4 font-serif text-[48px] leading-[1.05] tracking-tight max-md:text-[36px]">
              A scientist for <span className="italic">every</span> PI.
            </h2>
            <p className="mt-5 max-w-md text-[16px] leading-relaxed text-muted">
              Tell us about your team and the research you want to run. We&apos;ll set up pooled credits, invoicing
              and onboarding to fit.
            </p>
          </div>
          <div>
            {labMessage && (
              <div
                className={`mb-5 border border-ink px-4 py-3 text-[14px] ${labMessage[1] ? "bg-paper" : "bg-ink text-paper"}`}
              >
                {labMessage[1] ? "✓ " : ""}
                {labMessage[0]}
              </div>
            )}
            {lab !== "sent" && (
              <form action={contactLab} className="space-y-3">
                <div className="grid gap-3 sm:grid-cols-2">
                  <input name="name" required placeholder="Name" autoComplete="name" className={input} />
                  <input name="email" type="email" required placeholder="Work email" autoComplete="email" className={input} />
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <input name="organization" placeholder="Lab or organization" autoComplete="organization" className={input} />
                  <select name="team_size" defaultValue="" className={input}>
                    <option value="" disabled>
                      Team size
                    </option>
                    {["2–5", "6–20", "21–100", "100+"].map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </div>
                <textarea name="message" rows={4} placeholder="What do you want to research?" className={input} />
                <div className="flex justify-end">
                  <SubmitButton>Send →</SubmitButton>
                </div>
              </form>
            )}
          </div>
        </div>
      </section>

      <div className="border-t border-rule">
        <SiteFooter />
      </div>
    </div>
  );
}
