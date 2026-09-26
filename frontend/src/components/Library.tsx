"use client";

import { useEffect, useMemo, useState } from "react";

import type { LitPaper } from "@/lib/api";
import KnowledgeGraph from "./KnowledgeGraph";

interface Props {
  projectId: string;
  papers: LitPaper[];
  focus?: string;
  onClose: () => void;
}

type Sort = "relevance" | "year" | "citations";

export default function Library({ projectId, papers, focus, onClose }: Props) {
  const [tab, setTab] = useState<"papers" | "graph">("papers");
  const [open, setOpen] = useState<string | null>(focus ?? null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const showPaper = (id: string) => {
    setTab("papers");
    setOpen(id);
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button aria-label="Close library" onClick={onClose} className="absolute inset-0 bg-ink/20" />
      <div className="relative flex h-full w-full max-w-[960px] flex-col border-l border-ink bg-paper">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-ink px-6">
          <div className="flex items-baseline gap-4">
            <span className="font-serif text-[20px]">Library</span>
            <span className="font-mono text-[11px] text-faint">{papers.length} papers</span>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex border border-ink font-mono text-[11px] uppercase tracking-[0.1em]" role="tablist">
              {(["papers", "graph"] as const).map((t) => (
                <button
                  key={t}
                  role="tab"
                  aria-selected={tab === t}
                  onClick={() => setTab(t)}
                  className={`px-3 py-1.5 ${tab === t ? "bg-ink text-paper" : "text-muted hover:text-ink"}`}
                >
                  {t === "papers" ? "Papers" : "Knowledge graph"}
                </button>
              ))}
            </div>
            <button onClick={onClose} className="font-mono text-[18px] leading-none text-muted hover:text-ink" aria-label="Close">
              ×
            </button>
          </div>
        </header>
        {tab === "papers" ? (
          <PaperList papers={papers} open={open} setOpen={setOpen} />
        ) : (
          <KnowledgeGraph projectId={projectId} onSelectPaper={showPaper} />
        )}
      </div>
    </div>
  );
}

function PaperList({
  papers,
  open,
  setOpen,
}: {
  papers: LitPaper[];
  open: string | null;
  setOpen: (id: string | null) => void;
}) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<Sort>("relevance");

  const shown = useMemo(() => {
    const q = query.toLowerCase();
    const list = q
      ? papers.filter((p) =>
          [p.title, p.venue, ...(p.authors ?? []), ...(p.notes?.methods ?? []), ...(p.notes?.datasets ?? [])]
            .join(" ")
            .toLowerCase()
            .includes(q),
        )
      : papers;
    const key: Record<Sort, (p: LitPaper) => number> = {
      relevance: (p) => (p.relevance ?? 0) * 1e6 + p.citation_count,
      year: (p) => p.year ?? 0,
      citations: (p) => p.citation_count,
    };
    return [...list].sort((a, b) => key[sort](b) - key[sort](a));
  }, [papers, query, sort]);

  useEffect(() => {
    if (open) document.getElementById(`paper-${open}`)?.scrollIntoView({ block: "center" });
  }, [open]);

  return (
    <>
      <div className="flex shrink-0 items-center gap-4 border-b border-rule px-6 py-3">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter by title, author, method, dataset…"
          className="flex-1 border-b border-rule bg-transparent py-1 text-[13px] outline-none placeholder:text-faint focus:border-ink"
        />
        <div className="flex gap-3 font-mono text-[11px] uppercase tracking-[0.1em]">
          {(["relevance", "year", "citations"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setSort(s)}
              className={sort === s ? "text-ink underline underline-offset-4" : "text-faint hover:text-ink"}
            >
              {s}
            </button>
          ))}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        {shown.map((p, i) => (
          <PaperRow key={p.id} index={i} paper={p} open={open === p.id} onToggle={() => setOpen(open === p.id ? null : p.id)} />
        ))}
        {shown.length === 0 && <p className="px-6 py-8 text-[13px] text-faint">No papers match.</p>}
      </div>
    </>
  );
}

function PaperRow({ index, paper: p, open, onToggle }: { index: number; paper: LitPaper; open: boolean; onToggle: () => void }) {
  const authors = p.authors.length > 3 ? `${p.authors.slice(0, 3).join(", ")} et al.` : p.authors.join(", ");
  return (
    <article id={`paper-${p.id}`} className={`border-b border-rule ${open ? "bg-wash" : ""}`}>
      <button onClick={onToggle} className="grid w-full grid-cols-[36px_1fr_auto] gap-3 px-6 py-3.5 text-left hover:bg-wash">
        <span className="pt-0.5 font-mono text-[11px] text-faint">{String(index + 1).padStart(3, "0")}</span>
        <span className="min-w-0">
          <span className="block text-[14px] leading-snug">{p.title}</span>
          <span className="mt-0.5 block truncate text-[12px] text-muted">
            {authors}
            {p.venue ? ` · ${p.venue}` : ""}
          </span>
        </span>
        <span className="flex flex-col items-end gap-1 font-mono text-[11px] text-muted">
          <span>{p.year ?? "n.d."}</span>
          <span className="flex items-center gap-2">
            <Relevance value={p.relevance ?? 0} />
            <span className="text-faint">{p.citation_count.toLocaleString()} cit.</span>
          </span>
        </span>
      </button>

      {open && (
        <div className="grid gap-4 px-6 pb-5 pl-[72px] text-[13.5px] leading-relaxed">
          {p.notes ? (
            <>
              <p className="font-serif text-[16px] leading-snug">{p.notes.contribution}</p>
              <Chips label="Methods" items={p.notes.methods} />
              <Chips label="Datasets" items={p.notes.datasets} />
              <Chips label="Metrics" items={p.notes.metrics} />
              <Bullets label="Findings" items={p.notes.key_findings} />
              <Bullets label="Limitations" items={p.notes.limitations} />
            </>
          ) : (
            <p className="text-muted">{p.tldr ?? p.abstract}</p>
          )}
          {p.abstract && (
            <details>
              <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-[0.14em] text-faint">
                Abstract
              </summary>
              <p className="mt-2 text-[13px] text-muted">{p.abstract}</p>
            </details>
          )}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px] text-muted">
            {p.reason && <span>Why included: {p.reason}</span>}
            {p.origin === "citation" && <span className="border border-rule px-1.5">via citation</span>}
            {p.url && (
              <a href={p.url} target="_blank" rel="noreferrer" className="underline underline-offset-2 hover:text-ink">
                Source ↗
              </a>
            )}
            {p.pdf_url && (
              <a href={p.pdf_url} target="_blank" rel="noreferrer" className="underline underline-offset-2 hover:text-ink">
                PDF ↗
              </a>
            )}
          </div>
        </div>
      )}
    </article>
  );
}

function Relevance({ value }: { value: number }) {
  return (
    <span className="flex gap-0.5" title={`Relevance ${value}/3`}>
      {[1, 2, 3].map((n) => (
        <span key={n} className={`h-1.5 w-1.5 ${n <= value ? "bg-ink" : "border border-rule"}`} />
      ))}
    </span>
  );
}

function Chips({ label, items }: { label: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div>
      <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">{label}</div>
      <div className="flex flex-wrap gap-1">
        {items.map((m) => (
          <span key={m} className="border border-rule bg-paper px-1.5 py-px font-mono text-[11px]">
            {m}
          </span>
        ))}
      </div>
    </div>
  );
}

function Bullets({ label, items }: { label: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div>
      <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">{label}</div>
      <ul className="grid gap-1">
        {items.map((m) => (
          <li key={m} className="flex gap-2">
            <span className="font-mono text-faint">–</span>
            <span>{m}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
