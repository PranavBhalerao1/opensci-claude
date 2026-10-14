import { Suspense } from "react";

import { SiteFooter, SiteHeader } from "@/components/Site";
import Waitlist from "@/components/Waitlist";

export const metadata = { title: "Join the waitlist · OpenScientist" };

export default function WaitlistPage() {
  return (
    <div className="graph-paper relative flex min-h-full flex-col bg-paper text-ink">
      <SiteHeader />
      <main className="flex flex-1 flex-col items-center justify-center px-6 pb-24 text-center">
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
        <div className="mt-12 flex w-full justify-center">
          <Suspense>
            <Waitlist />
          </Suspense>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
