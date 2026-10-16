"use client";

import { useEffect, useState } from "react";

import { PlanEditError, planApi, type PlanAudit, type PlanRun as PlanRunT, type PlanTask, type Project, type ResearchPlan } from "@/lib/api";
import { useAuth } from "@/lib/supabase/AuthProvider";

interface Props {
  project: Project;
  run: PlanRunT | null;
  revisions: number;
  onApprove: () => Promise<void>;
  onRetry: () => Promise<void>;
  onSaved: (run: PlanRunT) => void;
}

export default function PlanRun({ project, run, revisions, onApprove, onRetry, onSaved }: Props) {
  const plan = run?.status === "done" ? run.result?.plan : undefined;
  // A plan run is stale if it was drafted for a different gap than the chosen one.
  const current = plan && run?.result?.gap_id === project.chosen_gap?.id;
  const approved = Boolean(project.plan && project.plan.run_id === run?.id);
  const [editing, setEditing] = useState(false);
  const { session } = useAuth();

  return (
    <section className="mb-10">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">04 · Research plan</div>
      <div className="border border-ink">
        <div className="flex items-center justify-between border-b border-ink px-6 py-2.5 font-mono text-[10px] uppercase tracking-[0.16em]">
          <span>
            vague_research_plan.json{revisions > 1 ? ` · revision ${revisions}` : ""}
          </span>
          <span
            className={
              approved ? "bg-ink px-1.5 py-0.5 text-paper" : run?.status === "error" ? "underline" : "text-muted"
            }
          >
            {approved ? "Approved" : run?.status === "done" ? "Draft · review" : run?.status === "error" ? "Failed" : "Drafting"}
          </span>
        </div>

        {(!run || run.status === "running") && <Progress run={run} revising={revisions > 0} />}

        {run?.status === "error" && (
          <div className="flex items-center justify-between px-6 py-4">
            <span className="font-mono text-[12px]">{run.error}</span>
            <button onClick={onRetry} className="bg-ink px-4 py-2 text-[13px] text-paper">
              Retry
            </button>
          </div>
        )}

        {plan && current && !editing && run?.result?.audit && <AuditCard {...run.result.audit} />}
        {plan && current && !editing && <PlanDocument plan={plan} note={run?.result?.instruction} />}
        {plan && current && editing && (
          <JsonEditor
            projectId={project.id}
            plan={plan}
            onCancel={() => setEditing(false)}
            onSaved={(r) => {
              setEditing(false);
              onSaved(r);
            }}
          />
        )}

        {plan && current && !editing && (approved ? (
          <Approved project={project} onEdit={() => setEditing(true)} token={session?.access_token ?? null} />
        ) : (
          !project.autonomous && <ApproveBar onApprove={onApprove} onEdit={() => setEditing(true)} />
        ))}
      </div>
    </section>
  );
}

function Progress({ run, revising }: { run: PlanRunT | null; revising: boolean }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const elapsed = run ? Math.max(0, Math.round((now - new Date(run.started_at).getTime()) / 1000)) : 0;
  const phase = run?.phase ?? "starting";
  const steps = [
    {
      key: "drafting",
      label: revising ? "Revise plan" : "Draft plan",
      detail: revising ? "applying your change · under a minute" : "phases, tasks, data, evaluation · usually ~2 min",
    },
    { key: "validating", label: "Validate task graph", detail: "ids, dependencies, cycles" },
  ];
  const order = ["starting", "drafting", "validating", "repairing"];
  const at = Math.max(1, order.indexOf(phase));
  return (
    <div>
      <ol className="px-6 py-4">
        {steps.map((s, i) => {
          const idx = order.indexOf(s.key);
          const state = idx < at ? "done" : idx === at || (phase === "repairing" && s.key === "validating") ? "active" : "pending";
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

function PlanDocument({ plan, note }: { plan: ResearchPlan; note?: string }) {
  const tasks = plan.phases.flatMap((p) => p.tasks);
  const [hover, setHover] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const dependents = (id: string) => tasks.filter((t) => t.depends_on.includes(id)).map((t) => t.id);

  return (
    <div className="px-6 py-6">
      {note && (
        <p className="mb-4 border-l-2 border-ink bg-wash px-3 py-2 font-mono text-[11.5px] text-muted">
          Revised: {note}
        </p>
      )}
      <div className="flex flex-wrap gap-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
        <span className="border border-rule px-1.5 py-0.5">{plan.study_type.replace(/_/g, " ")}</span>
        <span className="border border-rule px-1.5 py-0.5">{plan.phases.length} phases</span>
        <span className="border border-rule px-1.5 py-0.5">{tasks.length} tasks</span>
      </div>
      <h2 className="mt-3 font-serif text-[26px] leading-tight tracking-tight">{plan.title}</h2>
      <blockquote className="mt-4 border-l-2 border-ink pl-4 font-serif text-[17px] italic leading-snug">
        {plan.research_question}
      </blockquote>
      <dl className="mt-4 grid gap-3 sm:grid-cols-2">
        <Hyp label="H₁ · Hypothesis" text={plan.hypothesis} />
        <Hyp label="H₀ · Null" text={plan.null_hypothesis} />
      </dl>

      <Section title="Objectives">
        <ol className="grid gap-1.5">
          {plan.objectives.map((o, i) => (
            <li key={o} className="flex gap-3 text-[13.5px] leading-relaxed">
              <span className="font-mono text-[11px] text-faint">{String(i + 1).padStart(2, "0")}</span>
              <span>{o}</span>
            </li>
          ))}
        </ol>
      </Section>

      <Section title="Background">
        <p className="text-[13.5px] leading-relaxed text-muted">{plan.background}</p>
      </Section>

      <Section title="Tasks">
        <div className="border border-rule">
          {plan.phases.map((ph) => (
            <div key={ph.id} className="border-b border-rule last:border-b-0">
              <div className="flex items-baseline gap-3 bg-wash px-4 py-2.5">
                <span className="font-mono text-[11px]">{ph.id}</span>
                <span className="font-serif text-[16px]">{ph.name}</span>
                <span className="hidden truncate text-[12px] text-muted md:inline">— {ph.goal}</span>
              </div>
              {ph.tasks.map((t) => (
                <TaskRow
                  key={t.id}
                  task={t}
                  open={open === t.id}
                  highlight={hover !== null && (hover === t.id || tasks.find((x) => x.id === hover)?.depends_on.includes(t.id))}
                  dependents={dependents(t.id)}
                  onToggle={() => setOpen(open === t.id ? null : t.id)}
                  onHover={setHover}
                />
              ))}
            </div>
          ))}
        </div>
        <p className="mt-1.5 font-mono text-[10.5px] text-faint">Hover a task to highlight what it depends on · click for details</p>
      </Section>

      <Section title="Data">
        <div className="grid gap-px border border-rule bg-rule">
          {plan.datasets.map((d) => (
            <div key={d.name} className="bg-paper px-4 py-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="text-[14px] font-medium">{d.name}</span>
                <span className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-muted">{d.access.replace(/_/g, " ")}</span>
              </div>
              <p className="mt-0.5 text-[13px] leading-relaxed text-muted">{d.description}</p>
              <p className="mt-1 text-[12.5px]">
                <span className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-faint">Role · </span>
                {d.role}
              </p>
              <p className="mt-0.5 truncate font-mono text-[11px] text-muted">
                {d.source.startsWith("http") ? (
                  <a href={d.source} target="_blank" rel="noreferrer" className="underline underline-offset-2">
                    {d.source}
                  </a>
                ) : (
                  d.source
                )}
              </p>
            </div>
          ))}
        </div>
      </Section>

      <div className="grid gap-x-8 sm:grid-cols-2">
        <Section title="Methods">
          <dl className="grid gap-2">
            {plan.methods.map((m) => (
              <div key={m.name} className="text-[13.5px] leading-relaxed">
                <dt className="inline font-medium">{m.name}. </dt>
                <dd className="inline text-muted">{m.purpose}</dd>
              </div>
            ))}
          </dl>
        </Section>
        <Section title="Baselines & controls">
          <Bullets items={plan.baselines} mark="≡" />
        </Section>
      </div>

      <Section title="Evaluation">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-[13px]">
            <thead>
              <tr className="font-mono text-[10px] uppercase tracking-[0.12em] text-faint">
                <th className="border-b border-ink py-1.5 pr-4 font-normal">Metric</th>
                <th className="border-b border-ink py-1.5 pr-4 font-normal">Definition</th>
                <th className="border-b border-ink py-1.5 font-normal">Success if</th>
              </tr>
            </thead>
            <tbody>
              {plan.metrics.map((m) => (
                <tr key={m.name} className="align-top">
                  <td className="border-b border-rule py-2 pr-4 font-medium">{m.name}</td>
                  <td className="border-b border-rule py-2 pr-4 text-muted">{m.definition}</td>
                  <td className="border-b border-rule py-2">{m.success_threshold}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-[13.5px] leading-relaxed">
          <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-faint">Validation · </span>
          {plan.validation_strategy}
        </p>
      </Section>

      <Section title="Success criteria">
        <Bullets items={plan.success_criteria} mark="✓" />
      </Section>

      <div className="grid gap-x-8 sm:grid-cols-2">
        <Section title="Compute">
          <p className="text-[13.5px] leading-relaxed">{plan.compute_estimate}</p>
        </Section>
        <Section title="Duration">
          <p className="text-[13.5px] leading-relaxed">{plan.duration_estimate}</p>
        </Section>
      </div>

      <Section title="Risks">
        <div className="grid gap-2">
          {plan.risks.map((r) => (
            <div key={r.risk} className="grid grid-cols-[64px_1fr] gap-3 text-[13.5px] leading-relaxed">
              <span className="pt-1 font-mono text-[10px] uppercase tracking-[0.1em] text-muted" title={`${r.likelihood} likelihood`}>
                {r.likelihood === "high" ? "●●●" : r.likelihood === "medium" ? "●●○" : "●○○"}
              </span>
              <span>
                {r.risk} <span className="text-muted">→ {r.mitigation}</span>
              </span>
            </div>
          ))}
        </div>
      </Section>

      <div className="grid gap-x-8 sm:grid-cols-2">
        <Section title="Deliverables">
          <Bullets items={plan.deliverables} mark="□" />
        </Section>
        <Section title="Open questions">
          <Bullets items={plan.open_questions} mark="?" />
        </Section>
      </div>
    </div>
  );
}

function TaskRow({
  task: t,
  open,
  highlight,
  dependents,
  onToggle,
  onHover,
}: {
  task: PlanTask;
  open: boolean;
  highlight: boolean | undefined;
  dependents: string[];
  onToggle: () => void;
  onHover: (id: string | null) => void;
}) {
  return (
    <div
      className={`border-t border-rule ${highlight ? "bg-wash" : ""}`}
      onMouseEnter={() => onHover(t.id)}
      onMouseLeave={() => onHover(null)}
    >
      <button onClick={onToggle} className="grid w-full grid-cols-[52px_1fr_auto] items-baseline gap-3 px-4 py-2.5 text-left">
        <span className="font-mono text-[11.5px]">{t.id}</span>
        <span className="min-w-0">
          <span className="text-[13.5px] leading-snug">{t.title}</span>
          <span className="mt-1 flex flex-wrap items-center gap-1.5 font-mono text-[10.5px] text-muted">
            <span className="uppercase tracking-[0.08em]">{t.kind.replace(/_/g, " ")}</span>
            {t.depends_on.length > 0 && (
              <>
                <span className="text-faint">· after</span>
                {t.depends_on.map((d) => (
                  <span key={d} className="border border-rule px-1">
                    {d}
                  </span>
                ))}
              </>
            )}
          </span>
        </span>
        <span className="font-mono text-[10.5px] text-muted" title="Effort">
          {t.effort}
        </span>
      </button>
      {open && (
        <div className="grid gap-3 px-4 pb-4 pl-[68px] text-[13px] leading-relaxed">
          <p>{t.description}</p>
          <IO label="Inputs" items={t.inputs} />
          <IO label="Outputs" items={t.outputs} />
          <IO label="Tools" items={t.tools_hint} />
          {dependents.length > 0 && <IO label="Unblocks" items={dependents} />}
        </div>
      )}
    </div>
  );
}

function IO({ label, items }: { label: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="flex flex-wrap items-baseline gap-1.5">
      <span className="w-16 font-mono text-[10px] uppercase tracking-[0.12em] text-faint">{label}</span>
      {items.map((i) => (
        <span key={i} className="border border-rule bg-paper px-1.5 py-px font-mono text-[11px]">
          {i}
        </span>
      ))}
    </div>
  );
}

function ApproveBar({ onApprove, onEdit }: { onApprove: () => Promise<void>; onEdit: () => void }) {
  const [saving, setSaving] = useState(false);
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-ink bg-wash px-6 py-4">
      <span className="text-[13px] text-muted">Want changes? Reply below, or edit the JSON directly.</span>
      <div className="flex gap-2">
        <button onClick={onEdit} className="border border-ink bg-paper px-4 py-2 text-[13px] hover:bg-ink hover:text-paper">
          Edit JSON
        </button>
        <button
          disabled={saving}
          onClick={async () => {
            setSaving(true);
            try {
              await onApprove();
            } finally {
              setSaving(false);
            }
          }}
          className="bg-ink px-5 py-2 text-[13px] text-paper disabled:opacity-25"
        >
          {saving ? "Exporting…" : "Approve & export →"}
        </button>
      </div>
    </div>
  );
}

function Approved({ project, onEdit, token }: { project: Project; onEdit: () => void; token: string | null }) {
  return (
    <div className="border-t border-ink bg-wash px-6 py-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
          {project.autonomous ? "Approved automatically" : "Approved"} ·{" "}
          {project.plan ? new Date(project.plan.approved_at).toLocaleString() : ""}
        </span>
        <div className="flex gap-2">
          <button onClick={onEdit} className="px-3 py-1.5 font-mono text-[11.5px] text-muted hover:text-ink">
            Edit JSON
          </button>
          {["vague_research_plan.json", "context.json"].map((f) => (
            <a
              key={f}
              href={planApi.fileUrl(project.id, f, token)}
              className="border border-ink bg-paper px-3 py-1.5 font-mono text-[11.5px] hover:bg-ink hover:text-paper"
            >
              ↓ {f}
            </a>
          ))}
        </div>
      </div>
      <p className="mt-3 text-[13px] leading-relaxed text-muted">
        Planning is complete. Next, the Blueprint Agent compiles this plan into{" "}
        <span className="font-mono text-[12px]">master_plan.json</span>: the exact agents, tools and dependencies the
        orchestrator will run. Reply below to revise the plan (this returns it to draft).
      </p>
    </div>
  );
}

function JsonEditor({
  projectId,
  plan,
  onCancel,
  onSaved,
}: {
  projectId: string;
  plan: ResearchPlan;
  onCancel: () => void;
  onSaved: (run: PlanRunT) => void;
}) {
  const [text, setText] = useState(() => JSON.stringify(plan, null, 2));
  const [errors, setErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    let data: unknown;
    try {
      data = JSON.parse(text);
    } catch (e) {
      setErrors([`Not valid JSON: ${(e as Error).message}`]);
      return;
    }
    setSaving(true);
    try {
      onSaved(await planApi.edit(projectId, data));
    } catch (e) {
      setErrors(e instanceof PlanEditError ? e.errors : [String(e)]);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="px-6 py-5">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        spellCheck={false}
        className="h-[60vh] w-full resize-y border border-ink bg-wash p-4 font-mono text-[12px] leading-relaxed outline-none"
      />
      {errors.length > 0 && (
        <ul className="mt-3 border border-ink px-4 py-3 font-mono text-[12px]">
          {errors.map((e) => (
            <li key={e}>✕ {e}</li>
          ))}
        </ul>
      )}
      <div className="mt-3 flex justify-end gap-2">
        <button onClick={onCancel} className="px-4 py-2 text-[13px] text-muted hover:text-ink">
          Cancel
        </button>
        <button onClick={save} disabled={saving} className="bg-ink px-5 py-2 text-[13px] text-paper disabled:opacity-25">
          {saving ? "Validating…" : "Save changes"}
        </button>
      </div>
    </div>
  );
}

function Hyp({ label, text }: { label: string; text: string }) {
  return (
    <div className="border border-rule px-3 py-2.5">
      <dt className="font-mono text-[10px] uppercase tracking-[0.12em] text-faint">{label}</dt>
      <dd className="mt-1 text-[13.5px] leading-relaxed">{text}</dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-7">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">{title}</div>
      {children}
    </div>
  );
}

function Bullets({ items, mark }: { items: string[]; mark: string }) {
  return (
    <ul className="grid gap-1.5">
      {items.map((it) => (
        <li key={it} className="flex gap-2.5 text-[13.5px] leading-relaxed">
          <span className="w-3 shrink-0 font-mono text-faint">{mark}</span>
          <span>{it}</span>
        </li>
      ))}
    </ul>
  );
}

/** The domain expert's check of the question against established theory, before approval. */
function AuditCard({ first, final, revised, stale }: { first: PlanAudit; final: PlanAudit; revised: boolean; stale?: boolean }) {
  const serious = (a: PlanAudit) => a.problems.filter((x) => x.severity !== "MINOR");
  const fixed = revised ? serious(first) : [];
  const open = serious(final);
  return (
    <div className="border-b border-ink px-6 py-4">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-faint">Expert check · {final.field}</span>
        <span className={`font-mono text-[10.5px] uppercase tracking-[0.1em] ${open.length ? "underline" : "text-muted"}`}>
          {stale ? "Of an earlier version" : open.length ? `${open.length} serious problem${open.length > 1 ? "s" : ""} open` : revised ? "Fixed before approval" : "Passed"}
        </span>
      </div>
      {final.contribution && <p className="text-[13.5px] leading-relaxed">{final.contribution}</p>}
      {fixed.length > 0 && (
        <details className="mt-2 text-[13px]">
          <summary className="cursor-pointer text-muted">The first draft had {fixed.length} serious problem{fixed.length > 1 ? "s" : ""}; the plan was revised</summary>
          <ul className="mt-1.5 grid gap-1.5">
            {fixed.map((x, i) => (
              <li key={i} className="leading-relaxed">
                <span className="font-mono text-[10.5px]">{x.severity} · {x.kind.replace(/_/g, " ")}</span> {x.problem}
              </li>
            ))}
          </ul>
        </details>
      )}
      {open.length > 0 && (
        <ul className="mt-2 grid gap-2 text-[13px]">
          {open.map((x, i) => (
            <li key={i} className="leading-relaxed">
              <span className="font-mono text-[10.5px]">{x.severity} · {x.kind.replace(/_/g, " ")}</span> {x.problem}
              <span className="text-muted"> → {x.fix}</span>
            </li>
          ))}
        </ul>
      )}
      {final.established_theory.length > 0 && (
        <details className="mt-2 text-[13px]">
          <summary className="cursor-pointer text-muted">Established theory considered</summary>
          <ul className="mt-1.5 grid list-disc gap-1 pl-5 leading-relaxed">
            {final.established_theory.map((t, i) => <li key={i}>{t}</li>)}
          </ul>
        </details>
      )}
    </div>
  );
}
