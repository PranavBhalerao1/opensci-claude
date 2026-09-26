"use client";

import ReactMarkdown from "react-markdown";

import type { Literature, Project, Run } from "@/lib/api";

interface Props {
  project: Project;
  lit: Literature | null;
  onRetry: () => void;
  onOpenLibrary: (paperId?: string) => void;
}

type StepState = "done" | "active" | "pending" | "skipped";

const PHASE_ORDER = ["starting", "searching", "screening", "expanding", "reading", "linking", "synthesising", "done"];

function steps(run: Run | null, deep: boolean) {
  const c = run?.counts ?? {};
  const at = PHASE_ORDER.indexOf(run?.phase ?? "starting");
  const state = (phase: string): StepState => {
    const i = PHASE_ORDER.indexOf(phase);
    if (run?.status === "done") return phase === "expanding" && !deep ? "skipped" : "done";
    if (i < at) return phase === "expanding" && !deep ? "skipped" : "done";
    return i === at ? "active" : "pending";
  };
  return [
    {
      key: "searching",
      label: "Search",
      state: state("searching"),
      detail: c.found != null ? `${c.found} unique papers · ${c.queries_done ?? 0}/${c.queries_total ?? "?"} queries` : "",
    },
    {
      key: "screening",
      label: "Screen",
      state: state("screening"),
      detail: c.screened != null ? `${c.screened} screened → ${c.included ?? "…"} relevant` : c.candidates ? `${c.candidates} candidates` : "",
    },
    ...(deep
      ? [{ key: "expanding", label: "Follow citations", state: state("expanding"), detail: "" }]
      : []),
    {
      key: "reading",
      label: "Read & extract",
      state: state("reading"),
      detail: c.extracted != null ? `${c.extracted}/${c.included ?? "?"} papers` : "",
    },
    { key: "linking", label: "Link citations", state: state("linking"), detail: "" },
    { key: "synthesising", label: "Synthesise", state: state("synthesising"), detail: "" },
  ];
}

export default function LiteratureRun({ project, lit, onRetry, onOpenLibrary }: Props) {
  const run = lit?.run ?? null;
  const deep = (project.settings.citation_hops ?? 0) > 0;
  const overview = run?.result?.overview;
  const byId = new Map((lit?.papers ?? []).map((p) => [p.id, p]));

  return (
    <section className="mb-10">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">
        02 · Literature review
      </div>

      <div className="border border-ink">
        <div className="flex items-center justify-between border-b border-ink px-6 py-2.5 font-mono text-[10px] uppercase tracking-[0.16em]">
          <span>
            {project.settings.depth ?? "standard"} · up to {project.settings.max_papers ?? 100} papers
          </span>
          <span
            className={
              run?.status === "done" ? "bg-ink px-1.5 py-0.5 text-paper" : run?.status === "error" ? "underline" : "text-muted"
            }
          >
            {run?.status === "done" ? "Complete" : run?.status === "error" ? "Failed" : "Running"}
          </span>
        </div>

        <ol className="px-6 py-4">
          {steps(run, deep).map((s, i) => (
            <li key={s.key} className="flex items-baseline gap-4 py-1.5">
              <span className="w-5 font-mono text-[11px] text-faint">{String(i + 1).padStart(2, "0")}</span>
              <StepMark state={s.state} />
              <span className={`w-36 text-[14px] ${s.state === "pending" ? "text-faint" : ""}`}>{s.label}</span>
              <span className="font-mono text-[12px] text-muted">{s.state === "skipped" ? "—" : s.detail}</span>
            </li>
          ))}
        </ol>

        {run?.status === "running" && run.log.length > 0 && (
          <div className="border-t border-rule bg-wash px-6 py-3 font-mono text-[11.5px] leading-relaxed text-muted">
            {run.log.slice(-4).map((l) => (
              <div key={l.t + l.text}>
                <span className="text-faint">{new Date(l.t).toLocaleTimeString([], { hour12: false })}</span> {l.text}
              </div>
            ))}
          </div>
        )}

        {run?.status === "error" && (
          <div className="flex items-center justify-between border-t border-ink px-6 py-3">
            <span className="font-mono text-[12px]">{run.error}</span>
            <button onClick={onRetry} className="bg-ink px-4 py-2 text-[13px] text-paper">
              Retry
            </button>
          </div>
        )}

        {overview && (
          <div className="border-t border-ink px-6 py-6">
            <h3 className="font-serif text-[22px] leading-tight">State of the field</h3>
            <div className="prose-os mt-3 text-muted">
              <ReactMarkdown>{overview.summary}</ReactMarkdown>
            </div>

            <div className="mt-6 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">Themes</div>
            <div className="mt-2 grid gap-px border border-rule bg-rule sm:grid-cols-2">
              {overview.themes.map((t, i) => (
                <div key={t.name} className="bg-paper p-4">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="font-serif text-[16px] leading-snug">
                      <span className="mr-2 font-mono text-[11px] text-faint">T{i + 1}</span>
                      {t.name}
                    </span>
                    <span className="shrink-0 font-mono text-[11px] text-faint">{t.paper_ids.length} papers</span>
                  </div>
                  <p className="mt-1.5 text-[13px] leading-relaxed text-muted">{t.description}</p>
                  <div className="mt-2 grid gap-0.5">
                    {t.paper_ids.slice(0, 3).map((id) => {
                      const p = byId.get(id);
                      return p ? (
                        <button
                          key={id}
                          onClick={() => onOpenLibrary(id)}
                          className="truncate text-left text-[12px] text-muted underline decoration-rule underline-offset-2 hover:text-ink hover:decoration-ink"
                        >
                          {p.title}
                        </button>
                      ) : null;
                    })}
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-6 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">
              Open problems — where gaps hide
            </div>
            <ul className="mt-2 grid gap-1.5">
              {overview.open_problems.map((o) => (
                <li key={o} className="flex gap-2.5 text-[13.5px] leading-relaxed">
                  <span className="w-3 shrink-0 font-mono text-faint">?</span>
                  <span>{o}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {run?.status === "done" && (
          <div className="flex items-center justify-between border-t border-ink bg-wash px-6 py-3">
            <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
              {lit?.papers.length ?? 0} papers in the knowledge base
            </span>
            <button onClick={() => onOpenLibrary()} className="bg-ink px-4 py-2 text-[13px] text-paper">
              Open library &amp; graph →
            </button>
          </div>
        )}
      </div>

    </section>
  );
}

function StepMark({ state }: { state: StepState }) {
  if (state === "done") return <span className="h-2.5 w-2.5 shrink-0 bg-ink" aria-label="done" />;
  if (state === "active")
    return (
      <span className="relative flex h-2.5 w-2.5 shrink-0" aria-label="in progress">
        <span className="absolute inline-flex h-full w-full animate-ping bg-ink opacity-40" />
        <span className="relative inline-flex h-2.5 w-2.5 border border-ink bg-ink" />
      </span>
    );
  return <span className="h-2.5 w-2.5 shrink-0 border border-rule" aria-label={state} />;
}
