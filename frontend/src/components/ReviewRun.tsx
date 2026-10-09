"use client";

import { useState } from "react";

import { reviewApi, reviewBadge, type Project, type ReviewIteration, type ReviewView, type Run } from "@/lib/api";
import { useAuth } from "@/lib/supabase/AuthProvider";

interface Props {
  project: Project;
  review: ReviewView;
  enabled: boolean;
  run: Run | null;
  onAction: (action: "start" | "resume" | "stop") => Promise<void>;
}

const DECISION: Record<ReviewIteration["decision"], string> = {
  approved: "Approved",
  repair: "Repair",
  repair_gates: "Rebuild paper",
  unresolved: "Unresolved",
  budget_exhausted: "Budget used",
  review_failed: "Review failed",
};

const LEVEL: Record<NonNullable<ReviewIteration["level"]>, string> = {
  report: "manuscript only",
  execution: "re-ran tasks",
  blueprint: "amended blueprint",
  plan: "revised plan",
};

const STEP: Record<string, string> = {
  review: "Independent review",
  repair: "Planning Agent choosing fixes",
  execute: "Re-running invalidated tasks",
  report: "Rewriting the paper",
};

export default function ReviewRun({ project, review, enabled, run, onAction }: Props) {
  const { session } = useAuth();
  const token = session?.access_token ?? null;
  const status = review.status;
  const badge = reviewBadge(project);
  const iterations = review.iterations ?? [];
  const latest = iterations[iterations.length - 1];
  const live = Object.values(review.live ?? {}).some(Boolean);
  const active = status === "reviewing" || status === "repairing";
  const rounds = iterations.filter(
    (it) => it.n >= (review.session_first_iteration ?? 1) && (it.decision === "repair" || it.decision === "repair_gates"),
  ).length;
  const file = (name: string, iteration?: number) => reviewApi.fileUrl(project.id, name, token, iteration);

  return (
    <section className="mb-10">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">08 · Scientific review</div>
      <div className="border border-ink">
        <div className="flex items-center justify-between border-b border-ink px-6 py-2.5 font-mono text-[10px] uppercase tracking-[0.16em]">
          <span>Independent judge &amp; repair loop</span>
          <span className={badge.tone === "ok" ? "bg-ink px-1.5 py-0.5 text-paper" : badge.tone === "warn" ? "border border-ink px-1.5 py-0.5" : "text-muted"}>
            {badge.label}
          </span>
        </div>

        {!status && (
          <div className="flex items-center justify-between gap-4 px-6 py-5">
            <p className="text-[13.5px] leading-relaxed text-muted">
              {enabled
                ? "The paper will be reviewed by an independent model reviewer once it is written."
                : "Have an independent reviewer check the paper against its data, code, figures and citations, and repair what it finds by re-running only the affected work."}
            </p>
            <Button onClick={() => onAction("start")} label="Run scientific review →" strong />
          </div>
        )}

        {status && (
          <div className="px-6 py-5">
            {active && (
              <div className="flex items-baseline gap-3 text-[14px]">
                <span className="relative flex h-2.5 w-2.5 shrink-0">
                  <span className="absolute inline-flex h-full w-full animate-ping bg-ink opacity-40" />
                  <span className="relative inline-flex h-2.5 w-2.5 bg-ink" />
                </span>
                <span>{STEP[review.step ?? "review"] ?? "Working"}</span>
                <span className="font-mono text-[11.5px] text-muted">
                  round {rounds} of {review.max_rounds} · ${review.spent_usd.toFixed(2)} of ${review.max_usd?.toFixed(2)}
                  {run?.status === "running" && run.log.length ? ` · ${run.log[run.log.length - 1].text}` : ""}
                </span>
              </div>
            )}

            {!active && (
              <div className="border border-ink px-4 py-3">
                <div className="font-mono text-[10px] uppercase tracking-[0.14em]">{badge.label}</div>
                <p className="mt-1 text-[13.5px] leading-relaxed">
                  {review.outcome?.reason ?? review.attention ?? ""}
                </p>
                <p className="mt-1 font-mono text-[11px] text-muted">
                  {iterations.length} review{iterations.length === 1 ? "" : "s"} · {rounds} repair round
                  {rounds === 1 ? "" : "s"} · ${review.spent_usd.toFixed(2)} spent on refinement
                </p>
              </div>
            )}

            <div className="mt-4 flex flex-wrap gap-2 font-mono text-[11.5px]">
              {(status === "review_failed" || status === "attention") && !live && (
                <Button onClick={() => onAction("resume")} label="Resume" strong />
              )}
              {(active || status === "attention" || status === "review_failed") && (
                <Button onClick={() => onAction("stop")} label="Stop review" />
              )}
              {!active && status !== "attention" && status !== "review_failed" && (
                <Button onClick={() => onAction("start")} label={review.stale ? "Review the new version" : "Review again"} />
              )}
              <a href={file("REVIEW.md")} className="border border-ink px-3 py-1.5 hover:bg-ink hover:text-paper">
                ↓ REVIEW.md
              </a>
              <a href={file("HISTORY.md")} className="border border-ink px-3 py-1.5 hover:bg-ink hover:text-paper">
                ↓ HISTORY.md
              </a>
            </div>

            {review.outcome && (review.outcome.unresolved.length > 0 || review.outcome.open_concerns.length > 0 || review.outcome.needs_human.length > 0) && (
              <div className="mt-6 grid gap-x-8 sm:grid-cols-3">
                <Group title="Unresolved" items={review.outcome.unresolved.map((u) => `${u.severity}: ${u.title}`)} />
                <Group title="Disclosed concerns" items={review.outcome.open_concerns.map((u) => u.title)} />
                <Group title="Needs a human decision" items={review.outcome.needs_human.map((u) => u.title)} />
              </div>
            )}

            {latest && latest.issues.length > 0 && (
              <div className="mt-6">
                <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">
                  Review {latest.n} findings
                </div>
                <ol className="grid gap-2">
                  {latest.issues.map((i) => (
                    <li key={i.id} className="grid grid-cols-[64px_1fr] gap-3 text-[13px] leading-relaxed">
                      <span className="font-mono text-[10.5px] uppercase tracking-[0.1em]">{i.severity}</span>
                      <div>
                        <p className={i.blocking ? "" : "text-muted"}>{i.title}</p>
                        <p className="font-mono text-[10.5px] uppercase tracking-[0.08em] text-faint">
                          {i.category.replace(/_/g, " ")} · {i.blocking ? "blocking" : i.open_concern ? "open concern" : i.verification === "refuted" ? "refuted" : "not blocking"}
                          {i.tracking ? ` · ${i.tracking.status}` : ""}
                        </p>
                      </div>
                    </li>
                  ))}
                </ol>
              </div>
            )}

            {iterations.length > 0 && (
              <div className="mt-6">
                <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">Iterations</div>
                <div className="grid gap-1.5">
                  {iterations.map((it) => (
                    <div key={it.n} className="grid grid-cols-[28px_1fr_auto] items-baseline gap-3 text-[13px] leading-relaxed">
                      <span className="font-mono text-[11px] text-faint">R{it.n}</span>
                      <span>
                        {it.judged ? (it.verdict ?? "—").replace("_", " ") : "integrity gates failed"} →{" "}
                        <span className="font-mono text-[11px] uppercase">{DECISION[it.decision]}</span>
                        <span className="text-muted">
                          {it.judged ? ` · ${it.blocking.FATAL} fatal, ${it.blocking.MAJOR} major` : ""}
                          {it.level ? ` · ${LEVEL[it.level]}` : ""}
                          {it.rerun_tasks?.length ? ` (${it.rerun_tasks.join(", ")})` : ""}
                          {it.carried_over?.length ? ` · reused ${it.carried_over.length} finished tasks` : ""}
                          {it.objective_changes?.length ? ` · changed ${it.objective_changes.join(", ")}` : ""}
                        </span>
                      </span>
                      <span className="flex gap-2 font-mono text-[11px] text-muted">
                        <a href={file("mistakes.json", it.n)} className="hover:text-ink">mistakes.json</a>
                        <a href={file("paper.pdf", it.n)} className="hover:text-ink">pdf</a>
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <p className="mt-6 text-[12px] leading-relaxed text-faint">
              Approval means an independent model reviewer (the same model family that wrote the study) found no
              blocking scientific problems in the paper and its evidence, and the platform&apos;s integrity checks
              passed. It is a quality gate, not a guarantee of correctness.
            </p>
          </div>
        )}
      </div>
    </section>
  );
}

function Button({ onClick, label, strong }: { onClick: () => Promise<void>; label: string; strong?: boolean }) {
  const [busy, setBusy] = useState(false);
  return (
    <button
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          await onClick();
        } finally {
          setBusy(false);
        }
      }}
      className={`shrink-0 border border-ink px-3 py-1.5 font-mono text-[11.5px] disabled:opacity-25 ${
        strong ? "bg-ink text-paper" : "bg-paper hover:bg-ink hover:text-paper"
      }`}
    >
      {busy ? "…" : label}
    </button>
  );
}

function Group({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="mt-2">
      <div className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">{title}</div>
      <ul className="grid gap-1">
        {items.map((it) => (
          <li key={it} className="flex gap-2.5 text-[13px] leading-relaxed">
            <span className="font-mono text-faint">·</span>
            <span>{it}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
