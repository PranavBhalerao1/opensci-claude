import type { Stage } from "@/lib/api";

const STAGES: { key: Stage; label: string }[] = [
  { key: "clarify", label: "Clarify" },
  { key: "literature", label: "Literature" },
  { key: "gaps", label: "Gaps" },
  { key: "plan", label: "Plan" },
];

export default function StageBar({ stage }: { stage: Stage }) {
  const current = STAGES.findIndex((s) => s.key === stage);
  return (
    <ol className="flex items-center gap-3 font-mono text-[11px] uppercase tracking-[0.12em]">
      {STAGES.map((s, i) => {
        const state = stage === "done" || i < current ? "past" : i === current ? "now" : "next";
        return (
          <li key={s.key} className="flex items-center gap-3">
            {i > 0 && <span className="h-px w-5 bg-rule" />}
            <span className={state === "now" ? "text-ink" : state === "past" ? "text-muted" : "text-faint"}>
              <span className="mr-1.5">{String(i + 1).padStart(2, "0")}</span>
              {state === "now" ? <span className="border-b border-ink pb-px">{s.label}</span> : s.label}
            </span>
          </li>
        );
      })}
      {stage === "done" && (
        <li className="flex items-center gap-3">
          <span className="h-px w-5 bg-rule" />
          <span className="bg-ink px-1.5 py-0.5 text-paper">Planning complete</span>
        </li>
      )}
    </ol>
  );
}
