"use client";

import { useEffect, useState } from "react";

const STAGES: [string, string][] = [
  ["Clarify", "Two questions asked · research brief written"],
  ["Literature", "Papers searched, screened and read · citation graph built"],
  ["Gaps", "Open problems ranked by novelty, feasibility and impact"],
  ["Plan", "Hypotheses, controls and success criteria drafted"],
  ["Blueprint", "Agents, tools, dependencies and budget specified"],
  ["Execution", "Agents writing code and running jobs on cloud GPUs"],
  ["Paper", "Claims audited · citations checked · PDF compiled"],
];

/** Fig. 1: an investigation stepping through the seven stages, on a loop. */
export default function InvestigationFigure() {
  const [step, setStep] = useState(0);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const t = setInterval(() => setStep((s) => (s + 1) % (STAGES.length + 2)), 1700);
    return () => clearInterval(t);
  }, []);
  const active = Math.min(step, STAGES.length);
  const done = active === STAGES.length;

  return (
    <figure className="w-full border border-ink bg-paper text-left">
      <div className="flex items-center justify-between border-b border-ink px-5 py-2.5 font-mono text-[10px] uppercase tracking-[0.14em]">
        <span>Fig. 1 · One question, start to finish</span>
        <span className="text-faint">{done ? "Complete" : "Autonomous mode"}</span>
      </div>
      <div className="grid md:grid-cols-[1fr_1.15fr]">
        <div className="flex flex-col justify-between border-ink px-6 py-8 max-md:border-b md:border-r">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-faint">Question</div>
            <p className="mt-3 font-serif text-[26px] leading-snug">
              “Does the timing of weight decay change when a network suddenly generalises, or only how much of it
              there is?”
            </p>
          </div>
          <div className="mt-8 font-mono text-[12px] text-muted">
            {done ? (
              <span className="text-ink">→ paper.pdf · research_package.zip</span>
            ) : (
              <span className="caret">{STAGES[active][1]}</span>
            )}
          </div>
        </div>
        <ol className="font-mono text-[12.5px]">
          {STAGES.map(([name], i) => {
            const state = i < active ? "done" : i === active ? "running" : "pending";
            return (
              <li
                key={name}
                className={`flex items-center justify-between border-b border-rule px-6 py-3 last:border-b-0 ${
                  state === "running" ? "bg-ink text-paper" : ""
                }`}
              >
                <span className="flex items-center gap-4">
                  <span className={state === "running" ? "text-paper/60" : "text-faint"}>
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <span className={state === "pending" ? "text-faint" : ""}>{name}</span>
                </span>
                <span className="text-[10px] uppercase tracking-[0.14em]">
                  {state === "done" ? "✓" : state === "running" ? "Running" : ""}
                </span>
              </li>
            );
          })}
        </ol>
      </div>
    </figure>
  );
}
