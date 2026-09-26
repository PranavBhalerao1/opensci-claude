"use client";

import { useEffect, useState } from "react";

import type { Gap, GapsRun as GapsRunT, LitPaper, Project } from "@/lib/api";

interface Props {
  project: Project;
  run: GapsRunT | null;
  papers: LitPaper[];
  onSelect: (gapId: string) => Promise<void>;
  onRegenerate: (feedback: string) => Promise<void>;
  onOpenPaper: (paperId: string) => void;
}

const SCORE_KEYS = ["novelty", "feasibility", "impact", "testability"] as const;

const NOVELTY: Record<Gap["novelty_check"]["status"], { mark: string; label: string }> = {
  novel: { mark: "●", label: "Novel" },
  partially_addressed: { mark: "◐", label: "Partially addressed" },
  already_done: { mark: "○", label: "Already done" },
  unchecked: { mark: "?", label: "Unchecked" },
};

export default function GapsRun({ project, run, papers, onSelect, onRegenerate, onOpenPaper }: Props) {
  const result = run?.status === "done" ? run.result : null;
  const chosen = project.chosen_gap?.run_id === run?.id ? project.chosen_gap?.id : undefined;
  const byId = new Map(papers.map((p) => [p.id, p]));

  return (
    <section className="mb-10">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">03 · Research gaps</div>
      <div className="border border-ink">
        <div className="flex items-center justify-between border-b border-ink px-6 py-2.5 font-mono text-[10px] uppercase tracking-[0.16em]">
          <span>{result ? `${result.gaps.length} candidates · novelty-checked` : "Gap analysis"}</span>
          <span
            className={
              run?.status === "done" ? "bg-ink px-1.5 py-0.5 text-paper" : run?.status === "error" ? "underline" : "text-muted"
            }
          >
            {run?.status === "done" ? (chosen ? "Gap chosen" : "Choose a gap") : run?.status === "error" ? "Failed" : "Running"}
          </span>
        </div>

        {(!run || run.status === "running") && <Progress run={run} />}

        {run?.status === "error" && (
          <div className="flex items-center justify-between px-6 py-4">
            <span className="font-mono text-[12px]">{run.error}</span>
            <button onClick={() => onRegenerate("")} className="bg-ink px-4 py-2 text-[13px] text-paper">
              Retry
            </button>
          </div>
        )}

        {result && (
          <>
            <p className="border-b border-rule px-6 py-3 text-[13px] leading-relaxed text-muted">
              Ranked by novelty (30%), feasibility (30%), impact (25%) and testability (15%). Novelty is re-scored after
              searching for prior work that may already answer each question.
              {result.feedback && <span className="mt-1 block text-ink">Steered by: “{result.feedback}”</span>}
            </p>
            {result.gaps.map((g, i) => (
              <GapCard
                key={g.id}
                gap={g}
                rank={i + 1}
                recommended={g.id === result.recommended}
                chosen={chosen === g.id}
                dimmed={Boolean(chosen) && chosen !== g.id}
                selectable={!project.autonomous && chosen !== g.id}
                switching={Boolean(chosen)}
                autoChosen={project.autonomous}
                byId={byId}
                onSelect={onSelect}
                onOpenPaper={onOpenPaper}
              />
            ))}
            {!project.autonomous && <Steer onRegenerate={onRegenerate} chosen={Boolean(chosen)} />}
          </>
        )}
      </div>

    </section>
  );
}

function Progress({ run }: { run: GapsRunT | null }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const phase = run?.phase ?? "starting";
  const c = run?.counts ?? {};
  const order = ["starting", "proposing", "checking", "ranking"];
  const at = order.indexOf(phase);
  const elapsed = run ? Math.max(0, Math.round((now - new Date(run.started_at).getTime()) / 1000)) : 0;
  const counts = c as Record<string, number | undefined>;

  const steps = [
    { key: "proposing", label: "Propose candidates", detail: "deep reasoning over every paper’s notes · usually 2–4 min" },
    {
      key: "checking",
      label: "Check novelty",
      detail: counts.proposed ? `${counts.checked ?? 0}/${counts.proposed} gaps searched for prior work` : "",
    },
    { key: "ranking", label: "Score & rank", detail: "" },
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
        {run?.log.length ? ` · ${run.log[run.log.length - 1].text}` : ""}
      </div>
    </div>
  );
}

function GapCard({
  gap: g,
  rank,
  recommended,
  chosen,
  dimmed,
  selectable,
  switching,
  autoChosen,
  byId,
  onSelect,
  onOpenPaper,
}: {
  gap: Gap;
  rank: number;
  recommended: boolean;
  chosen: boolean;
  dimmed: boolean;
  selectable: boolean;
  switching: boolean;
  autoChosen: boolean;
  byId: Map<string, LitPaper>;
  onSelect: (gapId: string) => Promise<void>;
  onOpenPaper: (paperId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const nov = NOVELTY[g.novelty_check.status];

  return (
    <article className={`border-b border-rule last:border-b-0 ${chosen ? "bg-wash" : ""} ${dimmed ? "opacity-45" : ""}`}>
      <div className="px-6 pt-5 pb-4">
        <div className="flex items-start gap-4">
          <span className="pt-1 font-mono text-[11px] text-faint">#{rank}</span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              {chosen && (
                <span className="bg-ink px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-paper">
                  {autoChosen ? "Chosen automatically" : "Chosen"}
                </span>
              )}
              {recommended && !chosen && (
                <span className="border border-ink px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em]">
                  Recommended
                </span>
              )}
              <span className="border border-rule px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                {g.gap_type.replace(/_/g, " ")}
              </span>
            </div>
            <h3 className="mt-2 font-serif text-[20px] leading-snug">{g.title}</h3>
            <p className="mt-2 border-l-2 border-ink pl-3 font-serif text-[15.5px] italic leading-snug">{g.question}</p>
          </div>
          <div className="text-right">
            <div className="font-mono text-[22px] leading-none">{g.overall.toFixed(2)}</div>
            <div className="mt-1 font-mono text-[9.5px] uppercase tracking-[0.14em] text-faint">of 5</div>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 pl-[44px] sm:grid-cols-4">
          {SCORE_KEYS.map((k) => (
            <div key={k} title={g.scores[k].why}>
              <div className="flex items-baseline justify-between font-mono text-[10px] uppercase tracking-[0.12em] text-faint">
                <span>{k}</span>
                <span className="text-ink">{g.scores[k].score}</span>
              </div>
              <div className="mt-1 flex gap-0.5">
                {[1, 2, 3, 4, 5].map((n) => (
                  <span key={n} className={`h-1.5 flex-1 ${n <= g.scores[k].score ? "bg-ink" : "bg-rule"}`} />
                ))}
              </div>
            </div>
          ))}
        </div>

        <p className="mt-4 pl-[44px] text-[13px] leading-relaxed">
          <span className="mr-2 font-mono">{nov.mark}</span>
          <span className="font-medium">{nov.label}.</span>{" "}
          <span className="text-muted">{g.novelty_check.explanation}</span>
        </p>

        <div className="mt-4 flex items-center justify-between pl-[44px]">
          <button
            onClick={() => setOpen(!open)}
            className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted underline-offset-4 hover:text-ink hover:underline"
          >
            {open ? "Hide details" : "Details, evidence & prior work"}
          </button>
          {selectable && (
            <button
              disabled={saving}
              onClick={async () => {
                setSaving(true);
                try {
                  await onSelect(g.id);
                } finally {
                  setSaving(false);
                }
              }}
              className={`px-4 py-2 text-[13px] disabled:opacity-25 ${
                switching ? "border border-ink bg-paper hover:bg-ink hover:text-paper" : "bg-ink text-paper"
              }`}
            >
              {saving ? "Choosing…" : switching ? "Pursue this instead" : "Pursue this gap →"}
            </button>
          )}
        </div>
      </div>

      {open && (
        <div className="grid gap-5 border-t border-dashed border-rule px-6 py-5 pl-[68px] text-[13.5px] leading-relaxed">
          <Field label="Why it’s open">{g.why_open}</Field>
          <Field label="Hypothesis">{g.hypothesis}</Field>
          <Field label="How we’d test it">{g.approach}</Field>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Data needed">{g.data_needed}</Field>
            <Field label="Compute needed">{g.compute_needed}</Field>
          </div>
          <div>
            <Label>Score rationale</Label>
            <dl className="grid gap-1">
              {SCORE_KEYS.map((k) => (
                <div key={k} className="flex gap-2">
                  <dt className="w-24 shrink-0 font-mono text-[11px] uppercase tracking-[0.1em] text-faint">{k}</dt>
                  <dd className="text-muted">{g.scores[k].why}</dd>
                </div>
              ))}
            </dl>
          </div>
          {g.risks.length > 0 && (
            <div>
              <Label>Risks</Label>
              <ul className="grid gap-1">
                {g.risks.map((r) => (
                  <li key={r} className="flex gap-2">
                    <span className="font-mono text-faint">!</span>
                    <span>{r}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div>
            <Label>Closest prior work</Label>
            {g.novelty_check.closest.length ? (
              <ul className="grid gap-2">
                {g.novelty_check.closest.map((c) => (
                  <li key={c.title}>
                    {c.url ? (
                      <a href={c.url} target="_blank" rel="noreferrer" className="underline underline-offset-2">
                        {c.title}
                      </a>
                    ) : (
                      c.title
                    )}{" "}
                    <span className="font-mono text-[11px] text-faint">
                      {c.year ?? ""}
                      {c.in_review ? " · in your review" : ""}
                    </span>
                    <div className="text-[12.5px] text-muted">{c.overlap}</div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted">None found.</p>
            )}
            {g.novelty_queries.length > 0 && (
              <p className="mt-2 font-mono text-[11px] text-faint">Searched: {g.novelty_queries.join(" · ")}</p>
            )}
          </div>
          {g.supporting_paper_ids.length > 0 && (
            <div>
              <Label>Motivating papers from your review</Label>
              <div className="grid gap-0.5">
                {g.supporting_paper_ids.map((id) => {
                  const p = byId.get(id);
                  return p ? (
                    <button
                      key={id}
                      onClick={() => onOpenPaper(id)}
                      className="truncate text-left text-[12.5px] text-muted underline decoration-rule underline-offset-2 hover:text-ink hover:decoration-ink"
                    >
                      {p.title} <span className="font-mono text-[11px] text-faint">{p.year}</span>
                    </button>
                  ) : null;
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </article>
  );
}

function Steer({ onRegenerate, chosen }: { onRegenerate: (feedback: string) => Promise<void>; chosen: boolean }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <div className="flex flex-wrap items-center gap-3 border-t border-ink bg-wash px-6 py-4">
      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-faint">
        {chosen ? "Want different options?" : "None fit?"}
      </span>
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Steer the search, e.g. “something I can run on a laptop” or “focus on designed proteins”"
        className="min-w-0 flex-1 border-b border-rule bg-transparent py-1 text-[13px] outline-none placeholder:text-faint focus:border-ink"
      />
      <button
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await onRegenerate(text);
          } finally {
            setBusy(false);
          }
        }}
        className="border border-ink bg-paper px-4 py-1.5 text-[13px] hover:bg-ink hover:text-paper disabled:opacity-25"
      >
        Regenerate gaps
      </button>
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">{children}</div>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <Label>{label}</Label>
      <p>{children}</p>
    </div>
  );
}
