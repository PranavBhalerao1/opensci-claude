"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";

import { DEPTHS, type Depth, type Message, type Project, type ResearchBrief } from "@/lib/api";

type BriefMessage = Extract<Message, { kind: "brief" }>;

interface Props {
  message: BriefMessage;
  project: Project;
  /** Only the newest brief is actionable; older drafts are superseded. */
  latest: boolean;
  busy: boolean;
  onConfirm: (depth: Depth, maxPapers: number) => Promise<void>;
}

export default function BriefCard({ message, project, latest, busy, onConfirm }: Props) {
  const { brief } = message.payload;
  const [open, setOpen] = useState(latest);
  const confirmed = latest && project.stage !== "clarify";

  if (!latest) {
    return (
      <section className="mb-8">
        <button
          onClick={() => setOpen(!open)}
          className="flex w-full items-baseline justify-between border border-dashed border-rule px-4 py-3 text-left hover:border-ink"
        >
          <span>
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-faint">Earlier draft · </span>
            <span className="text-[14px] text-muted">{brief.title}</span>
          </span>
          <span className="font-mono text-[11px] text-faint">{open ? "hide" : "show"}</span>
        </button>
        {open && <BriefBody brief={brief} />}
      </section>
    );
  }

  return (
    <section className="mb-10">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">OpenScientist</div>
      <div className="prose-os mb-5">
        <ReactMarkdown>{message.payload.message}</ReactMarkdown>
      </div>

      <div className="border border-ink">
        <div className="flex items-center justify-between border-b border-ink px-6 py-2.5 font-mono text-[10px] uppercase tracking-[0.16em]">
          <span>Research brief</span>
          <span className={confirmed ? "bg-ink px-1.5 py-0.5 text-paper" : "text-muted"}>
            {confirmed ? "Confirmed" : "Draft"}
          </span>
        </div>
        <div className="px-6">
          <BriefBody brief={brief} />
        </div>
        {confirmed ? (
          <div className="flex items-center justify-between border-t border-ink bg-wash px-6 py-3 font-mono text-[11px] text-muted">
            <span className="uppercase tracking-[0.12em]">
              {project.settings.depth ?? "standard"} depth · {project.settings.max_papers ?? 100} papers
            </span>
            <span>{project.autonomous ? "Confirmed automatically" : "Confirmed"}</span>
          </div>
        ) : (
          <ConfirmBar project={project} busy={busy} onConfirm={onConfirm} />
        )}
      </div>
    </section>
  );
}

function ConfirmBar({ project, busy, onConfirm }: Pick<Props, "project" | "busy" | "onConfirm">) {
  const [depth, setDepth] = useState<Depth>(project.settings.depth ?? "standard");
  const [maxPapers, setMaxPapers] = useState<number>(project.settings.max_papers ?? 100);
  const [saving, setSaving] = useState(false);

  const pick = (d: Depth) => {
    setDepth(d);
    setMaxPapers(DEPTHS.find((x) => x.key === d)!.papers);
  };

  return (
    <div className="border-t border-ink bg-wash px-6 py-5">
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-faint">Literature review depth</div>
      <div className="mt-2 flex flex-wrap items-stretch gap-3">
        <div className="flex border border-ink" role="radiogroup">
          {DEPTHS.map((d) => (
            <button
              key={d.key}
              role="radio"
              aria-checked={depth === d.key}
              onClick={() => pick(d.key)}
              className={`px-4 py-2 text-left transition-colors ${
                depth === d.key ? "bg-ink text-paper" : "bg-paper hover:bg-wash"
              }`}
            >
              <span className="block text-[13px]">{d.label}</span>
              <span className={`block font-mono text-[10px] ${depth === d.key ? "text-faint" : "text-muted"}`}>
                {d.note}
              </span>
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 border border-rule bg-paper px-3">
          <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">Max papers</span>
          <input
            type="number"
            min={10}
            max={500}
            value={maxPapers}
            onChange={(e) => setMaxPapers(Number(e.target.value))}
            className="w-14 bg-transparent py-2 font-mono text-[13px] outline-none"
          />
        </label>
      </div>
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
        <span className="text-[13px] text-muted">Want to change something? Reply below and the brief will be revised.</span>
        <button
          disabled={busy || saving}
          onClick={async () => {
            setSaving(true);
            try {
              await onConfirm(depth, Math.max(10, Math.min(500, maxPapers || 100)));
            } finally {
              setSaving(false);
            }
          }}
          className="bg-ink px-5 py-2.5 text-[13px] text-paper disabled:opacity-25"
        >
          {saving ? "Confirming…" : "Confirm & start literature review →"}
        </button>
      </div>
    </div>
  );
}

function BriefBody({ brief }: { brief: ResearchBrief }) {
  const facts: [string, string][] = [
    ["Domain", brief.domain],
    ["Result type", brief.result_type],
    ["Data", brief.data_resources],
    ["Compute", brief.compute_resources],
    ["Your background", brief.user_expertise],
  ];
  return (
    <div className="py-6">
      <h2 className="font-serif text-[28px] leading-tight tracking-tight">{brief.title}</h2>
      <blockquote className="mt-4 border-l-2 border-ink pl-4 font-serif text-[19px] italic leading-snug">
        {brief.core_question}
      </blockquote>
      <p className="mt-4 text-[14.5px] leading-relaxed text-muted">{brief.summary}</p>

      <dl className="mt-6 border-t border-rule">
        {facts.map(([k, v]) => (
          <div key={k} className="grid grid-cols-[140px_1fr] gap-4 border-b border-rule py-2.5 max-sm:grid-cols-1 max-sm:gap-0.5">
            <dt className="font-mono text-[10px] uppercase tracking-[0.14em] text-faint pt-0.5">{k}</dt>
            <dd className="text-[13.5px] leading-relaxed">{v}</dd>
          </div>
        ))}
      </dl>

      <Section title="Key concepts">
        <dl className="grid gap-2.5">
          {brief.key_concepts.map((c) => (
            <div key={c.term} className="text-[13.5px] leading-relaxed">
              <dt className="inline font-medium">{c.term}. </dt>
              <dd className="inline text-muted">{c.definition}</dd>
            </div>
          ))}
        </dl>
      </Section>

      <div className="grid gap-x-8 sm:grid-cols-2">
        <Section title="In scope">
          <List items={brief.scope_in} mark="+" />
        </Section>
        <Section title="Out of scope">
          <List items={brief.scope_out} mark="−" />
        </Section>
      </div>

      {brief.constraints.length > 0 && (
        <Section title="Constraints">
          <List items={brief.constraints} mark="·" />
        </Section>
      )}

      {brief.assumptions.length > 0 && (
        <Section title="Assumptions made for you">
          <List items={brief.assumptions} mark="→" />
        </Section>
      )}

      <Section title="Search keywords">
        <div className="flex flex-wrap gap-1.5">
          {brief.search_keywords.map((k) => (
            <span key={k} className="border border-rule px-2 py-0.5 font-mono text-[11.5px] text-muted">
              {k}
            </span>
          ))}
        </div>
      </Section>
    </div>
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

function List({ items, mark }: { items: string[]; mark: string }) {
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
