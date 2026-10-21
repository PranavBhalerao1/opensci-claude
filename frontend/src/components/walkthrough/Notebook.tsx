// Copy of the workspace Notebook for the demo film: no backend calls, spend comes from the script.
import {
  type BlueprintRun,
  type Execution,
  type GapsRun,
  type Literature,
  type PlanRun,
  type Project,
} from "@/lib/api";

interface Props {
  project: Project | null;
  lit: Literature | null;
  gapsRun: GapsRun | null;
  planRun: PlanRun | null;
  bpRun: BlueprintRun | null;
  exec: Execution | null;
  onOpenFiles: () => void;
  onOpenLibrary: () => void;
  spent: number;
}

/** Right-hand lab notebook: a compact, always-visible record of each stage. */
export default function Notebook({ project, lit, gapsRun, planRun, bpRun, exec, onOpenFiles, onOpenLibrary, spent }: Props) {
  return (
    <aside className="flex w-80 shrink-0 flex-col border-l border-rule bg-paper max-xl:hidden">
      <div className="border-b border-rule px-5 py-4">
        <div className="font-serif text-[17px]">Notebook</div>
        <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-faint">Live record of the investigation</div>
      </div>
      {project ? (
        <Entries
          project={project}
          lit={lit}
          gapsRun={gapsRun}
          planRun={planRun}
          bpRun={bpRun}
          exec={exec}
          onOpenFiles={onOpenFiles}
          onOpenLibrary={onOpenLibrary}
          spent={spent}
        />
      ) : (
        <p className="px-5 py-4 text-[13px] leading-relaxed text-muted">Start an investigation to open a notebook.</p>
      )}
    </aside>
  );
}

function Spend({ spent }: { spent: number }) {
  if (!spent) return null;
  return (
    <div className="flex justify-between border-b border-dashed border-rule py-2">
      <dt className="uppercase tracking-wider text-faint">Model spend</dt>
      <dd className="text-ink">${spent.toFixed(2)}</dd>
    </div>
  );
}

function Entries({ project, lit, gapsRun, planRun, bpRun, exec, onOpenFiles, onOpenLibrary, spent }: Props & { project: Project }) {
  const { brief, settings } = project;
  const run = lit?.run;
  const overview = run?.result?.overview;
  const rows: [string, string][] = [
    ["Stage", project.stage],
    ["Mode", project.autonomous ? "Autonomous" : "Guided"],
    ["Depth", settings.depth ?? "standard"],
    ["Max papers", String(settings.max_papers ?? 100)],
    ["Opened", new Date(project.created_at).toLocaleDateString()],
  ];

  return (
    <div className="flex-1 overflow-y-auto px-5 py-4">
      <Label>§1 · Brief</Label>
      {brief ? (
        <div className="mt-2">
          <div className="font-serif text-[17px] leading-snug">{brief.title}</div>
          <p className="mt-2 border-l border-ink pl-3 font-serif text-[14px] italic leading-snug text-muted">
            {brief.core_question}
          </p>
        </div>
      ) : (
        <p className="mt-2 text-[13px] leading-relaxed text-faint">Forms once the clarifying questions are answered.</p>
      )}

      <div className="mt-7">
        <Label>§2 · Literature</Label>
        {run ? (
          <div className="mt-2">
            <dl className="grid grid-cols-3 border border-rule font-mono">
              {[
                ["Found", run.counts.found],
                ["Screened", run.counts.screened],
                ["Kept", run.counts.included],
              ].map(([k, v]) => (
                <div key={k} className="border-r border-rule px-2 py-2 last:border-r-0">
                  <dd className="text-[16px] leading-none">{v ?? "—"}</dd>
                  <dt className="mt-1 text-[9.5px] uppercase tracking-[0.12em] text-faint">{k}</dt>
                </div>
              ))}
            </dl>
            <p className="mt-2 font-mono text-[11px] text-muted">
              {run.status === "running" ? `${run.phase}…` : run.status === "error" ? "Failed" : "Complete"}
            </p>
            {overview && (
              <ol className="mt-3 grid gap-1.5">
                {overview.themes.map((t, i) => (
                  <li key={t.name} className="flex gap-2 text-[12.5px] leading-snug">
                    <span className="font-mono text-[10.5px] text-faint">T{i + 1}</span>
                    <span>{t.name}</span>
                  </li>
                ))}
              </ol>
            )}
            {run.status === "done" && (
              <button
                onClick={onOpenLibrary}
                className="mt-3 w-full border border-ink px-3 py-1.5 text-left text-[12.5px] transition-colors hover:bg-ink hover:text-paper"
              >
                Open library &amp; graph →
              </button>
            )}
          </div>
        ) : (
          <p className="mt-1 text-[12.5px] text-faint">Pending</p>
        )}
      </div>

      <div className="mt-7">
        <Label>§3 · Gaps</Label>
        {project.chosen_gap ? (
          <div className="mt-2">
            <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
              Chosen · {project.chosen_gap.overall.toFixed(2)} / 5
            </div>
            <div className="mt-1 font-serif text-[15px] leading-snug">{project.chosen_gap.title}</div>
            <p className="mt-1.5 border-l border-ink pl-3 font-serif text-[13px] italic leading-snug text-muted">
              {project.chosen_gap.question}
            </p>
          </div>
        ) : gapsRun ? (
          <p className="mt-1 font-mono text-[11px] text-muted">
            {gapsRun.status === "running"
              ? `${gapsRun.phase}…`
              : gapsRun.status === "error"
                ? "Failed"
                : `${gapsRun.result?.gaps.length ?? 0} candidates — awaiting your choice`}
          </p>
        ) : (
          <p className="mt-1 text-[12.5px] text-faint">Pending</p>
        )}
      </div>

      <div className="mt-7">
        <Label>§4 · Plan</Label>
        {planRun?.status === "done" && planRun.result ? (
          <div className="mt-2">
            <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
              {project.plan ? "Approved" : "Draft"} · {planRun.result.plan.phases.length} phases ·{" "}
              {planRun.result.plan.phases.reduce((n, p) => n + p.tasks.length, 0)} tasks
            </div>
            <ol className="mt-2 grid gap-1">
              {planRun.result.plan.phases.map((p) => (
                <li key={p.id} className="flex gap-2 text-[12.5px] leading-snug">
                  <span className="font-mono text-[10.5px] text-faint">{p.id}</span>
                  <span>{p.name}</span>
                </li>
              ))}
            </ol>
            {project.plan && (
              <div className="mt-3 grid gap-1">
                {["vague_research_plan.json", "context.json"].map((f) => (
                  <a
                    key={f}
                    href="#"
                    className="border border-ink px-3 py-1.5 font-mono text-[11px] transition-colors hover:bg-ink hover:text-paper"
                  >
                    ↓ {f}
                  </a>
                ))}
              </div>
            )}
          </div>
        ) : planRun ? (
          <p className="mt-1 font-mono text-[11px] text-muted">
            {planRun.status === "error" ? "Failed" : `${planRun.phase}…`}
          </p>
        ) : (
          <p className="mt-1 text-[12.5px] text-faint">Pending</p>
        )}
      </div>

      <div className="mt-7">
        <Label>§5 · Blueprint</Label>
        {bpRun?.status === "done" && bpRun.result ? (
          <div className="mt-2">
            <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
              {project.blueprint ? "Approved" : "Draft"} · {bpRun.result.master_plan.agents.length} agents ·{" "}
              {bpRun.result.master_plan.tasks.length} tasks
            </div>
            {bpRun.result.warnings.length > 0 && (
              <p className="mt-1 font-mono text-[11px] text-ink">! {bpRun.result.warnings.length} items need attention</p>
            )}
            {project.blueprint && (
              <a
                href="#"
                className="mt-2 block border border-ink px-3 py-1.5 font-mono text-[11px] transition-colors hover:bg-ink hover:text-paper"
              >
                ↓ master_plan.json
              </a>
            )}
          </div>
        ) : bpRun ? (
          <p className="mt-1 font-mono text-[11px] text-muted">{bpRun.status === "error" ? "Failed" : `${bpRun.phase}…`}</p>
        ) : (
          <p className="mt-1 text-[12.5px] text-faint">Pending</p>
        )}
      </div>

      <div className="mt-7">
        <Label>§6 · Execution</Label>
        {exec?.run ? (
          <div className="mt-2">
            <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
              {exec.tasks.filter((t) => t.status === "done" || t.status === "skipped").length} / {exec.tasks.length} tasks
              · ${exec.spent.toFixed(3)}
              {exec.live ? (exec.paused ? " · paused" : " · running") : ""}
            </div>
            {exec.tasks.some((t) => t.status === "failed" || t.status === "human") && (
              <p className="mt-1 font-mono text-[11px] text-ink">! tasks need your attention</p>
            )}
            <button
              onClick={onOpenFiles}
              className="mt-2 w-full border border-ink px-3 py-1.5 text-left font-mono text-[11px] transition-colors hover:bg-ink hover:text-paper"
            >
              Browse workspace →
            </button>
          </div>
        ) : (
          <p className="mt-1 text-[12.5px] text-faint">Pending</p>
        )}
      </div>

      <div className="mt-7">
        <Label>Record</Label>
        <dl className="mt-1 font-mono text-[12px]">
          {rows.map(([k, v]) => (
            <div key={k} className="flex justify-between border-b border-dashed border-rule py-2">
              <dt className="uppercase tracking-wider text-faint">{k}</dt>
              <dd className="capitalize text-ink">{v}</dd>
            </div>
          ))}
          <Spend spent={spent} />
        </dl>
      </div>
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-faint">{children}</div>;
}
