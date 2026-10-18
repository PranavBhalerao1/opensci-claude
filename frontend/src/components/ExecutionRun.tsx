"use client";

import { useEffect, useState } from "react";

import {
  executionApi,
  type AgentEvent,
  type Execution,
  type MasterPlan,
  type ModelPolicy,
  type Project,
  type TaskState,
} from "@/lib/api";

interface Props {
  project: Project;
  exec: Execution | null;
  mp: MasterPlan;
  onStart: (budget: number, policy: ModelPolicy) => Promise<void>;
  onPause: () => Promise<void>;
  onResume: (budget?: number) => Promise<void>;
  onCancel: () => Promise<void>;
  onTask: (taskId: string, action: "complete" | "skip", note?: string) => Promise<void>;
  onSecret: (name: string, value: string) => Promise<void>;
  onRequestChanges: (taskId: string, feedback: string) => Promise<void>;
  onOpenFiles: (path?: string) => void;
}

const MARK: Record<TaskState["status"], string> = {
  pending: "○",
  running: "◐",
  done: "●",
  failed: "✕",
  blocked: "⊘",
  human: "✋",
  skipped: "–",
  cancelled: "⊘",
};

const POLICIES: { key: ModelPolicy; label: string; note: string }[] = [
  { key: "default", label: "Default", note: "flagship for hard reasoning" },
  { key: "economy", label: "Economy", note: "no flagship model" },
  { key: "minimal", label: "Minimal", note: "cheapest; for quick tests" },
];

function statusLabel(exec: Execution | null): string {
  if (!exec?.run) return "Not started";
  if (exec.paused?.startsWith("checkpoint")) return "Paused · review";
  if (exec.paused?.startsWith("budget")) return "Paused · budget";
  if (exec.paused?.startsWith("beta_limit_reached")) return "Paused · out of credits";
  if (exec.paused?.startsWith("human")) return "Needs a person";
  if (exec.paused) return "Paused";
  if (exec.live) return "Running";
  if (exec.run.status === "error") return "Interrupted";
  const r = exec.run.result as { cancelled?: boolean; counts?: Record<string, number> } | null;
  if (r?.cancelled) return "Cancelled";
  const bad = (r?.counts?.failed ?? 0) + (r?.counts?.blocked ?? 0);
  return bad ? "Finished with issues" : "Complete";
}

export default function ExecutionRun(props: Props) {
  const { project, exec, mp } = props;
  const [open, setOpen] = useState<string | null>(null);
  const tasks = exec?.tasks ?? [];
  const byTask = new Map(tasks.map((t) => [t.task_id, t]));
  const done = tasks.filter((t) => t.status === "done" || t.status === "skipped").length;
  const label = statusLabel(exec);
  const started = Boolean(exec?.run);

  return (
    <section className="mb-10">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">06 · Execution</div>
      <div className="border border-ink">
        <div className="flex items-center justify-between border-b border-ink px-6 py-2.5 font-mono text-[10px] uppercase tracking-[0.16em]">
          <span>Workspace run</span>
          <span className={label === "Complete" ? "bg-ink px-1.5 py-0.5 text-paper" : label === "Running" ? "text-ink" : "text-muted"}>
            {label}
          </span>
        </div>

        {!started ? (
          <StartPanel project={project} mp={mp} onStart={props.onStart} />
        ) : (
          <>
            <Summary {...props} exec={exec!} done={done} />
            {exec!.paused && <PausedBanner exec={exec!} onResume={props.onResume} onOpenFiles={props.onOpenFiles} />}
            <Lanes mp={mp} byTask={byTask} onOpen={setOpen} />
            <div className="border-t border-ink">
              {mp.tasks.map((t) => {
                const st = byTask.get(t.id);
                return st ? (
                  <TaskRow
                    key={t.id}
                    projectId={project.id}
                    title={t.title}
                    agentName={mp.agents.find((a) => a.id === t.agent)?.name ?? t.agent}
                    st={st}
                    open={open === t.id}
                    onToggle={() => setOpen(open === t.id ? null : t.id)}
                    onTask={props.onTask}
                    onSecret={props.onSecret}
                    onRequestChanges={props.onRequestChanges}
                    onOpenFiles={props.onOpenFiles}
                  />
                ) : null;
              })}
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function StartPanel({ project, mp, onStart }: { project: Project; mp: MasterPlan; onStart: Props["onStart"] }) {
  const [budget, setBudget] = useState(project.settings.budget?.llm_usd ?? 15);
  const [policy, setPolicy] = useState<ModelPolicy>(project.settings.model_policy ?? "default");
  const [busy, setBusy] = useState(false);
  return (
    <div className="px-6 py-5">
      <p className="text-[13.5px] leading-relaxed text-muted">
        {mp.agents.length} agents will run {mp.tasks.length} tasks in this project’s sandboxed workspace. The blueprint
        estimates <span className="font-mono text-ink">${mp.llm_usd_estimate.toFixed(2)}</span> of model usage; execution
        pauses automatically when the budget is reached.
      </p>
      <div className="mt-4 flex flex-wrap items-end gap-4">
        <label className="grid gap-1">
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-faint">Budget (USD)</span>
          <input
            type="number"
            min={0.05}
            step={0.5}
            value={budget}
            onChange={(e) => setBudget(Number(e.target.value))}
            className="w-28 border border-ink bg-paper px-2 py-1.5 font-mono text-[13px] outline-none"
          />
        </label>
        <div className="grid gap-1">
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-faint">Models</span>
          <div className="flex border border-ink" role="radiogroup">
            {POLICIES.map((p) => (
              <button
                key={p.key}
                role="radio"
                aria-checked={policy === p.key}
                title={p.note}
                onClick={() => setPolicy(p.key)}
                className={`px-3 py-1.5 text-left ${policy === p.key ? "bg-ink text-paper" : "bg-paper hover:bg-wash"}`}
              >
                <span className="block text-[12.5px]">{p.label}</span>
                <span className={`block font-mono text-[9.5px] ${policy === p.key ? "text-faint" : "text-muted"}`}>{p.note}</span>
              </button>
            ))}
          </div>
        </div>
        <button
          disabled={busy || !(budget > 0)}
          onClick={async () => {
            setBusy(true);
            try {
              await onStart(budget, policy);
            } finally {
              setBusy(false);
            }
          }}
          className="ml-auto bg-ink px-5 py-2.5 text-[13px] text-paper disabled:opacity-25"
        >
          {busy ? "Starting…" : "Start execution →"}
        </button>
      </div>
    </div>
  );
}

function Summary({ exec, mp, done, onPause, onResume, onCancel, onOpenFiles }: Props & { exec: Execution; done: number }) {
  const pct = Math.min(100, (exec.spent / Math.max(exec.budget, 0.01)) * 100);
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-rule px-6 py-4">
      <div className="min-w-[180px] flex-1">
        <div className="flex justify-between font-mono text-[11px]">
          <span>
            {done} / {mp.tasks.length} tasks
          </span>
          <span className="text-muted">{exec.model_policy} models</span>
        </div>
        <div className="mt-1.5 flex gap-px">
          {mp.tasks.map((t) => {
            const st = exec.tasks.find((x) => x.task_id === t.id);
            const s = st?.status ?? "pending";
            return (
              <span
                key={t.id}
                title={`${t.id} · ${s}`}
                className={`h-2 flex-1 ${
                  s === "done" || s === "skipped"
                    ? "bg-ink"
                    : s === "running"
                      ? "animate-pulse bg-muted"
                      : s === "failed" || s === "blocked" || s === "cancelled"
                        ? "border border-ink bg-[repeating-linear-gradient(45deg,#0a0a0a_0_1px,transparent_1px_4px)]"
                        : s === "human"
                          ? "border border-dashed border-ink"
                          : "bg-rule"
                }`}
              />
            );
          })}
        </div>
      </div>
      <div className="min-w-[150px]">
        <div className="flex justify-between font-mono text-[11px]">
          <span>${exec.spent.toFixed(3)}</span>
          <span className="text-muted">of ${exec.budget.toFixed(2)}</span>
        </div>
        <div className="mt-1.5 h-2 bg-rule">
          <div className="h-2 bg-ink" style={{ width: `${pct}%` }} />
        </div>
      </div>
      <div className="flex gap-2 font-mono text-[11.5px]">
        <button onClick={() => onOpenFiles()} className="border border-ink px-3 py-1.5 hover:bg-ink hover:text-paper">
          Files
        </button>
        {exec.live && !exec.paused && (
          <button onClick={onPause} className="border border-ink px-3 py-1.5 hover:bg-ink hover:text-paper">
            Pause
          </button>
        )}
        {(exec.paused || (!exec.live && done < mp.tasks.length)) && (
          <button onClick={() => onResume()} className="border border-ink px-3 py-1.5 hover:bg-ink hover:text-paper">
            {exec.live ? "Resume" : "Run remaining"}
          </button>
        )}
        {exec.live && (
          <button onClick={onCancel} className="px-3 py-1.5 text-muted hover:text-ink">
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}

function PausedBanner({ exec, onResume, onOpenFiles }: Pick<Props, "onResume" | "onOpenFiles"> & { exec: Execution }) {
  const [budget, setBudget] = useState(Math.ceil(exec.budget * 2 * 100) / 100);
  const reason = exec.paused ?? "";
  const checkpoint = reason.startsWith("checkpoint:") ? reason.slice("checkpoint:".length) : null;
  return (
    <div className="border-b border-ink bg-wash px-6 py-4">
      {checkpoint ? (
        <>
          <div className="font-mono text-[10px] uppercase tracking-[0.14em]">◆ Checkpoint</div>
          <p className="mt-1 text-[13.5px] leading-relaxed">
            <span className="font-mono">{checkpoint.split(":")[0]}</span> finished.{" "}
            {checkpoint.split(":").slice(1).join(":").trim().replace(/[.!]?$/, ".")} Review the outputs, then continue —
            or open the task below and request changes.
          </p>
          <div className="mt-3 flex gap-2">
            <button onClick={() => onOpenFiles()} className="border border-ink bg-paper px-4 py-2 text-[13px] hover:bg-ink hover:text-paper">
              Review files
            </button>
            <button onClick={() => onResume()} className="bg-ink px-4 py-2 text-[13px] text-paper">
              Continue →
            </button>
          </div>
        </>
      ) : reason.startsWith("budget") ? (
        <>
          <div className="font-mono text-[10px] uppercase tracking-[0.14em]">Budget reached</div>
          <p className="mt-1 text-[13.5px]">{reason.replace("budget: ", "")}. Raise the budget to continue.</p>
          <div className="mt-3 flex items-center gap-2">
            <span className="font-mono text-[11px] text-muted">New budget $</span>
            <input
              type="number"
              step={0.5}
              value={budget}
              onChange={(e) => setBudget(Number(e.target.value))}
              className="w-24 border border-ink bg-paper px-2 py-1.5 font-mono text-[13px] outline-none"
            />
            <button onClick={() => onResume(budget)} className="bg-ink px-4 py-2 text-[13px] text-paper">
              Raise &amp; continue →
            </button>
          </div>
        </>
      ) : reason.startsWith("beta_limit_reached") ? (
        <>
          <div className="font-mono text-[10px] uppercase tracking-[0.14em]">Out of credits</div>
          <p className="mt-1 text-[13.5px]">
            You&apos;ve used this period&apos;s credits. Upgrade your plan, then continue. Running tasks finish; nothing
            new starts.
          </p>
          <div className="mt-3 flex gap-2">
            <a href="/pricing" className="border border-ink px-4 py-2 text-[13px] hover:bg-ink hover:text-paper">
              Upgrade
            </a>
            <button onClick={() => onResume()} className="bg-ink px-4 py-2 text-[13px] text-paper">
              Continue →
            </button>
          </div>
        </>
      ) : reason.startsWith("human") ? (
        <p className="text-[13.5px]">
          <span className="font-mono">✋</span> A task needs a person. Open it below and mark it done (with a note) or skip
          it.
        </p>
      ) : reason.startsWith("network") ? (
        <>
          <p className="text-[13.5px]">
            Paused: the model service was unavailable. It retries by itself every few minutes; nothing is spent while
            it waits.
          </p>
          <div className="mt-3">
            <button onClick={() => onResume()} className="bg-ink px-4 py-2 text-[13px] text-paper">
              Resume now →
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="text-[13.5px]">Paused. Running tasks finish; nothing new starts until you resume.</p>
          <div className="mt-3">
            <button onClick={() => onResume()} className="bg-ink px-4 py-2 text-[13px] text-paper">
              Resume →
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function Lanes({ mp, byTask, onOpen }: { mp: MasterPlan; byTask: Map<string, TaskState>; onOpen: (id: string) => void }) {
  return (
    <div className="grid gap-px bg-rule">
      {mp.agents.map((a) => {
        const mine = mp.tasks.filter((t) => t.agent === a.id);
        const live = mine.map((t) => byTask.get(t.id)).find((s) => s?.status === "running");
        return (
          <div key={a.id} className="bg-paper px-6 py-3">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
              <span className="w-48 shrink-0 text-[13px]">
                <span className="mr-2 font-mono text-[11px] text-faint">{a.id}</span>
                {a.name}
              </span>
              <div className="flex flex-wrap gap-1">
                {mine.map((t) => {
                  const s = byTask.get(t.id)?.status ?? "pending";
                  return (
                    <button
                      key={t.id}
                      onClick={() => onOpen(t.id)}
                      title={`${t.title} · ${s}`}
                      className={`border px-1.5 py-0.5 font-mono text-[11px] ${
                        s === "running" ? "border-ink bg-ink text-paper" : s === "done" ? "border-ink" : "border-rule text-muted"
                      }`}
                    >
                      {MARK[s]} {t.id}
                    </button>
                  );
                })}
              </div>
            </div>
            {live && (
              <div className="mt-2 border-l-2 border-ink pl-3 font-mono text-[11px] leading-relaxed text-muted">
                {live.events.slice(-4).map((e, i) => (
                  <div key={i} className="truncate">
                    <span className="text-faint">{e.sub ? `${e.sub} · ` : ""}step {e.step}</span> {e.tool ?? "note"}{" "}
                    <span className="text-ink">{(e.args ?? e.text ?? "").slice(0, 110)}</span>
                  </div>
                ))}
                {live.events.length === 0 && <div>starting {live.task_id}…</div>}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** A task's full agent log, fetched while its row is open (execution polls carry only a live
 * task's last few events) and again whenever the log changes. */
function useTaskLog(projectId: string, st: TaskState, open: boolean): AgentEvent[] {
  const [log, setLog] = useState<AgentEvent[] | null>(null);
  const seq = st.event_seq ?? st.events.length;
  // Polls from an older API carry the whole log already.
  const complete = st.event_seq === undefined;
  useEffect(() => {
    if (!open || complete) return;
    let cancelled = false;
    executionApi
      .events(projectId, st.task_id)
      .then((d) => !cancelled && setLog(d.events))
      .catch(() => {});
    return () => void (cancelled = true);
  }, [projectId, st.task_id, open, seq, complete]);
  return complete ? st.events : (log ?? st.events);
}

function TaskRow({
  projectId,
  title,
  agentName,
  st,
  open,
  onToggle,
  onTask,
  onSecret,
  onRequestChanges,
  onOpenFiles,
}: {
  projectId: string;
  title: string;
  agentName: string;
  st: TaskState;
  open: boolean;
  onToggle: () => void;
  onTask: Props["onTask"];
  onSecret: Props["onSecret"];
  onRequestChanges: Props["onRequestChanges"];
  onOpenFiles: Props["onOpenFiles"];
}) {
  const [change, setChange] = useState("");
  const [note, setNote] = useState("");
  const [secret, setSecret] = useState("");
  const events = useTaskLog(projectId, st, open);
  const steps = Math.max(st.event_count ?? 0, events.length);
  const credential = st.status === "human" ? /^Needs credential ([A-Z0-9_]+)/.exec(st.note ?? "")?.[1] : undefined;
  const duration =
    st.started_at && st.finished_at
      ? Math.round((new Date(st.finished_at).getTime() - new Date(st.started_at).getTime()) / 1000)
      : null;
  const actionable = st.status === "failed" || st.status === "human" || st.status === "blocked";

  return (
    <div className={`border-b border-rule last:border-b-0 ${open ? "bg-wash" : ""}`}>
      <button onClick={onToggle} className="grid w-full grid-cols-[20px_52px_1fr_auto] items-baseline gap-3 px-6 py-2.5 text-left hover:bg-wash">
        <span className={`font-mono text-[12px] ${st.status === "running" ? "animate-pulse" : ""}`}>{MARK[st.status]}</span>
        <span className="font-mono text-[11.5px]">{st.task_id}</span>
        <span className="min-w-0 truncate text-[13.5px]">{title}</span>
        <span className="font-mono text-[10.5px] text-muted">
          {st.status}
          {st.attempts > 1 ? ` · ${st.attempts} tries` : ""}
          {st.cost ? ` · $${st.cost.toFixed(3)}` : ""}
          {duration !== null ? ` · ${duration}s` : ""}
        </span>
      </button>
      {open && (
        <div className="grid gap-3 px-6 pb-4 pl-[102px] text-[13px] leading-relaxed">
          <div className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-faint">{agentName}</div>
          {st.summary && <p>{st.summary}</p>}
          {st.note && <p className="whitespace-pre-line border-l-2 border-ink pl-3 text-muted">{st.note}</p>}
          {st.artifacts.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {st.artifacts.map((a) => (
                <button
                  key={a}
                  onClick={() => onOpenFiles(a)}
                  className="border border-ink bg-paper px-1.5 py-px font-mono text-[11px] hover:bg-ink hover:text-paper"
                >
                  {a}
                </button>
              ))}
            </div>
          )}
          {st.checks.length > 0 && (
            <div className="grid gap-1">
              {st.checks.map((c) => (
                <div key={c.check} className="flex gap-2">
                  <span className="font-mono">{c.passed ? "✓" : "✕"}</span>
                  <span>
                    {c.check} <span className="text-muted">— {c.reason}</span>
                  </span>
                </div>
              ))}
            </div>
          )}
          {steps > 0 && (
            <details>
              <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-[0.14em] text-faint">
                Agent log · {steps} steps
              </summary>
              <div className="mt-2 max-h-72 overflow-y-auto border border-rule bg-paper p-3 font-mono text-[11px] leading-relaxed">
                {events.map((e, i) => (
                  <div key={i} className="border-b border-dashed border-rule py-1 last:border-b-0">
                    <span className="text-faint">
                      {e.sub ? `${e.sub} · ` : ""}step {e.step} · ${e.cost.toFixed(4)}
                    </span>{" "}
                    <span>{e.tool ?? "message"}</span>
                    <div className="break-all text-muted">{e.args ?? e.text}</div>
                    {e.result && <div className="whitespace-pre-line break-all text-faint">→ {e.result}</div>}
                  </div>
                ))}
              </div>
            </details>
          )}
          {st.status === "done" && (
            <form
              className="flex flex-wrap items-center gap-2"
              onSubmit={async (e) => {
                e.preventDefault();
                if (!change.trim()) return;
                await onRequestChanges(st.task_id, change.trim());
                setChange("");
              }}
            >
              <input
                value={change}
                onChange={(e) => setChange(e.target.value)}
                placeholder="Request changes — the task and everything downstream re-runs with your feedback"
                className="min-w-0 flex-1 border-b border-rule bg-transparent py-1 text-[13px] outline-none placeholder:text-faint focus:border-ink"
              />
              <button type="submit" className="border border-ink px-3 py-1.5 text-[12.5px] hover:bg-ink hover:text-paper">
                Re-run with feedback
              </button>
            </form>
          )}
          {credential && (
            <form
              className="flex flex-wrap items-center gap-2 border border-ink bg-paper px-3 py-2"
              onSubmit={async (e) => {
                e.preventDefault();
                if (!secret.trim()) return;
                await onSecret(credential, secret.trim());
                setSecret("");
              }}
            >
              <span className="font-mono text-[11px]">{credential}</span>
              <input
                type="password"
                autoComplete="off"
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
                placeholder="Paste the key — stored locally, only this project's sandbox sees it"
                className="min-w-0 flex-1 bg-transparent py-1 font-mono text-[12px] outline-none placeholder:text-faint"
              />
              <button type="submit" className="bg-ink px-3 py-1.5 text-[12.5px] text-paper">
                Provide &amp; retry
              </button>
            </form>
          )}
          {actionable && (
            <div className="flex flex-wrap items-center gap-2">
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder={st.status === "human" ? "What did you do? (optional)" : "Why? (optional)"}
                className="min-w-0 flex-1 border-b border-rule bg-transparent py-1 text-[13px] outline-none placeholder:text-faint focus:border-ink"
              />
              <button onClick={() => onTask(st.task_id, "complete", note)} className="bg-ink px-3 py-1.5 text-[12.5px] text-paper">
                {st.status === "human" ? "Mark done" : "Accept output"}
              </button>
              <button onClick={() => onTask(st.task_id, "skip", note)} className="border border-ink px-3 py-1.5 text-[12.5px]">
                Skip
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
