"use client";

import { useEffect, useMemo, useState } from "react";

import { planApi, type BlueprintRun as BlueprintRunT, type BpTask, type MasterPlan, type Project } from "@/lib/api";

interface Props {
  project: Project;
  run: BlueprintRunT | null;
  onStart: () => Promise<void>;
  onApprove: () => Promise<void>;
}

export default function BlueprintRun({ project, run, onStart, onApprove }: Props) {
  const result = run?.status === "done" ? run.result : null;
  const approved = Boolean(project.blueprint && project.blueprint.run_id === run?.id);

  return (
    <section className="mb-10">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">05 · Blueprint</div>
      <div className="border border-ink">
        <div className="flex items-center justify-between border-b border-ink px-6 py-2.5 font-mono text-[10px] uppercase tracking-[0.16em]">
          <span>master_plan.json</span>
          <span className={approved ? "bg-ink px-1.5 py-0.5 text-paper" : run?.status === "error" ? "underline" : "text-muted"}>
            {approved ? "Approved" : result ? "Draft · review" : run?.status === "error" ? "Failed" : run ? "Compiling" : "Not started"}
          </span>
        </div>

        {!run && (
          <div className="flex items-center justify-between gap-4 px-6 py-5">
            <p className="text-[13.5px] leading-relaxed text-muted">
              Compile the approved plan into an executable blueprint: the agent team, exact tasks, verified data sources
              and checkpoints.
            </p>
            <StartButton onStart={onStart} />
          </div>
        )}
        {run?.status === "running" && <Progress run={run} />}
        {run?.status === "error" && (
          <div className="flex items-center justify-between gap-4 px-6 py-4">
            <span className="font-mono text-[12px]">{run.error}</span>
            <StartButton onStart={onStart} label="Retry" />
          </div>
        )}
        {result && (
          <Document
            mp={result.master_plan}
            warnings={result.warnings}
            budget={result.budget}
            note={result.instruction}
          />
        )}
        {result &&
          (approved ? (
            <div className="border-t border-ink bg-wash px-6 py-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
                  {project.autonomous ? "Approved automatically" : "Approved"} ·{" "}
                  {project.blueprint ? new Date(project.blueprint.approved_at).toLocaleString() : ""}
                </span>
                <a
                  href={planApi.fileUrl(project.id, "master_plan.json")}
                  className="border border-ink bg-paper px-3 py-1.5 font-mono text-[11.5px] hover:bg-ink hover:text-paper"
                >
                  ↓ master_plan.json
                </a>
              </div>
              <p className="mt-3 text-[13px] leading-relaxed text-muted">
                Ready to execute. The orchestrator will run these agents and tasks in the project workspace — that is
                the next build step. Reply below to revise the blueprint.
              </p>
            </div>
          ) : (
            !project.autonomous && <ApproveBar onApprove={onApprove} />
          ))}
      </div>
    </section>
  );
}

function StartButton({ onStart, label = "Compile blueprint →" }: { onStart: () => Promise<void>; label?: string }) {
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

function Progress({ run }: { run: BlueprintRunT }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const elapsed = Math.max(0, Math.round((now - new Date(run.started_at).getTime()) / 1000));
  const order = ["starting", "resolving", "compiling", "validating", "repairing"];
  const at = order.indexOf(run.phase);
  const steps = [
    { key: "resolving", label: "Locate data sources", detail: "web search for every dataset in the plan" },
    { key: "compiling", label: "Compile agents & tasks", detail: "exact steps, inputs/outputs, checks · a few minutes" },
    { key: "validating", label: "Validate", detail: "tools, runtime, data flow, cycles, budget" },
  ];
  return (
    <div>
      <ol className="px-6 py-4">
        {steps.map((s, i) => {
          const idx = order.indexOf(s.key);
          const state =
            idx < at && !(s.key === "validating" && run.phase === "repairing")
              ? "done"
              : idx === at || (s.key === "validating" && run.phase === "repairing") || (at <= 0 && i === 0)
                ? "active"
                : "pending";
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
              <span className={`w-44 text-[14px] ${state === "pending" ? "text-faint" : ""}`}>{s.label}</span>
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

function Document({
  mp,
  warnings,
  budget,
  note,
}: {
  mp: MasterPlan;
  warnings: string[];
  budget: { llm_usd: number; gpu_hours: number };
  note?: string;
}) {
  const [selected, setSelected] = useState<string | null>(mp.tasks[0]?.id ?? null);
  const task = mp.tasks.find((t) => t.id === selected);
  const agents = new Map(mp.agents.map((a) => [a.id, a]));
  const stats: [string, string][] = [
    ["Agents", String(mp.agents.length)],
    ["Tasks", String(mp.tasks.length)],
    ["LLM est.", `$${mp.llm_usd_estimate.toFixed(2)} / ${budget.llm_usd}`],
    ["Compute est.", `${mp.compute_hours_estimate} h`],
    ["Checkpoints", String(mp.checkpoints.length)],
  ];

  return (
    <div className="px-6 py-6">
      {note && (
        <p className="mb-4 border-l-2 border-ink bg-wash px-3 py-2 font-mono text-[11.5px] text-muted">Revised: {note}</p>
      )}
      <h2 className="font-serif text-[24px] leading-tight">{mp.title}</h2>
      <p className="mt-2 text-[13.5px] leading-relaxed text-muted">{mp.summary}</p>

      <dl className="mt-5 grid grid-cols-2 border border-rule sm:grid-cols-5">
        {stats.map(([k, v]) => (
          <div key={k} className="border-b border-r border-rule px-3 py-2.5 sm:border-b-0 sm:last:border-r-0">
            <dd className="font-mono text-[15px] leading-none">{v}</dd>
            <dt className="mt-1 font-mono text-[9.5px] uppercase tracking-[0.12em] text-faint">{k}</dt>
          </div>
        ))}
      </dl>

      {warnings.length > 0 && (
        <div className="mt-5 border border-ink px-4 py-3">
          <div className="font-mono text-[10px] uppercase tracking-[0.14em]">Needs attention · {warnings.length}</div>
          <ul className="mt-2 grid gap-1">
            {warnings.map((w) => (
              <li key={w} className="flex gap-2 text-[13px] leading-relaxed">
                <span className="font-mono">!</span>
                <span>{w}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <Section title="Task graph">
        <Dag mp={mp} selected={selected} onSelect={setSelected} />
        {task && <TaskDetail task={task} agentName={agents.get(task.agent)?.name ?? task.agent} />}
      </Section>

      <Section title="Agent team">
        <div className="grid gap-px border border-rule bg-rule sm:grid-cols-2">
          {mp.agents.map((a) => (
            <div key={a.id} className="bg-paper p-4">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-[14px] font-medium">
                  <span className="mr-2 font-mono text-[11px] text-faint">{a.id}</span>
                  {a.name}
                </span>
                <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">{a.model_tier}</span>
              </div>
              <p className="mt-1.5 text-[12.5px] leading-relaxed text-muted">{a.instructions}</p>
              <div className="mt-2 flex flex-wrap gap-1">
                {a.tools.map((t) => (
                  <span key={t} className="border border-rule px-1.5 py-px font-mono text-[10.5px]">
                    {t}
                  </span>
                ))}
              </div>
              <div className="mt-2 font-mono text-[10.5px] text-faint">
                Tasks: {mp.tasks.filter((t) => t.agent === a.id).map((t) => t.id).join(" · ")}
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Data sources">
        <div className="grid gap-2">
          {mp.datasets.map((d) => (
            <div key={d.id} className="grid grid-cols-[28px_1fr] gap-2 text-[13px] leading-relaxed">
              <span
                className="pt-0.5 font-mono text-[12px]"
                title={d.url ? (d.verified ? "URL reachable" : "URL did not respond") : "No source found"}
              >
                {d.url ? (d.verified ? "✓" : "✗") : "—"}
              </span>
              <div>
                <span className="font-mono text-[11px] text-faint">{d.id} </span>
                <span className="font-medium">{d.name}</span>
                <span className="text-muted"> · {d.format} · {d.license}</span>
                {d.url && (
                  <a href={d.url} target="_blank" rel="noreferrer" className="block truncate font-mono text-[11px] underline underline-offset-2">
                    {d.url}
                  </a>
                )}
                <div className="text-[12.5px] text-muted">
                  {d.access_method}
                  {d.notes ? ` — ${d.notes}` : ""}
                </div>
              </div>
            </div>
          ))}
        </div>
      </Section>

      <div className="grid gap-x-8 sm:grid-cols-2">
        <Section title="Environment">
          <div className="flex flex-wrap gap-1">
            {mp.python_packages.map((p) => (
              <span key={p} className="border border-rule px-1.5 py-px font-mono text-[11px]">
                {p}
              </span>
            ))}
          </div>
        </Section>
        <Section title="Human checkpoints">
          <ul className="grid gap-1.5">
            {mp.checkpoints.map((c) => (
              <li key={c.after_task + c.reason} className="text-[13px] leading-relaxed">
                <span className="font-mono text-[11px]">◆ after {c.after_task} </span>
                <span className="text-muted">{c.reason}</span>
              </li>
            ))}
          </ul>
        </Section>
      </div>

      {mp.execution_notes.length > 0 && (
        <Section title="Execution notes">
          <ul className="grid gap-1">
            {mp.execution_notes.map((n) => (
              <li key={n} className="flex gap-2 text-[13px] leading-relaxed">
                <span className="font-mono text-faint">·</span>
                <span>{n}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

const NODE_W = 58;
const NODE_H = 26;
const COL_W = 96;
const ROW_H = 44;

function Dag({ mp, selected, onSelect }: { mp: MasterPlan; selected: string | null; onSelect: (id: string) => void }) {
  const [hover, setHover] = useState<string | null>(null);
  const layout = useMemo(() => {
    const byId = new Map(mp.tasks.map((t) => [t.id, t]));
    const depth = new Map<string, number>();
    const visit = (id: string, trail: Set<string>): number => {
      if (depth.has(id)) return depth.get(id)!;
      if (trail.has(id)) return 0;
      trail.add(id);
      const t = byId.get(id);
      const d = t && t.depends_on.length ? 1 + Math.max(...t.depends_on.filter((x) => byId.has(x)).map((x) => visit(x, trail)), -1) : 0;
      depth.set(id, d);
      return d;
    };
    mp.tasks.forEach((t) => visit(t.id, new Set()));
    const cols = new Map<number, string[]>();
    for (const t of mp.tasks) cols.set(depth.get(t.id)!, [...(cols.get(depth.get(t.id)!) ?? []), t.id]);
    const pos = new Map<string, { x: number; y: number }>();
    const maxRows = Math.max(...[...cols.values()].map((c) => c.length));
    for (const [c, ids] of cols) {
      const offset = ((maxRows - ids.length) * ROW_H) / 2;
      ids.forEach((id, r) => pos.set(id, { x: 12 + c * COL_W, y: 16 + offset + r * ROW_H }));
    }
    return { pos, width: 24 + cols.size * COL_W, height: 24 + maxRows * ROW_H };
  }, [mp.tasks]);

  const checkpointed = new Set(mp.checkpoints.map((c) => c.after_task));
  const related = (id: string) => {
    if (!hover) return true;
    const t = mp.tasks.find((x) => x.id === hover);
    return id === hover || t?.depends_on.includes(id) || mp.tasks.find((x) => x.id === id)?.depends_on.includes(hover);
  };

  return (
    <div className="overflow-x-auto border border-rule">
      <svg width={layout.width} height={layout.height} role="img" aria-label="Task dependency graph" className="block">
        <defs>
          <pattern id="hatch" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="4" stroke="#0a0a0a" strokeWidth="1" strokeOpacity="0.25" />
          </pattern>
        </defs>
        {mp.tasks.flatMap((t) =>
          t.depends_on
            .filter((d) => layout.pos.has(d))
            .map((d) => {
              const a = layout.pos.get(d)!;
              const b = layout.pos.get(t.id)!;
              const on = hover && (hover === t.id || hover === d);
              const x1 = a.x + NODE_W;
              const y1 = a.y + NODE_H / 2;
              const x2 = b.x;
              const y2 = b.y + NODE_H / 2;
              const mx = (x1 + x2) / 2;
              return (
                <path
                  key={`${d}-${t.id}`}
                  d={`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`}
                  fill="none"
                  stroke="#0a0a0a"
                  strokeOpacity={on ? 0.8 : hover ? 0.06 : 0.25}
                  strokeWidth={on ? 1.2 : 0.8}
                />
              );
            }),
        )}
        {mp.tasks.map((t) => {
          const p = layout.pos.get(t.id)!;
          const blocked = t.compute.kind === "cuda_gpu" || t.human_required;
          const isSel = selected === t.id;
          return (
            <g
              key={t.id}
              transform={`translate(${p.x},${p.y})`}
              opacity={related(t.id) ? 1 : 0.2}
              onMouseEnter={() => setHover(t.id)}
              onMouseLeave={() => setHover(null)}
              onClick={() => onSelect(t.id)}
              className="cursor-pointer"
            >
              <title>{`${t.id} · ${t.title}${t.human_required ? " (needs a person)" : ""}${t.compute.kind === "cuda_gpu" ? " (needs CUDA)" : ""}`}</title>
              <rect
                width={NODE_W}
                height={NODE_H}
                fill={isSel ? "#0a0a0a" : blocked ? "url(#hatch)" : "#fff"}
                stroke="#0a0a0a"
                strokeWidth={1}
                strokeDasharray={blocked ? "3 2" : undefined}
              />
              <text x={NODE_W / 2} y={11} textAnchor="middle" className={`font-mono text-[10px] ${isSel ? "fill-paper" : "fill-ink"}`}>
                {t.id}
              </text>
              <text x={NODE_W / 2} y={21} textAnchor="middle" className={`font-mono text-[8px] ${isSel ? "fill-faint" : "fill-muted"}`}>
                {t.agent}
              </text>
              {checkpointed.has(t.id) && (
                <text x={NODE_W - 2} y={-3} textAnchor="end" className="fill-ink font-mono text-[10px]">
                  ◆
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function TaskDetail({ task: t, agentName }: { task: BpTask; agentName: string }) {
  return (
    <div className="border border-t-0 border-rule bg-wash px-4 py-4 text-[13px] leading-relaxed">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-serif text-[17px]">
          <span className="mr-2 font-mono text-[12px]">{t.id}</span>
          {t.title}
        </span>
        <span className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-muted">
          {t.agent} · {agentName}
        </span>
      </div>
      <p className="mt-1.5">{t.objective}</p>
      <ol className="mt-3 grid gap-1">
        {t.steps.map((s, i) => (
          <li key={i} className="flex gap-2.5">
            <span className="font-mono text-[11px] text-faint">{i + 1}.</span>
            <span>{s}</span>
          </li>
        ))}
      </ol>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div>
          <Label>Inputs</Label>
          {t.inputs.map((i) => (
            <div key={i.path + i.source} className="font-mono text-[11.5px]">
              {i.path} <span className="text-faint">← {i.source}</span>
            </div>
          ))}
        </div>
        <div>
          <Label>Outputs</Label>
          {t.outputs.map((o) => (
            <div key={o.path} className="font-mono text-[11.5px]" title={o.description}>
              {o.path} <span className="text-faint">· {o.format}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="mt-3">
        <Label>Acceptance checks</Label>
        {t.acceptance_checks.map((c) => (
          <div key={c} className="flex gap-2">
            <span className="font-mono text-faint">✓</span>
            <span>{c}</span>
          </div>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 font-mono text-[11px] text-muted">
        <span>compute: {t.compute.kind.replace("_", " ")} · ~{t.compute.est_minutes} min (timeout {t.compute.timeout_minutes})</span>
        <span>budget: ${t.max_cost_usd.toFixed(2)}</span>
        <span>retries: {t.retries}</span>
        <span>tools: {t.tools.join(", ")}</span>
        {t.human_required && <span className="text-ink">needs a person</span>}
      </div>
    </div>
  );
}

function ApproveBar({ onApprove }: { onApprove: () => Promise<void> }) {
  const [saving, setSaving] = useState(false);
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-ink bg-wash px-6 py-4">
      <span className="text-[13px] text-muted">Reply below to change the team, tasks or data sources.</span>
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
        {saving ? "Exporting…" : "Approve blueprint →"}
      </button>
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">{children}</div>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-7">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">{title}</div>
      {children}
    </div>
  );
}
