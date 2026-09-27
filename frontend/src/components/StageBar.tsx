import type { Stage } from "@/lib/api";

const STAGES: { key: Stage; label: string }[] = [
  { key: "clarify", label: "Clarify" },
  { key: "literature", label: "Literature" },
  { key: "gaps", label: "Gaps" },
  { key: "plan", label: "Plan" },
  { key: "blueprint", label: "Blueprint" },
  { key: "executing", label: "Execute" },
];

export default function StageBar({ stage }: { stage: Stage }) {
  // "done" is the legacy name for "plan approved"; "ready" means the blueprint is approved.
  const current =
    stage === "done" ? 4 : stage === "ready" ? 5 : stage === "executed" ? STAGES.length : STAGES.findIndex((s) => s.key === stage);
  return (
    <ol className="flex min-w-0 items-center gap-2 overflow-hidden font-mono text-[11px] uppercase tracking-[0.1em]">
      {STAGES.map((s, i) => {
        const state = i < current ? "past" : i === current ? "now" : "next";
        return (
          <li key={s.key} className="flex shrink-0 items-center gap-2">
            {i > 0 && <span className="h-px w-3 bg-rule" />}
            <span className={state === "now" ? "text-ink" : state === "past" ? "text-muted" : "text-faint"}>
              <span className="mr-1.5">{String(i + 1).padStart(2, "0")}</span>
              {state === "now" ? <span className="border-b border-ink pb-px">{s.label}</span> : s.label}
            </span>
          </li>
        );
      })}
      {stage === "executed" && (
        <li className="flex shrink-0 items-center gap-2">
          <span className="h-px w-3 bg-rule" />
          <span className="bg-ink px-1.5 py-0.5 text-paper">Executed</span>
        </li>
      )}
    </ol>
  );
}
