"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import type { PaperDocument } from "./types";

const pageCls =
  "relative min-h-[707px] w-[500px] shrink-0 border border-ink bg-paper px-[46px] pb-10 pt-9 text-ink shadow-[8px_8px_0_0_#0a0a0a]";
const body = "text-justify font-serif text-[7.6px] leading-[1.42]";
const h1 = "mt-3 font-serif text-[9.5px] font-bold";

/** Renders inline **bold** and *italic*. */
function Rich({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g);
  return (
    <>
      {parts.map((p, i) =>
        p.startsWith("**") ? (
          <b key={i}>{p.slice(2, -2)}</b>
        ) : p.startsWith("*") && p.length > 2 ? (
          <i key={i}>{p.slice(1, -1)}</i>
        ) : (
          p
        ),
      )}
    </>
  );
}

function Caption({ text }: { text: string }) {
  const i = text.indexOf(":");
  return (
    <p className="mt-1 font-serif text-[7px] leading-[1.35]">
      <b>{text.slice(0, i + 1)}</b>
      {text.slice(i + 1)}
    </p>
  );
}

function rng(seed: number) {
  let s = seed;
  return () => ((s = (s * 16807) % 2147483647) - 1) / 2147483646;
}

function Figure({
  kind,
  seed,
}: {
  kind: "scatter" | "bars" | "lines" | "heat";
  seed: number;
}) {
  const r = rng(seed * 97 + 13);
  const W = 180;
  const H = 110;
  const axes = (
    <>
      <line
        x1={22}
        y1={H - 16}
        x2={W - 6}
        y2={H - 16}
        stroke="#0a0a0a"
        strokeWidth={0.8}
      />
      <line
        x1={22}
        y1={6}
        x2={22}
        y2={H - 16}
        stroke="#0a0a0a"
        strokeWidth={0.8}
      />
    </>
  );
  if (kind === "heat") {
    return (
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        {Array.from({ length: 12 * 7 }, (_, i) => {
          const x = i % 12;
          const y = Math.floor(i / 12);
          const v = Math.max(
            0,
            Math.min(
              1,
              0.25 +
                0.6 * Math.exp(-((x - 7) ** 2 + (y - 3) ** 2) / 10) +
                (r() - 0.5) * 0.25,
            ),
          );
          return (
            <rect
              key={i}
              x={10 + x * 13.5}
              y={6 + y * 13.5}
              width={13}
              height={13}
              fill="#0a0a0a"
              fillOpacity={v}
            />
          );
        })}
      </svg>
    );
  }
  if (kind === "bars") {
    const vals = Array.from(
      { length: 6 },
      (_, i) => 0.3 + 0.1 * i + r() * 0.15,
    );
    return (
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        {axes}
        {vals.map((v, i) => (
          <g key={i}>
            <rect
              x={30 + i * 24}
              y={H - 16 - v * 80}
              width={9}
              height={v * 80}
              fill="#0a0a0a"
            />
            <rect
              x={40 + i * 24}
              y={H - 16 - v * 62}
              width={9}
              height={v * 62}
              fill="#0a0a0a"
              fillOpacity={0.3}
            />
          </g>
        ))}
      </svg>
    );
  }
  if (kind === "lines") {
    const line = (k: number, dash?: string) => {
      const pts = Array.from({ length: 16 }, (_, i) => {
        const x = 24 + i * 9.6;
        const y =
          14 +
          (1 - Math.exp(-i / (3 + k * 2))) * (60 - k * 14) +
          (r() - 0.5) * 4;
        return `${x},${H - 16 - (H - 30 - y)}`;
      });
      return (
        <polyline
          points={pts.join(" ")}
          fill="none"
          stroke="#0a0a0a"
          strokeWidth={1}
          strokeDasharray={dash}
        />
      );
    };
    return (
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        {axes}
        {line(0)}
        {line(1, "3 2")}
        {line(2, "1 2")}
      </svg>
    );
  }
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      {axes}
      {Array.from({ length: 70 }, (_, i) => {
        const x = r();
        const y = 0.15 + 0.7 * x + (r() - 0.5) * 0.3;
        return (
          <circle
            key={i}
            cx={24 + x * 148}
            cy={H - 16 - Math.max(0.02, Math.min(1, y)) * 86}
            r={1.6}
            fill={i % 3 ? "#0a0a0a" : "none"}
            stroke="#0a0a0a"
            strokeWidth={0.6}
          />
        );
      })}
      <line
        x1={24}
        y1={H - 16 - 0.15 * 86}
        x2={172}
        y2={H - 16 - 0.85 * 86}
        stroke="#0a0a0a"
        strokeWidth={0.8}
        strokeDasharray="3 2"
      />
    </svg>
  );
}

function Table({
  caption,
  head,
  rows,
}: {
  caption: string;
  head: string[];
  rows: string[][];
}) {
  return (
    <div className="mt-2">
      <Caption text={caption} />
      <table className="mt-1 w-full border-collapse font-serif text-[7px]">
        <thead>
          <tr className="border-y border-ink">
            {head.map((h) => (
              <th key={h} className="px-1 py-0.5 text-left font-normal">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={i}
              className={i === rows.length - 1 ? "border-b border-ink" : ""}
            >
              {row.map((v, j) => (
                <td key={j} className="px-1 py-[1px]">
                  <Rich text={v} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Page({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <div className={pageCls}>
      {children}
      <div className="absolute bottom-3 left-0 right-0 text-center font-serif text-[7px]">
        {n}
      </div>
    </div>
  );
}

type Section = PaperDocument["sections"][number];

/** A paper laid out on NeurIPS-style pages: title and abstract first, then about two sections a page. */
export function documentPages(doc: PaperDocument) {
  const pages: React.ReactNode[] = [];
  const sectionBlock = (s: Section, i: number) => (
    <div key={s.heading}>
      <div className={h1}>
        {i + 1}&nbsp;&nbsp;{s.heading}
      </div>
      {s.paragraphs.map((p, k) => (
        <p key={k} className={`${body} mt-1.5`}>
          <Rich text={p} />
        </p>
      ))}
      {s.figure && (
        <div className="mt-2 px-6">
          <div className="grid grid-cols-2 gap-3">
            <Figure kind={s.figure.kind} seed={i} />
            <Figure
              kind={s.figure.kind === "scatter" ? "lines" : "scatter"}
              seed={i + 50}
            />
          </div>
          <Caption text={s.figure.caption} />
        </div>
      )}
      {s.table && <Table {...s.table} />}
    </div>
  );

  pages.push(
    <Page n={1} key="p1">
      <div className="border-t-[3px] border-ink" />
      <div className="px-2 py-2.5 text-center font-serif text-[13.5px] font-bold leading-snug">
        {doc.title}
      </div>
      <div className="border-t border-ink" />
      <div className="mt-3 text-center font-serif text-[7.6px] leading-[1.35]">
        <div className="font-bold">{doc.authors}</div>
        <div>{doc.affiliation}</div>
      </div>
      <div className="mt-3 text-center font-serif text-[9.5px] font-bold">
        Abstract
      </div>
      <p className={`${body} mx-6 mt-1`}>
        <Rich text={doc.abstract} />
      </p>
      {doc.sections[0] && sectionBlock(doc.sections[0], 0)}
      <div className="absolute bottom-3 left-[46px] font-serif text-[6.5px] text-muted">
        Preprint. Under review.
      </div>
    </Page>,
  );

  let n = 2;
  for (let i = 1; i < doc.sections.length;) {
    const a = doc.sections[i];
    const heavy = (s: Section) =>
      Boolean(s.table || s.figure) || s.paragraphs.join("").length > 1400;
    const b =
      !heavy(a) && doc.sections[i + 1] && !heavy(doc.sections[i + 1])
        ? doc.sections[i + 1]
        : null;
    pages.push(
      <Page n={n} key={`p${n}`}>
        {sectionBlock(a, i)}
        {b && sectionBlock(b, i + 1)}
      </Page>,
    );
    n++;
    i += b ? 2 : 1;
  }

  pages.push(
    <Page n={n} key="refs">
      <div className={h1}>References</div>
      <ol className="mt-1.5 space-y-[3px] font-serif text-[7px] leading-[1.35]">
        {doc.references.map((ref, i) => (
          <li key={i} className="flex gap-1.5">
            <span className="shrink-0">[{i + 1}]</span>
            <span>
              <Rich text={ref} />
            </span>
          </li>
        ))}
      </ol>
    </Page>,
  );
  return pages;
}

/** Thumbnails of every page; click one to read the paper full size. */
export function PaperGrid({ pages }: { pages: React.ReactNode[] }) {
  const [open, setOpen] = useState<number | null>(null);

  useEffect(() => {
    if (open === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(null);
      if (e.key === "ArrowRight")
        setOpen((o) => (o === null ? o : Math.min(pages.length - 1, o + 1)));
      if (e.key === "ArrowLeft")
        setOpen((o) => (o === null ? o : Math.max(0, o - 1)));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, pages.length]);

  return (
    <>
      <div className="grid w-full grid-cols-4 gap-3 px-4">
        {pages.map((pg, i) => (
          <button
            key={i}
            onClick={() => setOpen(i)}
            className="h-[200px] overflow-hidden text-left hover:opacity-80"
            title={`Page ${i + 1}`}
          >
            <div className="pointer-events-none origin-top-left scale-[0.28]">
              {pg}
            </div>
          </button>
        ))}
      </div>
      {/* Portalled: an animated (transformed) ancestor would otherwise contain the fixed overlay. */}
      {open !== null &&
        createPortal(
          <div
            className="fixed inset-0 z-[300] flex flex-col bg-ink/80"
            onClick={() => setOpen(null)}
          >
            <div className="flex items-center justify-between px-6 py-3 font-mono text-[11px] uppercase tracking-wider text-paper">
              <span>
                paper.pdf · page {open + 1} / {pages.length}
              </span>
              <span>← → to turn pages · esc to close</span>
            </div>
            <div
              className="flex flex-1 items-start justify-center overflow-y-auto pb-10"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="h-[1010px] pt-4">
                <div className="origin-top scale-[1.35]">{pages[open]}</div>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
