"use client";

import { useEffect, useState } from "react";

// Copy of the workspace ReportRun for the demo film: the PDF frame is replaced by an inline
// preview and downloads point nowhere, so nothing reaches the backend.
import { reviewBadge, type Project, type ReportRun as ReportRunT } from "@/lib/api";
import { PaperPreview } from "./overlays";

interface Props {
  project: Project;
  run: ReportRunT | null;
  onStart: () => Promise<void>;
  onOpenFiles: (path?: string) => void;
  /** The paper's pages; the heatwave film's paper when omitted. */
  paper?: React.ReactNode;
}

const VERDICT: Record<string, string> = {
  supported: "Hypothesis supported",
  not_supported: "Hypothesis not supported",
  inconclusive: "Inconclusive",
  mixed: "Mixed evidence",
};

export default function ReportRun({ project, run, onStart, onOpenFiles, paper }: Props) {
  const r = run?.status === "done" ? run.result : null;
  const file = (p: string) => `#${p}`;
  const reviewed = reviewBadge(project);
  // With the scientific review on, the independent judge replaces the claims audit.
  const judged = Boolean(project.settings?.refinement?.enabled || project.review?.status);

  return (
    <section className="mb-10">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">07 · Report</div>
      <div className="border border-ink">
        <div className="flex items-center justify-between border-b border-ink px-6 py-2.5 font-mono text-[10px] uppercase tracking-[0.16em]">
          <span>Consolidation &amp; paper</span>
          <span className="flex items-center gap-2">
            {r?.files.pdf && (
              <span className={reviewed.tone === "ok" ? "bg-ink px-1.5 py-0.5 text-paper" : "border border-ink px-1.5 py-0.5"}>
                {reviewed.label}
              </span>
            )}
            <span className={r?.files.pdf ? "bg-ink px-1.5 py-0.5 text-paper" : "text-muted"}>
              {r ? (r.files.pdf ? "Paper ready" : "Written · no PDF") : run?.status === "error" ? "Failed" : run ? "Writing" : "Not started"}
            </span>
          </span>
        </div>

        {!run && (
          <div className="flex items-center justify-between gap-4 px-6 py-5">
            <p className="text-[13.5px] leading-relaxed text-muted">
              Consolidate every result, check and log into findings with evidence, then write and compile a
              conference-style paper with verified citations.
            </p>
            <Start onStart={onStart} label="Write the report →" />
          </div>
        )}
        {run?.status === "running" && <Progress run={run} />}
        {run?.status === "error" && (
          <div className="flex items-center justify-between gap-4 px-6 py-4">
            <span className="font-mono text-[12px]">{run.error}</span>
            <Start onStart={onStart} label="Retry" />
          </div>
        )}

        {r && (
          <div className="px-6 py-6">
            <h2 className="font-serif text-[24px] leading-tight">{r.scaffold.title}</h2>
            <p className="mt-2 text-[14px] leading-relaxed text-muted">{r.scaffold.one_sentence_summary}</p>

            <div className="mt-5 border border-ink px-4 py-3">
              <div className="font-mono text-[10px] uppercase tracking-[0.14em]">{VERDICT[r.scaffold.hypothesis_verdict]}</div>
              <p className="mt-1 text-[13.5px] leading-relaxed">{r.scaffold.verdict_explanation}</p>
            </div>

            <Section title={`Findings · ${r.scaffold.findings.length}`}>
              <ol className="grid gap-3">
                {r.scaffold.findings.map((f, i) => (
                  <li key={f.claim} className="grid grid-cols-[28px_1fr] gap-2 text-[13.5px] leading-relaxed">
                    <span className="font-mono text-[11px] text-faint">F{i + 1}</span>
                    <div>
                      <p>{f.claim}</p>
                      <p className="mt-0.5 font-mono text-[10.5px] uppercase tracking-[0.1em] text-muted">
                        {f.strength} · {f.relation}
                      </p>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {f.evidence.map((e) => (
                          <span key={e} className="border border-rule px-1.5 py-px font-mono text-[10.5px] text-muted">
                            {e}
                          </span>
                        ))}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            </Section>

            {r.scaffold.success_criteria.length > 0 && (
              <Section title="Success criteria">
                <div className="grid gap-1.5">
                  {r.scaffold.success_criteria.map((c) => (
                    <div key={c.criterion} className="grid grid-cols-[72px_1fr] gap-3 text-[13px] leading-relaxed">
                      <span className="font-mono text-[10.5px] uppercase tracking-[0.1em]">{c.status.replace("_", " ")}</span>
                      <span>
                        {c.criterion} <span className="text-muted">— {c.evidence}</span>
                      </span>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            <Section title="Integrity">
              <div className="grid gap-2 text-[13px] leading-relaxed">
                {r.citations.available === 0 ? (
                  <p>
                    <span className="font-mono">–</span> Citations: this project has no literature review, so the paper
                    cites nothing.
                  </p>
                ) : (
                  <p>
                    <span className="font-mono">{r.citations.unknown.length ? "✕" : "✓"}</span> Citations:{" "}
                    {r.citations.used.length} of {r.citations.available} reviewed papers cited
                    {r.citations.unknown.length
                      ? `; not from the review: ${r.citations.unknown.join(", ")}`
                      : ", all from the literature review"}
                    .
                  </p>
                )}
                {judged ? (
                  <p>
                    <span className="font-mono">→</span> Claims: checked by the independent scientific review below.
                  </p>
                ) : r.audit.length === 0 ? (
                  <p>
                    <span className="font-mono">✓</span> Claims audit: no statements disagree with the evidence.
                  </p>
                ) : (
                  <div>
                    <p>
                      <span className="font-mono">!</span> Claims audit found {r.audit.length} issue(s):
                    </p>
                    <ul className="mt-1 grid gap-1 pl-5">
                      {r.audit.map((a) => (
                        <li key={a.claim} className="list-disc">
                          <span className="font-mono text-[10.5px] uppercase">{a.severity}</span> “{a.claim}” —{" "}
                          <span className="text-muted">{a.problem}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </Section>

            {r.files.pdf && (
              <Section title="Paper">
                <div className="flex justify-center border border-ink bg-wash py-8">{paper ?? <PaperPreview />}</div>
              </Section>
            )}

            <div className="mt-6 flex flex-wrap gap-2 font-mono text-[11.5px]">
              {r.files.pdf && <Download href={file("paper/paper.pdf")} label="paper.pdf" />}
              {r.files.tex && <Download href={file("paper/paper.tex")} label="paper.tex" />}
              <Download href={file("paper/references.bib")} label="references.bib" />
              <Download href={file("paper/scaffold.json")} label="scaffold.json" />
              <Download href={"#package"} label="research package (.zip)" strong />
              <button onClick={() => onOpenFiles()} className="px-3 py-1.5 text-muted hover:text-ink">
                Browse workspace
              </button>
            </div>

            {(r.scaffold.limitations.length > 0 || r.scaffold.deviations.length > 0) && (
              <div className="mt-6 grid gap-x-8 sm:grid-cols-2">
                <Section title="Limitations">
                  <List items={r.scaffold.limitations} />
                </Section>
                <Section title="Deviations from plan">
                  <List items={r.scaffold.deviations.length ? r.scaffold.deviations : ["None"]} />
                </Section>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function Progress({ run }: { run: ReportRunT }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const elapsed = Math.max(0, Math.round((now - new Date(run.started_at).getTime()) / 1000));
  const order = ["starting", "consolidating", "writing", "auditing"];
  const at = order.indexOf(run.phase);
  const steps = [
    { key: "consolidating", label: "Consolidate", detail: "findings, evidence, verdict, outline" },
    { key: "writing", label: "Write & compile", detail: "LaTeX paper → PDF, by the Report Agent" },
    { key: "auditing", label: "Audit", detail: "citations and claims vs evidence" },
  ];
  return (
    <div>
      <ol className="px-6 py-4">
        {steps.map((s, i) => {
          const idx = order.indexOf(s.key);
          const state = idx < at ? "done" : idx === at || (at <= 0 && i === 0) ? "active" : "pending";
          return (
            <li key={s.key} className="flex items-baseline gap-4 py-1.5">
              <span className="w-5 font-mono text-[11px] text-faint">{String(i + 1).padStart(2, "0")}</span>
              {state === "done" ? (
                <span className="h-2.5 w-2.5 shrink-0 bg-ink" />
              ) : state === "active" ? (
                <span className="relative flex h-2.5 w-2.5 shrink-0">
                  <span className="absolute inline-flex h-full w-full animate-ping bg-ink opacity-40" />
                  <span className="relative inline-flex h-2.5 w-2.5 bg-ink" />
                </span>
              ) : (
                <span className="h-2.5 w-2.5 shrink-0 border border-rule" />
              )}
              <span className={`w-40 text-[14px] ${state === "pending" ? "text-faint" : ""}`}>{s.label}</span>
              <span className="font-mono text-[12px] text-muted">{state === "pending" ? "" : s.detail}</span>
            </li>
          );
        })}
      </ol>
      <div className="border-t border-rule bg-wash px-6 py-2.5 font-mono text-[11.5px] text-muted">
        {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")} elapsed
        {run.log.length ? ` · ${run.log[run.log.length - 1].text}` : ""}
      </div>
    </div>
  );
}

function Start({ onStart, label }: { onStart: () => Promise<void>; label: string }) {
  const [busy, setBusy] = useState(false);
  return (
    <button
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          await onStart();
        } finally {
          setBusy(false);
        }
      }}
      className="shrink-0 bg-ink px-4 py-2 text-[13px] text-paper disabled:opacity-25"
    >
      {busy ? "Starting…" : label}
    </button>
  );
}

function Download({ href, label, strong }: { href: string; label: string; strong?: boolean }) {
  return (
    <a
      href={href}
      className={`border border-ink px-3 py-1.5 ${strong ? "bg-ink text-paper" : "bg-paper hover:bg-ink hover:text-paper"}`}
    >
      ↓ {label}
    </a>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-6">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">{title}</div>
      {children}
    </div>
  );
}

function List({ items }: { items: string[] }) {
  return (
    <ul className="grid gap-1.5">
      {items.map((it) => (
        <li key={it} className="flex gap-2.5 text-[13px] leading-relaxed">
          <span className="font-mono text-faint">·</span>
          <span>{it}</span>
        </li>
      ))}
    </ul>
  );
}
