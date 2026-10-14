// OpenScientist landing page (v3, from the landing handoff). Signed-out visitors to "/"
// are rewritten here by src/lib/supabase/proxy.ts; signed-in users get the app at "/".
import Link from "next/link";
import { redirect } from "next/navigation";

import InvestigationFigure from "@/components/InvestigationFigure";
import { SiteFooter, SiteHeader } from "@/components/Site";

const METHOD: [string, string][] = [
  ["Clarify", "A few multiple-choice questions turn a loose idea into a precise research brief."],
  ["Literature", "Hundreds of papers searched, screened and read, then mapped into a citation graph."],
  ["Gaps", "Open problems ranked by novelty, feasibility and impact. You choose, or it does."],
  ["Plan", "Hypotheses, methods, controls and success criteria, written out for review."],
  ["Blueprint", "A machine spec: which agents, which tools, in what order, on what budget."],
  ["Execution", "Agents write code, install software, train models and run jobs on cloud GPUs."],
  ["Paper", "Results consolidated, claims audited, citations verified, LaTeX compiled to PDF."],
];

const PRINCIPLES: [string, string][] = [
  [
    "Any field",
    "Biology, physics, machine learning, economics. Agents find the databases, servers and software a question needs on their own.",
  ],
  [
    "Real compute",
    "Every investigation gets its own sandbox and environment, plus cloud GPUs that run in parallel and are metered by the second.",
  ],
  [
    "Guided or autonomous",
    "Approve every stage yourself, or let it run from question to paper. Switch at any point.",
  ],
  [
    "Verified, not vibes",
    "Each task is checked against the files it produced. Each claim in the paper is traced back to a result.",
  ],
];

const AUDIENCE: [string, string, string][] = [
  ["Researchers", "Run the study you never had the weeks for.", "Test a side hypothesis, replicate a result or scan a new field overnight."],
  ["Labs & R&D teams", "A tireless junior scientist for every PI.", "Parallel investigations with audit trails, budgets and checkpoints you control."],
  ["The curious", "No PhD required.", "Ask in plain words. Every step is explained, and nothing is hidden behind jargon."],
];

function Label({ children }: { children: React.ReactNode }) {
  return <div className="font-mono text-[11px] uppercase tracking-[0.16em] text-faint">{children}</div>;
}

export default async function Landing({ searchParams }: PageProps<"/welcome">) {
  // Referral links shared before the waitlist moved to /waitlist still count.
  const { ref } = await searchParams;
  if (typeof ref === "string" && ref) redirect(`/waitlist?ref=${encodeURIComponent(ref)}`);

  return (
    <div className="flex min-h-full flex-col bg-paper text-ink">
      {/* Hero */}
      <section className="graph-paper relative flex min-h-[min(92vh,900px)] flex-col">
        <SiteHeader />
        <div className="flex flex-1 flex-col items-center justify-center px-6 pb-20 text-center">
          <div className="border border-ink bg-paper px-3 py-1 font-mono text-[10px] uppercase tracking-[0.18em]">
            Private beta · 2026
          </div>
          <h1 className="mt-10 max-w-5xl font-serif text-[88px] leading-[0.98] tracking-[-0.02em] max-md:text-[56px] max-sm:text-[42px]">
            Every question
            <br />
            deserves a <span className="italic">scientist</span>.
          </h1>
          <p className="mt-8 max-w-xl text-[17px] leading-relaxed text-muted">
            Ask in plain words. Agents read the literature, run the experiments and write the paper.
          </p>
          <div className="mt-12 flex flex-wrap justify-center gap-3">
            <Link
              href="/waitlist"
              className="bg-ink px-7 py-3.5 font-mono text-[12px] uppercase tracking-[0.12em] text-paper transition-opacity hover:opacity-85"
            >
              Join the waitlist →
            </Link>
            <a
              href="/demo"
              className="border border-ink bg-paper px-7 py-3.5 font-mono text-[12px] uppercase tracking-[0.12em] transition-colors hover:bg-ink hover:text-paper"
            >
              Watch the demo
            </a>
          </div>
          <p className="mt-5 font-mono text-[11px] text-faint">
            Partner lab, beta tester or investor?{" "}
            <Link href="/login" className="text-muted underline underline-offset-2 hover:text-ink">
              Sign in
            </Link>
          </p>
        </div>
      </section>

      {/* Fig. 1 */}
      <section className="mx-auto w-full max-w-6xl px-6 pb-28">
        <InvestigationFigure />
        <div className="mt-4 flex justify-between gap-4 font-mono text-[11px] text-faint max-sm:flex-col">
          <span>An investigation, compressed. Each stage runs for minutes to days in practice.</span>
          <a href="/demo" className="text-muted underline underline-offset-2 hover:text-ink">
            Step inside a recorded swarm run →
          </a>
        </div>
      </section>

      {/* §1 Method */}
      <section id="method" className="scroll-mt-6 border-t border-ink">
        <div className="mx-auto max-w-6xl px-6 py-28">
          <Label>§1 · Method</Label>
          <h2 className="mt-4 max-w-3xl font-serif text-[52px] leading-[1.05] tracking-tight max-md:text-[38px]">
            Seven stages, from a question to a <span className="italic">paper</span>.
          </h2>
          <p className="mt-5 max-w-xl text-[16px] leading-relaxed text-muted">
            The full scientific method, carried out by a team of agents. You see every step and can step in at any of
            them.
          </p>
          <div className="mt-14 grid border-t border-l border-ink sm:grid-cols-2 lg:grid-cols-4">
            {METHOD.map(([name, text], i) => (
              <div key={name} className="border-r border-b border-ink px-6 py-7">
                <div className="font-mono text-[11px] text-faint">{String(i + 1).padStart(2, "0")}</div>
                <h3 className="mt-4 font-serif text-[28px] leading-none">{name}</h3>
                <p className="mt-3 text-[14px] leading-relaxed text-muted">{text}</p>
              </div>
            ))}
            <Link
              href="/waitlist"
              className="group flex flex-col justify-between border-r border-b border-ink bg-ink px-6 py-7 text-paper"
            >
              <div className="font-mono text-[11px] text-paper/50">08</div>
              <div>
                <h3 className="font-serif text-[28px] italic leading-none">Your question</h3>
                <p className="mt-3 font-mono text-[11px] uppercase tracking-[0.14em] text-paper/70 transition-colors group-hover:text-paper">
                  Join the waitlist →
                </p>
              </div>
            </Link>
          </div>
        </div>
      </section>

      {/* §2 Principles */}
      <section id="principles" className="scroll-mt-6 border-t border-ink bg-wash">
        <div className="mx-auto max-w-6xl px-6 py-28">
          <Label>§2 · Principles</Label>
          <h2 className="mt-4 max-w-3xl font-serif text-[52px] leading-[1.05] tracking-tight max-md:text-[38px]">
            Rigour you don’t have to <span className="italic">supply yourself</span>.
          </h2>
          <div className="mt-14 grid border-t border-l border-ink bg-paper md:grid-cols-2">
            {PRINCIPLES.map(([title, text], i) => (
              <div key={title} className="border-r border-b border-ink px-8 py-10">
                <div className="font-mono text-[11px] text-faint">{String(i + 1).padStart(2, "0")}</div>
                <h3 className="mt-4 font-serif text-[30px] leading-tight">{title}</h3>
                <p className="mt-3 max-w-md text-[15px] leading-relaxed text-muted">{text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* §3 Audience */}
      <section className="border-t border-ink">
        <div className="mx-auto max-w-6xl px-6 py-28">
          <Label>§3 · Who it’s for</Label>
          <h2 className="mt-4 max-w-3xl font-serif text-[52px] leading-[1.05] tracking-tight max-md:text-[38px]">
            Built for anyone with a <span className="italic">good question</span>.
          </h2>
          <div className="mt-14 grid gap-px border border-ink bg-ink md:grid-cols-3">
            {AUDIENCE.map(([who, line, text]) => (
              <div key={who} className="bg-paper px-7 py-9">
                <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-faint">{who}</div>
                <h3 className="mt-4 font-serif text-[26px] leading-snug">{line}</h3>
                <p className="mt-3 text-[14px] leading-relaxed text-muted">{text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Closing call to action */}
      <section className="graph-paper relative border-t border-ink">
        <div className="mx-auto flex max-w-6xl flex-col items-center px-6 py-32 text-center">
          <div className="border border-ink bg-paper px-3 py-1 font-mono text-[10px] uppercase tracking-[0.18em]">
            Early access opens in waves
          </div>
          <h2 className="mt-8 max-w-4xl font-serif text-[64px] leading-[1.02] tracking-tight max-md:text-[42px]">
            Your next question could be a <span className="italic">paper</span>.
          </h2>
          <Link
            href="/waitlist"
            className="mt-12 bg-ink px-8 py-4 font-mono text-[12px] uppercase tracking-[0.12em] text-paper transition-opacity hover:opacity-85"
          >
            Join the waitlist →
          </Link>
          <p className="mt-4 font-mono text-[11px] text-faint">Invite friends to move up the line.</p>
        </div>
      </section>

      <div className="border-t border-rule">
        <SiteFooter />
      </div>
    </div>
  );
}
