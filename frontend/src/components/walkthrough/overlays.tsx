"use client";

import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, type SimulationLinkDatum, type SimulationNodeDatum } from "d3-force";
import { useEffect, useRef, useState } from "react";

import { CONCEPTS, GAPS, MASTER, PAPER_TITLE, QUERIES, READING, STREAM, TOOL_SCRIPT, TOTALS } from "./data";

// ── Timing helpers ─────────────────────────────────────────────────────────

/** Milliseconds of "film time" since mount (scaled by speed). */
export function useClock(speed: number) {
  const [t, setT] = useState(0);
  useEffect(() => {
    const start = performance.now();
    let raf = 0;
    const loop = () => {
      setT((performance.now() - start) * speed);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [speed]);
  return t;
}

const clamp = (x: number, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const ease = (x: number) => 1 - Math.pow(1 - clamp(x), 3);
const ramp = (t: number, from: number, to: number) => ease((t - from) / (to - from));
const typed = (text: string, t: number, start: number, cps = 60) =>
  text.slice(0, Math.max(0, Math.floor(((t - start) / 1000) * cps)));
const fmt = (n: number) => Math.round(n).toLocaleString("en-US");

/** Deterministic pseudo-random numbers, so every replay is identical. */
function rng(seed: number) {
  let s = seed;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

function Pulse({ size = 2.5 }: { size?: number }) {
  const s = `${size * 4}px`;
  return (
    <span className="relative inline-flex shrink-0" style={{ width: s, height: s }}>
      <span className="absolute inline-flex h-full w-full animate-ping bg-ink opacity-40" />
      <span className="relative inline-flex h-full w-full bg-ink" />
    </span>
  );
}

function Kicker({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`font-mono text-[10px] uppercase tracking-[0.16em] text-faint ${className}`}>{children}</div>;
}

// ── Intro, chapter cards, outro ────────────────────────────────────────────

export function Intro() {
  return (
    <div className="film-fade fixed inset-0 z-[80] flex items-center justify-center bg-ink text-paper">
      <div className="text-center">
        <div className="film-rise font-mono text-[11px] uppercase tracking-[0.3em] text-faint">A research run, start to finish</div>
        <div className="film-rise mt-6 font-serif text-[92px] leading-none tracking-tight" style={{ animationDelay: "150ms" }}>
          Open<span className="italic">Scientist</span>
        </div>
        <div className="film-rise mt-6 font-serif text-[26px] italic text-faint" style={{ animationDelay: "450ms" }}>
          Every question deserves a scientist.
        </div>
        <div className="film-rise mx-auto mt-10 h-px w-24 bg-faint/50" style={{ animationDelay: "700ms" }} />
      </div>
    </div>
  );
}

export function Chapter({ n, total, title, subtitle }: { n: number; total: number; title: string; subtitle: string }) {
  return (
    <div className="film-wipe fixed inset-0 z-[80] flex items-center bg-ink text-paper">
      <div className="mx-auto w-full max-w-5xl px-16">
        <div className="film-rise flex items-center gap-4 font-mono text-[12px] uppercase tracking-[0.3em] text-faint">
          <span>Stage {String(n).padStart(2, "0")}</span>
          <span className="h-px w-16 bg-faint/40" />
          <span>{String(total).padStart(2, "0")}</span>
        </div>
        <div className="film-rise mt-5 font-serif text-[76px] leading-[1.02] tracking-tight" style={{ animationDelay: "120ms" }}>
          {title}
        </div>
        <div className="film-rise mt-4 font-serif text-[28px] italic text-faint" style={{ animationDelay: "260ms" }}>
          {subtitle}
        </div>
        <div className="mt-10 flex gap-1.5">
          {Array.from({ length: total }, (_, i) => (
            <span key={i} className={`h-[3px] w-10 ${i < n ? "bg-paper" : "bg-paper/20"}`} />
          ))}
        </div>
      </div>
    </div>
  );
}

export function Outro({ speed }: { speed: number }) {
  const t = useClock(speed);
  const stats: [string, string][] = [
    [TOTALS.wall, "question → reviewed paper"],
    ["118", "papers read & extracted"],
    ["3", "MCP servers it wrote"],
    ["0", "servers you had to set up"],
    ["2,350", "forecasts re-run on 47 heatwaves"],
    ["4", "new skills it taught itself"],
    ["9.2 / 10", "independent review score"],
    [`$${TOTALS.total.toFixed(2)}`, "total cost of the run"],
  ];
  return (
    <div className="film-fade fixed inset-0 z-[80] flex items-center justify-center bg-ink text-paper">
      <div className="w-full max-w-5xl px-16">
        <div className={`transition-opacity duration-700 ${t > 5000 ? "opacity-0" : "opacity-100"}`}>
          <Kicker className="text-faint">The run, in numbers</Kicker>
          <div className="mt-6 grid grid-cols-4 gap-px bg-paper/15">
            {stats.map(([v, k], i) => (
              <div key={k} className="bg-ink px-5 py-6" style={{ opacity: ramp(t, 200 + i * 200, 700 + i * 200) }}>
                <div className="font-serif text-[40px] leading-none">{v}</div>
                <div className="mt-2 font-mono text-[10.5px] uppercase tracking-[0.14em] text-faint">{k}</div>
              </div>
            ))}
          </div>
          <p className="mt-8 font-serif text-[22px] italic text-faint" style={{ opacity: ramp(t, 2200, 2900) }}>
            No human touched it after the question.
          </p>
        </div>
        <div
          className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center transition-opacity duration-1000"
          style={{ opacity: t > 5400 ? 1 : 0 }}
        >
          <div className="font-serif text-[92px] leading-none tracking-tight">
            Open<span className="italic">Scientist</span>
          </div>
          <div className="mt-6 font-serif text-[26px] italic text-faint">Every question deserves a scientist.</div>
        </div>
      </div>
    </div>
  );
}

// ── Captions, callouts, cursor ─────────────────────────────────────────────

export function Caption({ kicker, text }: { kicker: string; text: string }) {
  return (
    <div className="pointer-events-none fixed bottom-7 left-1/2 z-[70] -translate-x-1/2">
      <div key={text} className="film-caption flex max-w-[780px] items-stretch border border-ink bg-ink text-paper shadow-[6px_6px_0_0_rgba(10,10,10,0.18)]">
        <div className="flex items-center border-r border-paper/20 px-4 font-mono text-[10px] uppercase tracking-[0.16em] text-faint">
          {kicker}
        </div>
        <div className="px-5 py-3.5 font-serif text-[19px] leading-snug">{text}</div>
      </div>
    </div>
  );
}

type Side = "right" | "left" | "top" | "bottom";

/** A ring around a live element plus a label pinned beside it; follows the element every frame. */
export function Callout({ target, text, side = "right", dim = false }: { target: string; text: string; side?: Side; dim?: boolean }) {
  const [rect, setRect] = useState<DOMRect | null>(null);
  useEffect(() => {
    let raf = 0;
    const loop = () => {
      const el = document.querySelector(target);
      setRect(el ? el.getBoundingClientRect() : null);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [target]);
  if (!rect) return null;
  const pad = 8;
  const box = { left: rect.left - pad, top: rect.top - pad, width: rect.width + pad * 2, height: rect.height + pad * 2 };
  const W = 290;
  let label: React.CSSProperties;
  if (side === "right") label = { left: Math.min(box.left + box.width + 28, window.innerWidth - W - 16), top: box.top + box.height / 2, transform: "translateY(-50%)" };
  else if (side === "left") label = { left: Math.max(16, box.left - W - 28), top: box.top + box.height / 2, transform: "translateY(-50%)" };
  else if (side === "top") label = { left: Math.max(16, Math.min(box.left + box.width / 2 - W / 2, window.innerWidth - W - 16)), top: box.top - 20, transform: "translateY(-100%)" };
  else label = { left: Math.max(16, Math.min(box.left + box.width / 2 - W / 2, window.innerWidth - W - 16)), top: box.top + box.height + 20 };
  return (
    <div className="pointer-events-none fixed inset-0 z-[60]">
      <div
        className="film-ring absolute border-2 border-ink transition-all duration-300"
        style={{ ...box, boxShadow: dim ? "0 0 0 9999px rgba(10,10,10,0.38)" : "0 0 0 4px rgba(255,255,255,0.9)" }}
      />
      <div key={text} className="film-pop absolute bg-ink px-4 py-3 text-paper shadow-[5px_5px_0_0_rgba(10,10,10,0.2)]" style={{ ...label, width: W }}>
        <div className="font-mono text-[9.5px] uppercase tracking-[0.16em] text-faint">◆ Note</div>
        <div className="mt-1 text-[14px] leading-snug">{text}</div>
      </div>
    </div>
  );
}

export function Cursor({ x, y, visible, clicking }: { x: number; y: number; visible: boolean; clicking: number }) {
  return (
    <div
      className="pointer-events-none fixed z-[90] transition-[left,top,opacity] duration-[900ms] ease-[cubic-bezier(.5,0,.2,1)]"
      style={{ left: x, top: y, opacity: visible ? 1 : 0 }}
    >
      {clicking > 0 && <span key={clicking} className="film-click absolute -left-5 -top-5 h-10 w-10 rounded-full border-2 border-ink" />}
      <svg width="22" height="26" viewBox="0 0 22 26" className="drop-shadow-[2px_3px_2px_rgba(0,0,0,0.25)]">
        <path d="M2 1 L2 21 L7.5 16 L11 24.5 L14.5 23 L11 14.8 L18.5 14.8 Z" fill="#0a0a0a" stroke="#fff" strokeWidth="1.4" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

/** Small toasts in the top-right, used for system events. */
export function Toasts({ items }: { items: { id: number; text: string; mark: string }[] }) {
  return (
    <div className="pointer-events-none fixed right-8 top-[70px] z-[75] grid w-[420px] gap-2">
      {items.map((i) => (
        <div key={i.id} className="film-pop flex gap-3 border border-ink bg-paper px-4 py-3 shadow-[4px_4px_0_0_#0a0a0a]">
          <span className="font-mono text-[13px]">{i.mark}</span>
          <span className="text-[13px] leading-snug">{i.text}</span>
        </div>
      ))}
    </div>
  );
}

// ── Scene shell ────────────────────────────────────────────────────────────

function Scene({ kicker, title, right, children }: { kicker: string; title: string; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-[50] bg-paper">
      <div className="film-zoom-in flex h-full flex-col">
        <div className="graph-paper pointer-events-none absolute inset-0 opacity-60" />
        <header className="relative flex h-14 shrink-0 items-center justify-between border-b border-ink px-8">
          <div className="flex items-baseline gap-4">
            <span className="font-serif text-[20px] leading-none tracking-tight">
              Open<span className="italic">Scientist</span>
            </span>
            <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-faint">{kicker}</span>
          </div>
          <div className="flex items-center gap-4 font-mono text-[11px] uppercase tracking-[0.12em]">{right}</div>
        </header>
        <div className="relative px-8 pt-6">
          <h2 className="font-serif text-[34px] leading-tight tracking-tight">{title}</h2>
        </div>
        <div className="relative min-h-0 flex-1 px-8 pb-24 pt-5">{children}</div>
      </div>
    </div>
  );
}

// ── Source finder (literature) ─────────────────────────────────────────────

type GNode = SimulationNodeDatum & { id: string; kind: "paper" | "concept"; label: string };
type GLink = SimulationLinkDatum<GNode> & { kind: "mentions" | "cites" };

function LiveGraph({ count }: { count: number }) {
  const W = 560;
  const H = 440;
  const sim = useRef<ReturnType<typeof forceSimulation<GNode>> | null>(null);
  const nodes = useRef<GNode[]>([]);
  const links = useRef<GLink[]>([]);
  const rand = useRef(rng(7));
  const [, setFrame] = useState(0);

  useEffect(() => {
    const s = forceSimulation<GNode>([])
      .force("charge", forceManyBody<GNode>().strength((d) => (d.kind === "concept" ? -160 : -28)))
      .force("link", forceLink<GNode, GLink>([]).id((d) => d.id).distance((l) => (l.kind === "cites" ? 26 : 48)).strength(0.3))
      .force("collide", forceCollide<GNode>((d) => (d.kind === "concept" ? 22 : 6)))
      .force("center", forceCenter(W / 2, H / 2))
      .alphaDecay(0.01)
      .on("tick", () => setFrame((f) => f + 1));
    sim.current = s;
    return () => void s.stop();
  }, []);

  useEffect(() => {
    const s = sim.current;
    if (!s) return;
    let changed = false;
    const have = nodes.current;
    const concepts = () => have.filter((n) => n.kind === "concept");
    while (concepts().length < Math.min(CONCEPTS.length, Math.floor(count / 2.5))) {
      const i = concepts().length;
      have.push({ id: `c${i}`, kind: "concept", label: CONCEPTS[i], x: W / 2 + Math.cos(i * 2.4) * 120, y: H / 2 + Math.sin(i * 2.4) * 100 });
      changed = true;
    }
    while (have.filter((n) => n.kind === "paper").length < count * 3) {
      const i = have.filter((n) => n.kind === "paper").length;
      const node: GNode = { id: `p${i}`, kind: "paper", label: "", x: W / 2 + (rand.current() - 0.5) * 300, y: H / 2 + (rand.current() - 0.5) * 240 };
      have.push(node);
      const cs = concepts();
      if (cs.length) {
        links.current.push({ source: node.id, target: cs[(i * 7) % cs.length].id, kind: "mentions" });
        if (i % 3 === 0) links.current.push({ source: node.id, target: cs[(i * 3 + 1) % cs.length].id, kind: "mentions" });
      }
      if (i > 4 && i % 2 === 0) links.current.push({ source: node.id, target: `p${(i * 5) % i}`, kind: "cites" });
      changed = true;
    }
    if (changed) {
      s.nodes(have);
      (s.force("link") as ReturnType<typeof forceLink<GNode, GLink>>).links(links.current);
      s.alpha(0.6).restart();
    }
  }, [count]);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-full w-full">
      {/* d3 moves the nodes in place and each tick bumps `frame`, so reading the refs here is intended. */}
      {/* eslint-disable-next-line react-hooks/refs */}
      {links.current.map((l, i) => {
        const a = l.source as GNode;
        const b = l.target as GNode;
        if (a.x == null || b.x == null) return null;
        return (
          <line
            key={i}
            x1={a.x}
            y1={a.y}
            x2={b.x}
            y2={b.y}
            stroke="#0a0a0a"
            strokeOpacity={l.kind === "cites" ? 0.35 : 0.12}
            strokeWidth={l.kind === "cites" ? 0.9 : 0.7}
            strokeDasharray={l.kind === "cites" ? undefined : "2 2"}
          />
        );
      })}
      {/* eslint-disable-next-line react-hooks/refs */}
      {nodes.current.map((n) =>
        n.kind === "concept" ? (
          <g key={n.id} transform={`translate(${n.x ?? 0},${n.y ?? 0})`} className="film-node">
            <rect x={-4} y={-4} width={8} height={8} fill="#0a0a0a" />
            <text y={-9} textAnchor="middle" className="fill-ink font-mono text-[9px]">
              {n.label}
            </text>
          </g>
        ) : (
          <circle key={n.id} cx={n.x} cy={n.y} r={2.6} fill="#fff" stroke="#0a0a0a" strokeWidth={1} className="film-node" />
        ),
      )}
    </svg>
  );
}

export function SourceFinder({ speed }: { speed: number }) {
  const t = useClock(speed);
  const found = 2106 * ramp(t, 400, 9000);
  const screened = 486 * ramp(t, 3500, 12500);
  const kept = 118 * ramp(t, 5000, 14000);
  const read = 118 * ramp(t, 8000, 17000);
  const phases = [
    ["Search", 0],
    ["Screen", 3500],
    ["Follow citations", 7000],
    ["Read & extract", 8500],
    ["Link", 14500],
    ["Synthesise", 16000],
  ] as const;
  const phaseAt = phases.filter(([, at]) => t >= at).length - 1;
  const streamed = STREAM.filter((_, i) => t > 700 + i * 430);
  const shown = streamed.slice(-8).reverse();
  const reading = t > 8800 && t < 15200;

  return (
    <Scene
      kicker="02 · Literature review · live"
      title="Finding its own sources"
      right={
        <>
          <span className="flex items-center gap-2">
            <Pulse /> {phases[Math.max(0, phaseAt)][0]}
          </span>
          <span className="text-faint">Semantic Scholar · OpenAlex</span>
        </>
      }
    >
      <div className="grid h-full grid-cols-[300px_1fr_1fr] gap-6">
        <div className="flex min-h-0 flex-col gap-5">
          <div className="border border-ink bg-paper">
            <div className="border-b border-ink px-4 py-2">
              <Kicker>Queries written from the brief</Kicker>
            </div>
            <ol className="px-4 py-2">
              {QUERIES.map((q, i) => {
                const at = 200 + i * 650;
                if (t < at) return null;
                const done = t > at + 900;
                return (
                  <li key={q} className="film-slide flex items-baseline gap-2 py-1 font-mono text-[11.5px]">
                    <span className="w-3">{done ? "✓" : "›"}</span>
                    <span className={done ? "text-muted" : ""}>{typed(q, t, at, 70)}</span>
                  </li>
                );
              })}
            </ol>
          </div>
          <div className="border border-ink bg-paper px-4 py-3">
            <Kicker>Pipeline</Kicker>
            <ol className="mt-2 grid gap-1.5">
              {phases.map(([p], i) => (
                <li key={p} className="flex items-center gap-3 text-[13px]">
                  {i < phaseAt ? <span className="h-2.5 w-2.5 bg-ink" /> : i === phaseAt ? <Pulse /> : <span className="h-2.5 w-2.5 border border-rule" />}
                  <span className={i > phaseAt ? "text-faint" : ""}>{p}</span>
                </li>
              ))}
            </ol>
          </div>
          <div className="grid grid-cols-2 border border-ink bg-paper font-mono">
            {[
              ["Found", found],
              ["Screened", screened],
              ["Kept", kept],
              ["Read", read],
            ].map(([k, v], i) => (
              <div key={k as string} className={`px-4 py-3 ${i % 2 === 0 ? "border-r border-rule" : ""} ${i < 2 ? "border-b border-rule" : ""}`}>
                <div className="text-[26px] leading-none">{fmt(v as number)}</div>
                <div className="mt-1 text-[9.5px] uppercase tracking-[0.14em] text-faint">{k as string}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="flex min-h-0 flex-col border border-ink bg-paper">
          <div className="flex items-center justify-between border-b border-ink px-4 py-2">
            <Kicker>Incoming papers · screened by OS-Scout</Kicker>
            <span className="font-mono text-[10px] text-muted">relevance</span>
          </div>
          <div className="min-h-0 flex-1 overflow-hidden">
            {shown.map((p) => (
              <div key={p.title} className="film-slide grid grid-cols-[34px_1fr_auto] items-start gap-3 border-b border-rule px-4 py-2.5">
                <span className="mt-0.5 border border-rule px-1 text-center font-mono text-[9px] text-muted">{p.src === "CIT" ? "CITE" : p.src}</span>
                <div className="min-w-0">
                  <div className={`truncate text-[13px] ${p.keep ? "" : "text-faint line-through"}`}>{p.title}</div>
                  <div className="font-mono text-[10.5px] text-faint">
                    {p.venue} · {p.year}
                    {p.src === "CIT" ? " · found by following citations" : ""}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[11px]">{p.score.toFixed(2)}</span>
                  <span className={`px-1.5 py-0.5 font-mono text-[9.5px] uppercase tracking-[0.12em] ${p.keep ? "bg-ink text-paper" : "border border-rule text-faint"}`}>
                    {p.keep ? "Keep" : "Drop"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="relative flex min-h-0 flex-col border border-ink bg-paper">
          <div className="flex items-center justify-between border-b border-ink px-4 py-2">
            <Kicker>Knowledge graph · growing</Kicker>
            <span className="font-mono text-[10px] text-muted">■ concept · ○ paper · — cites</span>
          </div>
          <div className="min-h-0 flex-1">
            <LiveGraph count={streamed.filter((s) => s.keep).length} />
          </div>
        </div>
      </div>

      {reading && (
        <div className="film-pop absolute left-1/2 top-[54%] z-10 w-[580px] -translate-x-1/2 -translate-y-1/2 border-2 border-ink bg-paper shadow-[10px_10px_0_0_#0a0a0a]">
          <div className="flex items-center justify-between border-b border-ink bg-ink px-5 py-2 text-paper">
            <span className="font-mono text-[10px] uppercase tracking-[0.16em]">Reading · extracting notes with OS-Reader</span>
            <span className="font-mono text-[10px] text-faint">paper 22 / 118</span>
          </div>
          <div className="px-5 py-4">
            <div className="font-serif text-[20px] leading-snug">{READING.title}</div>
            <div className="mt-1 font-mono text-[11px] text-muted">{READING.meta}</div>
            <dl className="mt-4 grid gap-2.5">
              {READING.notes.map(([k, v], i) => {
                const at = 9400 + i * 900;
                if (t < at) return null;
                return (
                  <div key={k} className="grid grid-cols-[100px_1fr] gap-3 text-[13px] leading-relaxed">
                    <dt className="pt-0.5 font-mono text-[10px] uppercase tracking-[0.12em] text-faint">{k}</dt>
                    <dd>{typed(v, t, at, 90)}</dd>
                  </div>
                );
              })}
            </dl>
          </div>
        </div>
      )}
    </Scene>
  );
}

// ── Novelty check (gaps) ───────────────────────────────────────────────────

export function NoveltyCheck({ speed }: { speed: number }) {
  const t = useClock(speed);
  const g = GAPS[0];
  const counts = [44, 31, 58];
  const verdicts = ["Different question", "Different phenomenon"];
  const scores = [
    ["Novelty", g.scores.novelty.score],
    ["Feasibility", g.scores.feasibility.score],
    ["Impact", g.scores.impact.score],
    ["Testability", g.scores.testability.score],
  ] as const;
  return (
    <Scene kicker="03 · Research gaps · novelty check" title="Has anyone already done this?" right={<span className="flex items-center gap-2"><Pulse /> Checking gap 1 of 5</span>}>
      <div className="grid h-full grid-cols-[1fr_1fr] gap-6">
        <div className="flex flex-col gap-5">
          <div className="border border-ink bg-paper px-6 py-5">
            <Kicker>Candidate gap #1 · proposed by OS-Reasoner</Kicker>
            <div className="mt-2 font-serif text-[26px] leading-snug">{g.title}</div>
            <p className="mt-3 border-l-2 border-ink pl-3 font-serif text-[16px] italic leading-snug text-muted">
              AI models are scored on average days. Nobody has asked whether they break down exactly when heat goes beyond what they were trained on — or tried to fix it.
            </p>
          </div>
          <div className="border border-ink bg-paper">
            <div className="border-b border-ink px-5 py-2">
              <Kicker>Targeted searches for prior work</Kicker>
            </div>
            {g.novelty_queries.map((q, i) => {
              const at = 300 + i * 900;
              if (t < at) return null;
              const done = t > at + 800;
              return (
                <div key={q} className="film-slide flex items-center justify-between border-b border-rule px-5 py-2.5 font-mono text-[12px] last:border-b-0">
                  <span className="flex items-center gap-2">
                    {done ? "✓" : <Pulse size={2} />} “{q}”
                  </span>
                  <span className="text-muted">{done ? `${counts[i]} results` : "searching…"}</span>
                </div>
              );
            })}
          </div>
        </div>
        <div className="flex flex-col gap-5">
          <div className="border border-ink bg-paper">
            <div className="border-b border-ink px-5 py-2">
              <Kicker>Closest prior work · overlap judged by OS-Reader</Kicker>
            </div>
            {g.novelty_check.closest.map((c, i) => {
              const at = 2900 + i * 900;
              if (t < at) return null;
              return (
                <div key={c.title} className="film-slide border-b border-rule px-5 py-3 last:border-b-0">
                  <div className="flex items-start justify-between gap-3">
                    <div className="text-[13.5px] leading-snug">{c.title}</div>
                    <span className="shrink-0 border border-ink px-1.5 py-0.5 font-mono text-[9.5px] uppercase tracking-[0.12em]">{verdicts[i]}</span>
                  </div>
                  <div className="font-mono text-[10.5px] text-faint">{c.year} · in your review</div>
                  <div className="mt-1 text-[12.5px] text-muted">{c.overlap}</div>
                </div>
              );
            })}
          </div>
          {t > 4700 && (
            <div className="film-pop border-2 border-ink bg-paper px-6 py-5">
              <div className="flex items-center justify-between">
                <span className="bg-ink px-2 py-1 font-mono text-[12px] uppercase tracking-[0.16em] text-paper">● Novel</span>
                <span className="font-mono text-[28px] leading-none">
                  {g.overall.toFixed(2)} <span className="text-[12px] text-faint">/ 5</span>
                </span>
              </div>
              <div className="mt-4 grid grid-cols-4 gap-4">
                {scores.map(([k, v], i) => (
                  <div key={k}>
                    <div className="flex justify-between font-mono text-[10px] uppercase tracking-[0.12em] text-faint">
                      <span>{k}</span>
                      <span className="text-ink">{v}</span>
                    </div>
                    <div className="mt-1 flex gap-0.5">
                      {[1, 2, 3, 4, 5].map((n) => (
                        <span key={n} className={`h-1.5 flex-1 transition-colors duration-300 ${n <= v && t > 4900 + i * 200 + n * 60 ? "bg-ink" : "bg-rule"}`} />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </Scene>
  );
}

// ── Expert check (plan) ────────────────────────────────────────────────────

export function ExpertCheck({ speed }: { speed: number }) {
  const t = useClock(speed);
  const problems = [
    {
      sev: "FATAL",
      kind: "Training-period leakage",
      draft: "events = detect_records(years=range(2016, 2024))",
      problem: "2016–2017 are inside the AI models' training data. Those “record” events were seen in training, so they cannot test generalisation.",
      fix: "events = detect_records(years=range(2018, 2024))  # after every model's training data",
    },
    {
      sev: "MAJOR",
      kind: "Unfair comparison",
      draft: "score(hres, truth=hres_analysis); score(ai, truth=era5)",
      problem: "Each model was scored against a different “truth”. HRES would look better or worse for reasons unrelated to skill.",
      fix: "for m in [hres, graphcast, pangu]: score(m, truth=era5, grid='0.25deg')",
    },
  ];
  return (
    <Scene
      kicker="04 · Plan · expert check"
      title="A domain expert audits the science — before any compute is spent"
      right={<span className="flex items-center gap-2">{t < 6200 ? <><Pulse /> Auditing first draft</> : "✓ Passed"}</span>}
    >
      <div className="grid gap-5">
        {problems.map((p, i) => {
          const at = 400 + i * 2600;
          if (t < at) return null;
          const fixed = t > at + 1700;
          return (
            <div key={p.kind} className="film-slide grid grid-cols-[1fr_60px_1fr] items-stretch gap-0">
              <div className={`border border-ink bg-paper px-5 py-4 transition-opacity duration-500 ${fixed ? "opacity-50" : ""}`}>
                <div className="flex items-center gap-2">
                  <span className="bg-ink px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-paper">{p.sev}</span>
                  <span className="font-mono text-[11px] uppercase tracking-[0.12em]">{p.kind}</span>
                </div>
                <div className={`mt-3 border border-rule bg-wash px-3 py-2 font-mono text-[12px] ${fixed ? "line-through" : ""}`}>{p.draft}</div>
                <p className="mt-2 text-[13.5px] leading-relaxed">{p.problem}</p>
              </div>
              <div className="flex items-center justify-center font-mono text-[22px]">{fixed ? "→" : ""}</div>
              <div className={`border-2 border-ink bg-paper px-5 py-4 transition-all duration-500 ${fixed ? "opacity-100" : "opacity-0"}`}>
                <div className="flex items-center gap-2">
                  <span className="border border-ink px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em]">✓ Revised</span>
                  <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-muted">plan rewritten by itself</span>
                </div>
                <div className="mt-3 border border-ink bg-ink px-3 py-2 font-mono text-[12px] text-paper">{p.fix}</div>
                <p className="mt-2 text-[13.5px] leading-relaxed text-muted">Applied before approval. Downstream tasks updated.</p>
              </div>
            </div>
          );
        })}
        {t > 6000 && (
          <div className="film-pop flex items-center justify-between border-2 border-ink bg-ink px-6 py-4 text-paper">
            <span className="font-serif text-[22px]">Fixed before approval. Not one experiment was run on a flawed design.</span>
            <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-faint">2 serious problems → 0</span>
          </div>
        )}
      </div>
    </Scene>
  );
}

// ── Build tools: servers, MCPs, sources (blueprint) ────────────────────────

const MCP_CODE = `from mcp.server.fastmcp import FastMCP
import xarray as xr

mcp = FastMCP("era5-arco")
ERA5 = "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"
ds = xr.open_zarr(ERA5, chunks=None, storage_options={"token": "anon"})

@mcp.tool()
def get_field(var: str, start: str, end: str, bbox: list[float]) -> str:
    """Slice one ERA5 variable to NetCDF; returns the path."""
    sub = ds[var].sel(time=slice(start, end), **box(bbox))
    return save(sub)

@mcp.tool()
def find_records(after: int = 2018, min_k: float = 1.0) -> list[dict]:
    """Cells where heat after \`after\` beats the 1979–2017 record."""
    return detect(ds["2m_temperature"], after, min_k)

if __name__ == "__main__":
    mcp.run()`;

export function BuildTools({ speed }: { speed: number }) {
  const t = useClock(speed);
  const servers = [
    { name: "era5-arco", tools: "get_field · find_records · list_variables · climatology", at: 8200 },
    { name: "forecast-runner", tools: "rollout · load_checkpoint · finetune", at: 9300 },
    { name: "hres-archive", tools: "fetch_forecast · list_starts", at: 10300 },
  ];
  const sources = [
    ["ARCO-ERA5", "gs://gcp-public-data-arco-era5 · 0.25° hourly reanalysis", "reachable"],
    ["WeatherBench 2", "gs://weatherbench2 · IFS HRES forecasts", "reachable"],
    ["GraphCast", "github.com/google-deepmind/graphcast · 0.25°, 37 levels", "weights ✓"],
    ["Pangu-Weather", "github.com/198808xc/Pangu-Weather · ONNX 1h/3h/6h/24h", "weights ✓"],
  ];
  return (
    <Scene
      kicker="05 · Blueprint · infrastructure"
      title="It builds its own tools — writes MCP servers and wires up its data"
      right={<span className="flex items-center gap-2">{t < 12500 ? <><Pulse /> Infra Engineer · A3</> : "✓ Ready to execute"}</span>}
    >
      <div className="grid h-full grid-cols-[1fr_1.15fr_1fr] gap-6">
        <div className="flex min-h-0 flex-col gap-4">
          <div className="border border-ink bg-paper">
            <div className="flex items-center justify-between border-b border-ink px-4 py-2">
              <Kicker>Compute · OpenScientist Cloud</Kicker>
              <span className="font-mono text-[10px] text-muted">managed for you</span>
            </div>
            <p className="border-b border-rule px-4 py-3 text-[13px] leading-relaxed">
              No servers, no setup. OpenScientist sizes and allocates the compute this plan needs.
            </p>
            {[
              ["Sandbox", "Python 3.12 · conda · 2 TB scratch"],
              ["Accelerated workers", "allocated for hindcasts & fine-tuning"],
              ["ERA5 mirror", "attached read-only"],
              ["Scaling", "grows with the queue, stops when idle"],
            ].map(([k, v], i) => {
              const at = 900 + i * 900;
              if (t < at) return null;
              return (
                <div key={k} className="film-slide flex items-baseline justify-between gap-3 border-b border-rule px-4 py-2 last:border-b-0">
                  <span className="text-[13px]">✓ {k}</span>
                  <span className="truncate font-mono text-[10.5px] text-muted">{v}</span>
                </div>
              );
            })}
          </div>
          {t > 4600 && (
            <div className="film-pop border border-ink bg-ink px-4 py-3 font-mono text-[11px] leading-[1.7] text-paper">
              <div className="text-faint">workload estimate</div>
              <div>2,350 forecasts · 1 retrain · 1 fine-tune</div>
              <div>≈ 17 h on OpenScientist Cloud</div>
              <div className="text-faint">included in the run budget</div>
            </div>
          )}
        </div>

        <div className="flex min-h-0 flex-col gap-4">
          <div className="flex min-h-0 flex-1 flex-col border border-ink bg-ink text-paper">
            <div className="flex items-center justify-between border-b border-paper/20 px-4 py-2">
              <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-faint">Writing its own MCP server · mcp/era5_arco.py</span>
              <span className="font-mono text-[10px] text-faint">{t > 7600 ? "6 / 6 tests passed" : "writing…"}</span>
            </div>
            <pre className="caret min-h-0 flex-1 overflow-hidden whitespace-pre px-4 py-3 font-mono text-[10.8px] leading-[1.55] text-paper/90">
              {typed(MCP_CODE, t, 400, 150)}
            </pre>
          </div>
          <div className="border border-ink bg-paper">
            <div className="border-b border-ink px-4 py-2">
              <Kicker>MCP servers registered for this project’s agents</Kicker>
            </div>
            {servers.map((s) =>
              t < s.at ? null : (
                <div key={s.name} className="film-slide flex items-baseline justify-between gap-3 border-b border-rule px-4 py-2 last:border-b-0">
                  <span className="shrink-0 font-mono text-[12px]">✓ mcp:{s.name}</span>
                  <span className="truncate font-mono text-[10.5px] text-muted">{s.tools}</span>
                </div>
              ),
            )}
          </div>
        </div>

        <div className="flex min-h-0 flex-col gap-4">
          <div className="border border-ink bg-paper">
            <div className="border-b border-ink px-4 py-2">
              <Kicker>Experiment sources · located & verified</Kicker>
            </div>
            {sources.map(([n, where, ok], i) => {
              const at = 900 + i * 1200;
              if (t < at) return null;
              const done = t > at + 900;
              return (
                <div key={n} className="film-slide border-b border-rule px-4 py-2.5 last:border-b-0">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-[13px]">{n}</span>
                    <span className="font-mono text-[10.5px]">{done ? `✓ ${ok}` : "checking…"}</span>
                  </div>
                  <div className="truncate font-mono text-[10.5px] text-muted">{where}</div>
                </div>
              );
            })}
          </div>
          {t > 10800 && (
            <div className="film-pop border-2 border-ink bg-paper px-4 py-3">
              <Kicker>Experiment matrix</Kicker>
              <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5 font-mono text-[11.5px]">
                <span>47 record events</span>
                <span>× 5 start dates</span>
                <span>× GraphCast, Pangu</span>
                <span>+ HRES baseline</span>
                <span>+ 1 counterfactual model</span>
                <span>+ 1 fine-tuned model</span>
              </div>
              <div className="mt-2 border-t border-rule pt-2 font-mono text-[11px] text-muted">= 2,350 ten-day forecasts · runs on OpenScientist Cloud</div>
            </div>
          )}
        </div>
      </div>
    </Scene>
  );
}

// ── Mission control (execution) ────────────────────────────────────────────

/** When each task runs inside the execution scene (ms of scene time). */
export const EXEC_SCHEDULE: Record<string, { start: number; end: number; fail?: number }> = {
  T1: { start: 300, end: 3600 },
  T2: { start: 300, end: 4200 },
  T3: { start: 3800, end: 6600 },
  T5: { start: 6800, end: 8800 },
  T4: { start: 6800, end: 15500, fail: 10600 },
  T8: { start: 4400, end: 17500 },
  T6: { start: 15700, end: 19800, fail: 16900 },
  T7: { start: 15700, end: 18400 },
  T9: { start: 19900, end: 23400 },
  T10: { start: 23500, end: 25200 },
  T11: { start: 23500, end: 25800 },
  T12: { start: 25900, end: 27400 },
};
export const EXEC_END = 27700;

const SUBS = ["graphcast-a", "graphcast-b", "pangu-a", "pangu-b"];

/** Simulated per-event results: bias = a + slope × exceedance + noise. */
function makeEvents() {
  const r = rng(42);
  return Array.from({ length: 47 }, () => {
    const e = 1 + r() * 3.5 + (r() > 0.85 ? r() * 1.6 : 0);
    const n = () => (r() - 0.5) * 1.3;
    return { e, gc: -1.17 - 0.52 * e + n(), hres: -0.715 - 0.14 * e + n() * 0.8, ta: -0.92 - 0.21 * e + n() * 0.9 };
  });
}
const EVENTS = makeEvents();

function Scatter({ t }: { t: number }) {
  const W = 420;
  const H = 200;
  const x = (e: number) => 34 + (e / 6.5) * (W - 44);
  const y = (b: number) => 12 + ((1 - b) / 7.5) * (H - 40);
  const shownBase = Math.floor(clamp((t - 17900) / 1900) * EVENTS.length);
  const shownTA = Math.floor(clamp((t - 23500) / 1700) * EVENTS.length);
  const line = (a: number, s: number) => `M${x(0.8)},${y(a + s * 0.8)} L${x(6.2)},${y(a + s * 6.2)}`;
  const progress = Math.floor(2350 * clamp((t - 6800) / 8700));
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        {[0, -2, -4, -6].map((v) => (
          <g key={v}>
            <line x1={34} x2={W - 10} y1={y(v)} y2={y(v)} stroke="#e5e5e5" />
            <text x={28} y={y(v) + 3} textAnchor="end" className="fill-faint font-mono text-[9px]">
              {v}
            </text>
          </g>
        ))}
        {[1, 2, 3, 4, 5, 6].map((v) => (
          <text key={v} x={x(v)} y={H - 16} textAnchor="middle" className="fill-faint font-mono text-[9px]">
            +{v}
          </text>
        ))}
        <text x={W - 10} y={H - 4} textAnchor="end" className="fill-muted font-mono text-[9px]">
          record exceedance (K) →
        </text>
        <text x={36} y={10} className="fill-muted font-mono text-[9px]">
          day-5 peak bias (K)
        </text>
        {EVENTS.slice(0, shownBase).map((p, i) => (
          <g key={i}>
            <circle cx={x(p.e)} cy={y(p.hres)} r={2.4} fill="#0a0a0a" opacity={0.35} />
            <circle cx={x(p.e)} cy={y(p.gc)} r={2.6} fill="#fff" stroke="#0a0a0a" strokeWidth={1} />
          </g>
        ))}
        {EVENTS.slice(0, shownTA).map((p, i) => (
          <rect key={i} x={x(p.e) - 2.2} y={y(p.ta) - 2.2} width={4.4} height={4.4} fill="#0a0a0a" />
        ))}
        {t > 19800 && (
          <>
            <path d={line(-0.715, -0.14)} stroke="#0a0a0a" strokeOpacity={0.45} strokeWidth={1.4} strokeDasharray="4 3" fill="none" />
            <path d={line(-1.17, -0.52)} stroke="#0a0a0a" strokeWidth={1.6} fill="none" />
            <text x={x(6.2)} y={y(-1.17 - 0.52 * 6.2) - 4} textAnchor="end" className="fill-ink font-mono text-[9px]">
              GraphCast −0.52 K/K
            </text>
            <text x={x(6.2)} y={y(-0.715 - 0.14 * 6.2) - 4} textAnchor="end" className="fill-muted font-mono text-[9px]">
              HRES −0.14 K/K
            </text>
          </>
        )}
        {t > 25200 && (
          <>
            <path d={line(-0.92, -0.21)} stroke="#0a0a0a" strokeWidth={1.2} strokeDasharray="1.5 2" fill="none" />
            <text x={x(4.6)} y={y(-0.92 - 0.21 * 4.6) + 12} className="fill-ink font-mono text-[9px]">
              fine-tuned −0.21
            </text>
          </>
        )}
      </svg>
      <div className="mt-1 flex flex-wrap justify-between gap-x-4 font-mono text-[9.5px] text-muted">
        <span>○ GraphCast · ● HRES · ■ fine-tuned (ours)</span>
        <span>{t < 15500 ? `hindcasts ${fmt(progress)} / 2,350` : t < 17900 ? "scoring 47 events…" : "47 events scored"}</span>
      </div>
    </div>
  );
}

export function MissionControl({ speed }: { speed: number }) {
  const t = useClock(speed);
  const p = clamp(t / EXEC_END);
  const clock = Math.floor(p * (17 * 3600 + 48 * 60));
  const hh = Math.floor(clock / 3600);
  const mm = Math.floor((clock % 3600) / 60);
  const ss = clock % 60;
  const cost = 72.4 * clamp(p * 1.02);
  const doneTasks = Object.entries(EXEC_SCHEDULE).filter(([, s]) => t >= s.end).length;
  const gpuBusy = (t > 6800 && t < 17500) || (t > 19900 && t < 23400);
  const subsOn = t > 7600;

  const status = (id: string) => {
    const s = EXEC_SCHEDULE[id];
    if (t < s.start) return "pending";
    if (t >= s.end) return "done";
    if (s.fail && t >= s.fail && t < s.fail + 900) return "failed";
    return "running";
  };

  const linesFor = (agent: string) => {
    const out: { key: string; text: string; tool: string; dim: boolean; sub?: string; at: number }[] = [];
    for (const tk of MASTER.tasks.filter((x) => x.agent === agent)) {
      const s = EXEC_SCHEDULE[tk.id];
      const script = TOOL_SCRIPT[tk.id] ?? [];
      script.forEach((e, i) => {
        const at = s.start + ((s.end - s.start - 300) * (i + 0.3)) / script.length;
        if (t >= at) out.push({ key: tk.id + i, at, tool: e.tool, text: `${tk.id} · ${e.args}`, dim: t >= s.end, sub: e.sub });
      });
      if (t >= s.end) out.push({ key: tk.id + "d", at: s.end, tool: "✓", text: `${tk.id} verified · ${tk.title}`, dim: true });
    }
    return out.sort((a, b) => a.at - b.at).slice(-4);
  };

  const skills = [
    { name: "nan_safe_zarr_reader", why: "repairs corrupt Zarr chunks", at: 2600, reuse: "" },
    { name: "sharded_rollout", why: "splits rollouts across workers", at: 12400, reuse: t > 20500 ? "reused 3×" : "" },
    { name: "regrid_to_era5", why: "conservative regridding", at: 17900, reuse: t > 24000 ? "reused 2×" : "" },
    { name: "bootstrap_by_event", why: "event-block resampling", at: 23800, reuse: "" },
  ];

  const toasts = [
    { at: 6700, until: 9300, mark: "◆", text: "Checkpoint after T3: all 47 events fall after every model’s training data." },
    { at: 10600, until: 12400, mark: "✕", text: "T4 ran out of memory on 10-day, 0.25° rollouts." },
    { at: 12400, until: 15600, mark: "✦", text: "It wrote itself a new skill, sharded_rollout, saved it to its library, and the retry passed." },
    { at: 16900, until: 19800, mark: "✕", text: "Verifier rejected T6: forecasts and ERA5 were on different grids. New skill regrid_to_era5; retrying on OS-Reasoner." },
    { at: 20500, until: 23300, mark: "↻", text: "sharded_rollout reused by T8, T9 and T10 — what one agent learned, every agent now uses." },
    { at: 27400, until: 1e9, mark: "✓", text: "12 / 12 tasks verified · 4 new skills learned." },
  ]
    .map((x, id) => ({ ...x, id }))
    .filter((x) => t >= x.at && t < x.until)
    .slice(-2);

  return (
    <Scene
      kicker="06 · Execution · OpenScientist Cloud"
      title="Six agents run the experiment — and get better as they go"
      right={
        <>
          <span className="flex items-center gap-2">{doneTasks < 12 ? <Pulse /> : "✓"} {doneTasks} / 12 tasks</span>
          <span>{gpuBusy ? "Cloud workers · 91%" : "Cloud · idle"}</span>
          <span>${cost.toFixed(2)}</span>
          <span className="bg-ink px-2 py-1 text-paper">
            {String(hh).padStart(2, "0")}:{String(mm).padStart(2, "0")}:{String(ss).padStart(2, "0")} · time-lapse
          </span>
        </>
      }
    >
      <div className="grid h-full grid-cols-[1fr_440px] gap-6">
        <div className="grid min-h-0 grid-cols-2 grid-rows-3 gap-3">
          {MASTER.agents.map((a) => {
            const mine = MASTER.tasks.filter((x) => x.agent === a.id);
            const live = mine.some((x) => status(x.id) === "running" || status(x.id) === "failed");
            const failed = mine.some((x) => status(x.id) === "failed");
            const lines = linesFor(a.id);
            return (
              <div
                key={a.id}
                className={`relative flex min-h-0 flex-col border bg-paper transition-shadow ${live ? "border-ink shadow-[4px_4px_0_0_#0a0a0a]" : "border-rule"} ${failed ? "film-shake" : ""}`}
              >
                <div className={`flex items-center justify-between px-3 py-1.5 ${live ? "bg-ink text-paper" : "border-b border-rule"}`}>
                  <span className="text-[12.5px]">
                    <span className="mr-2 font-mono text-[10px] text-faint">{a.id}</span>
                    {a.name}
                  </span>
                  <span className="flex gap-1">
                    {mine.map((x) => {
                      const s = status(x.id);
                      return (
                        <span
                          key={x.id}
                          className={`px-1 font-mono text-[9.5px] ${
                            s === "done" ? (live ? "bg-paper text-ink" : "bg-ink text-paper") : s === "failed" ? "line-through" : s === "running" ? "animate-pulse underline" : "opacity-50"
                          }`}
                        >
                          {x.id}
                        </span>
                      );
                    })}
                  </span>
                </div>
                <div className="min-h-0 flex-1 overflow-hidden px-3 py-1.5 font-mono text-[10.5px] leading-[1.55]">
                  {lines.map((l) => (
                    <div key={l.key} className={`film-slide truncate ${l.dim ? "text-faint" : ""}`}>
                      {l.tool === "skill+" ? (
                        <span className="mr-1 bg-ink px-1 text-paper">✦ new skill</span>
                      ) : l.tool === "error" || l.tool === "verifier" ? (
                        <span className="mr-1 border border-ink px-1 text-ink">✕ {l.tool}</span>
                      ) : (
                        <span className="text-muted">{l.sub ? `${l.sub} · ` : ""}{l.tool} </span>
                      )}
                      <span>{l.text}</span>
                    </div>
                  ))}
                  {!lines.length && <div className="text-faint">waiting on upstream tasks…</div>}
                </div>
                {a.id === "A4" && subsOn && (
                  <div className="flex gap-1 border-t border-dashed border-rule px-3 py-1.5">
                    {SUBS.map((s, i) => (
                      <span
                        key={s}
                        className={`film-pop border px-1.5 font-mono text-[9.5px] ${t < 15500 ? "border-ink" : "border-rule text-faint"}`}
                        style={{ animationDelay: `${i * 120}ms` }}
                      >
                        ↳ {s}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
        <div className="flex min-h-0 flex-col gap-3">
          <div className="border border-ink bg-paper px-4 py-3">
            <Kicker>Live results · peak bias vs. record exceedance</Kicker>
            <Scatter t={t} />
          </div>
          <div className="border border-ink bg-paper">
            <div className="flex items-center justify-between border-b border-ink px-4 py-2">
              <Kicker>Self-improvement · tool library</Kicker>
              <span className="font-mono text-[10px] text-muted">{skills.filter((s) => t >= s.at).length} new skills</span>
            </div>
            <div className="px-4 py-2 font-mono text-[10.5px] leading-[1.7]">
              <div className="text-muted">mcp:era5-arco · mcp:forecast-runner · mcp:hres-archive</div>
              {skills.map((s) =>
                t < s.at ? null : (
                  <div key={s.name} className="film-slide flex justify-between gap-2">
                    <span className="truncate">
                      <span className="mr-1.5 bg-ink px-1 text-paper">✦</span>
                      {s.name} <span className="text-faint">· {s.why}</span>
                    </span>
                    <span className="shrink-0 text-muted">{s.reuse}</span>
                  </div>
                ),
              )}
            </div>
          </div>
          <div className="border border-ink bg-paper">
            <div className="grid grid-cols-6 gap-1 p-3">
              {MASTER.tasks.map((x) => {
                const s = status(x.id);
                return (
                  <div
                    key={x.id}
                    className={`border px-1 py-1.5 text-center font-mono text-[10px] transition-colors duration-300 ${
                      s === "done"
                        ? "border-ink bg-ink text-paper"
                        : s === "running"
                          ? "animate-pulse border-ink"
                          : s === "failed"
                            ? "border-ink bg-[repeating-linear-gradient(45deg,#0a0a0a_0_1px,transparent_1px_4px)]"
                            : "border-rule text-faint"
                    }`}
                  >
                    {x.id}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
      <Toasts items={toasts} />
    </Scene>
  );
}

// ── The paper: NeurIPS-style pages ─────────────────────────────────────────

function HeatMap() {
  const r = rng(3);
  const cols = 26;
  const rows = 14;
  return (
    <svg viewBox="0 0 130 70" className="w-full">
      {Array.from({ length: rows }, (_, j) =>
        Array.from({ length: cols }, (_, i) => {
          const d = Math.hypot((i - 9) / 6, (j - 6) / 4);
          const v = clamp(1 - d + (r() - 0.5) * 0.15);
          return <rect key={`${i}-${j}`} x={i * 5} y={j * 5} width={5} height={5} fill="#0a0a0a" opacity={0.05 + v * 0.85} />;
        }),
      )}
      <path d="M8,62 C20,50 22,30 30,18 C36,10 44,8 48,4" stroke="#fff" strokeWidth="0.7" fill="none" />
      <circle cx={46} cy={31} r={1.6} fill="#fff" stroke="#0a0a0a" strokeWidth="0.5" />
    </svg>
  );
}

function Traces() {
  const pts = (f: (d: number) => number) => Array.from({ length: 21 }, (_, i) => `${6 + i * 6},${60 - f(i / 2) * 9}`).join(" ");
  const era5 = (d: number) => 1 + 4.6 * Math.exp(-Math.pow((d - 6) / 1.8, 2));
  return (
    <svg viewBox="0 0 132 70" className="w-full">
      <line x1={6} x2={128} y1={60} y2={60} stroke="#0a0a0a" strokeWidth="0.4" />
      <line x1={6} x2={6} y1={4} y2={60} stroke="#0a0a0a" strokeWidth="0.4" />
      <polyline points={pts(era5)} fill="none" stroke="#0a0a0a" strokeWidth="1.3" />
      <polyline points={pts((d) => era5(d) * 0.86)} fill="none" stroke="#0a0a0a" strokeWidth="0.7" strokeDasharray="3 1.5" />
      <polyline points={pts((d) => era5(d) * 0.58)} fill="none" stroke="#0a0a0a" strokeWidth="0.7" strokeDasharray="1 1.2" />
      <polyline points={pts((d) => era5(d) * 0.8)} fill="none" stroke="#0a0a0a" strokeWidth="0.7" opacity={0.55} />
    </svg>
  );
}

function MiniScatter() {
  const x = (e: number) => 6 + (e / 6.5) * 122;
  const y = (b: number) => 4 + ((1 - b) / 7.5) * 58;
  return (
    <svg viewBox="0 0 132 70" className="w-full">
      <line x1={6} x2={128} y1={y(0)} y2={y(0)} stroke="#0a0a0a" strokeWidth="0.3" strokeDasharray="1 1" />
      {EVENTS.map((p, i) => (
        <g key={i}>
          <circle cx={x(p.e)} cy={y(p.gc)} r={1.1} fill="#fff" stroke="#0a0a0a" strokeWidth="0.4" />
          <circle cx={x(p.e)} cy={y(p.hres)} r={1} fill="#0a0a0a" opacity={0.4} />
        </g>
      ))}
      <path d={`M${x(0.8)},${y(-1.17 - 0.52 * 0.8)} L${x(6.2)},${y(-1.17 - 0.52 * 6.2)}`} stroke="#0a0a0a" strokeWidth="0.9" />
      <path d={`M${x(0.8)},${y(-0.715 - 0.14 * 0.8)} L${x(6.2)},${y(-0.715 - 0.14 * 6.2)}`} stroke="#0a0a0a" strokeWidth="0.7" strokeDasharray="2 1" />
    </svg>
  );
}

function Spectra() {
  const curve = (drop: number) =>
    Array.from({ length: 30 }, (_, i) => {
      const k = i / 29;
      const v = 8 + k * 50 + (k > 0.55 ? Math.pow((k - 0.55) / 0.45, 2) * drop : 0);
      return `${6 + k * 120},${v}`;
    }).join(" ");
  return (
    <svg viewBox="0 0 132 70" className="w-full">
      <line x1={6} x2={128} y1={66} y2={66} stroke="#0a0a0a" strokeWidth="0.4" />
      <line x1={6} x2={6} y1={2} y2={66} stroke="#0a0a0a" strokeWidth="0.4" />
      <polyline points={curve(0)} fill="none" stroke="#0a0a0a" strokeWidth="1.1" />
      <polyline points={curve(12)} fill="none" stroke="#0a0a0a" strokeWidth="0.7" strokeDasharray="1 1.2" />
      <polyline points={curve(3)} fill="none" stroke="#0a0a0a" strokeWidth="0.7" strokeDasharray="3 1.5" />
    </svg>
  );
}

function Bars() {
  const bars = [
    ["full (→2017)", 1.3],
    ["2005 model", 2.4],
  ] as const;
  return (
    <svg viewBox="0 0 132 70" className="w-full">
      <line x1={10} x2={128} y1={60} y2={60} stroke="#0a0a0a" strokeWidth="0.4" />
      {bars.map(([n, v], i) => (
        <g key={n} transform={`translate(${28 + i * 50},0)`}>
          <rect x={0} y={60 - v * 20} width={22} height={v * 20} fill={i ? "#0a0a0a" : "url(#hp)"} stroke="#0a0a0a" strokeWidth="0.5" />
          <text x={11} y={56 - v * 20} textAnchor="middle" className="fill-ink" style={{ fontSize: 5.5 }}>
            −{v.toFixed(1)} K
          </text>
          <text x={11} y={67} textAnchor="middle" className="fill-ink" style={{ fontSize: 5 }}>
            {n}
          </text>
        </g>
      ))}
      <defs>
        <pattern id="hp" width="2.5" height="2.5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="2.5" stroke="#0a0a0a" strokeWidth="0.5" />
        </pattern>
      </defs>
    </svg>
  );
}

const pageCls = "relative min-h-[707px] w-[500px] shrink-0 border border-ink bg-paper px-[46px] pb-10 pt-9 text-ink shadow-[8px_8px_0_0_#0a0a0a]";
const body = "text-justify font-serif text-[7.6px] leading-[1.42]";
const h1 = "mt-3 font-serif text-[9.5px] font-bold";
const cite = (n: string) => <span>[{n}]</span>;

export function PaperPage1({ reveal = 99 }: { reveal?: number }) {
  const show = (n: number) => ({ opacity: reveal >= n ? 1 : 0, transition: "opacity .5s" });
  return (
    <div className={pageCls}>
      <div style={show(0)}>
        <div className="border-t-[3px] border-ink" />
        <div className="px-2 py-2.5 text-center font-serif text-[13.5px] font-bold leading-snug">{PAPER_TITLE}</div>
        <div className="border-t border-ink" />
        <div className="mt-3 text-center font-serif text-[7.6px] leading-[1.35]">
          <div className="font-bold">Anonymous Author(s)</div>
          <div>Affiliation · Address</div>
          <div className="font-mono text-[6.5px]">email</div>
        </div>
      </div>
      <div style={show(1)}>
        <div className="mt-3 text-center font-serif text-[9.5px] font-bold">Abstract</div>
        <p className={`${body} mx-6 mt-1`}>
          Machine-learning weather models now rival physics-based forecasts on average skill, yet the heatwaves with the largest human cost
          are increasingly <i>record-shattering</i> — hotter than any state in the training data. We re-forecast all 47 record-shattering
          heat events of 2018–2023 with GraphCast and Pangu-Weather and compare them with IFS HRES against ERA5. AI models are more accurate on
          ordinary days, but their day-5 peak bias grows with record exceedance at −0.52 K/K versus −0.14 K/K for HRES (Δ = −0.38, 95% CI
          [−0.52, −0.25]). Counterfactual retraining on 1979–2005 shifts the failure to the earlier record, identifying the training
          distribution as causal. A tail-aware fine-tuning objective reduces held-out peak bias by 42% at a 0.6% cost in everyday RMSE.
        </p>
      </div>
      <div style={show(2)}>
        <div className={h1}>1&nbsp;&nbsp;Introduction</div>
        <p className={`${body} mt-1`}>
          Data-driven global models such as GraphCast {cite("1")} and Pangu-Weather {cite("2")} match or exceed the deterministic skill of
          ECMWF’s IFS HRES on standard benchmarks {cite("3")}. Their evaluation, however, is dominated by ordinary days. Climate change makes
          records not only more frequent but broken by larger margins {cite("4")}, as in the June 2021 Pacific Northwest heatwave {cite("5")}.
          Early comparisons on extremes are mixed {cite("6, 7")} and out-of-training behaviour has been studied for tropical cyclones {cite("8")},
          but no study has asked whether forecast error scales with <i>how far</i> an event leaves the training distribution.
        </p>
      </div>
      <div style={show(3)} className="mt-3">
        <div className="grid grid-cols-3 gap-2">
          <div><HeatMap /><div className="text-center font-serif text-[6.5px]">(a)</div></div>
          <div><Traces /><div className="text-center font-serif text-[6.5px]">(b)</div></div>
          <div><MiniScatter /><div className="text-center font-serif text-[6.5px]">(c)</div></div>
        </div>
        <p className="mt-1 font-serif text-[7px] leading-[1.35]">
          <b>Figure 1:</b> (a) ERA5 2 m temperature anomaly, 29 June 2021. (b) Peak-day forecasts at 5-day lead: ERA5 (solid), HRES (dashed),
          GraphCast (dotted), ours (grey). (c) Day-5 peak bias against record exceedance for 47 events; GraphCast (○), HRES (●).
        </p>
      </div>
      <div style={show(4)}>
        <p className={`${body} mt-2`}>
          We make three contributions: (i) a catalogue and hindcast archive of every post-training record heat event; (ii) evidence that AI
          error scales with exceedance and a counterfactual test showing the training record is the cause; and (iii) a tail-aware fine-tuning
          objective that closes most of the gap without degrading everyday skill.
        </p>
      </div>
      <div className="absolute bottom-3 left-[46px] font-serif text-[6.5px] text-muted">Preprint. Under review.</div>
    </div>
  );
}

export function PaperPage2({ reveal = 99 }: { reveal?: number }) {
  const show = (n: number) => ({ opacity: reveal >= n ? 1 : 0, transition: "opacity .5s" });
  const rows = [
    ["Persistence", "3.41", "−4.9", "−0.83", "0.04"],
    ["IFS HRES", "1.92", "**−1.1**", "**−0.14**", "**0.62**"],
    ["Pangu-Weather", "1.84", "−2.8", "−0.61", "0.28"],
    ["GraphCast", "**1.71**", "−2.6", "−0.52", "0.34"],
    ["GraphCast-TA (ours)", "1.72", "−1.5", "−0.21", "0.55"],
  ];
  const cell = (v: string) => (v.startsWith("**") ? <b>{v.slice(2, -2)}</b> : v);
  return (
    <div className={pageCls}>
      <div style={show(5)}>
        <div className={h1}>2&nbsp;&nbsp;Method</div>
        <p className={`${body} mt-1`}>
          For each grid cell we define the training record <i>R</i> as the 1979–2017 ERA5 maximum {cite("9")}. An event is a connected region where
          2018–2023 temperature exceeds it by ≥ 1 K. For event <i>e</i> with ERA5 peak <i>T</i> and forecast <i>T̂<sub>τ</sub></i> at lead τ:
        </p>
        <div className="my-1.5 flex justify-between px-8 font-serif text-[8.5px] italic">
          <span>x<sub>e</sub> = T<sub>e</sub> − R<sub>e</sub>,&nbsp;&nbsp; b<sub>e</sub>(τ) = max T̂<sub>τ</sub> − max T</span>
          <span className="not-italic">(1)</span>
        </div>
        <p className={body}>
          We fit b<sub>e</sub>(5d) = α + β x<sub>e</sub> per model with event-block bootstrap CIs. To test causation we retrain GraphCast-small on
          1979–2005 only. For the fix we fine-tune with a pinball loss on the hottest 1% of days:
        </p>
        <div className="my-1.5 flex justify-between px-8 font-serif text-[8.5px] italic">
          <span>ℒ = ℒ<sub>MSE</sub> + λ Σ ρ<sub>0.99</sub>(T − T̂) 𝟙[T &gt; q<sub>0.99</sub>]</span>
          <span className="not-italic">(2)</span>
        </div>
      </div>
      <div style={show(6)}>
        <div className={h1}>3&nbsp;&nbsp;Results</div>
        <p className="mt-1 text-center font-serif text-[7px]">
          <b>Table 1:</b> Day-5 skill on 2020 (all days) and on 47 record events (2018–2023). Best in bold.
        </p>
        <table className="mx-auto mt-1 w-full border-collapse font-serif text-[7.2px]">
          <thead>
            <tr className="border-y border-ink">
              {["Model", "RMSE all (K)", "Peak bias (K)", "Slope β (K/K)", "Record hit rate"].map((h) => (
                <th key={h} className="px-1 py-0.5 text-left font-normal">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r[0]} className={i === rows.length - 1 ? "border-y border-ink" : ""}>
                {r.map((v, j) => (
                  <td key={j} className="px-1 py-[1px]">
                    {cell(v)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <p className={`${body} mt-2`}>
          AI models are best on ordinary days but 2.4× more biased on record events, and their bias grows 3.7× faster with exceedance
          (Δβ = −0.38 K/K, <i>p</i> &lt; 0.001). The counterfactual model fails on events above the 2005 record that the full model handles
          (Fig. 2a), and day-5 AI forecasts lose 23% of energy at wavenumbers above 40 (Fig. 2b), consistent with regression to
          climatology under MSE training {cite("10")}. Tail-aware fine-tuning removes 42% of peak bias (−2.6 → −1.5 K).
        </p>
      </div>
      <div style={show(7)} className="mt-2">
        <div className="grid grid-cols-2 gap-4 px-6">
          <div><Bars /><div className="text-center font-serif text-[6.5px]">(a) counterfactual</div></div>
          <div><Spectra /><div className="text-center font-serif text-[6.5px]">(b) energy spectra</div></div>
        </div>
        <p className="mt-1 font-serif text-[7px] leading-[1.35]">
          <b>Figure 2:</b> (a) Peak bias on events between the 2005 and 2017 records. (b) Day-5 spectra: ERA5 (solid), GraphCast (dotted), ours (dashed).
        </p>
      </div>
      <div style={show(8)}>
        <div className={h1}>References</div>
        <ol className="mt-1 grid gap-[1px] font-serif text-[6.6px] leading-[1.3]">
          {[
            "R. Lam et al. Learning skillful medium-range global weather forecasting. Science, 2023.",
            "K. Bi et al. Accurate medium-range global weather forecasting with 3D neural networks. Nature, 2023.",
            "S. Rasp et al. WeatherBench 2. J. Adv. Model. Earth Syst., 2024.",
            "E. Fischer et al. Increasing probability of record-shattering climate extremes. Nat. Clim. Change, 2021.",
            "S. Philip et al. Rapid attribution analysis of the extraordinary heat wave on the Pacific coast… Earth Syst. Dynam., 2022.",
            "L. Olivetti, G. Messori. Do data-driven models beat numerical models in forecasting weather extremes? GMD, 2024.",
            "I. Lopez-Gomez et al. Global extreme heat forecasting using neural weather models. AIES, 2023.",
            "Y. Q. Sun et al. Can AI weather models predict out-of-training gray swan tropical cyclones? PNAS, 2025.",
            "H. Hersbach et al. The ERA5 global reanalysis. Q. J. R. Meteorol. Soc., 2020.",
            "M. Bonavita. On some limitations of current machine learning weather prediction models. GRL, 2024.",
          ].map((r, i) => (
            <li key={r} className="flex gap-1">
              <span>[{i + 1}]</span>
              <span className="flex-1">{r}</span>
              {reveal >= 9 && <span className="font-mono text-[6.5px]">✓</span>}
            </li>
          ))}
        </ol>
      </div>
      <div className="absolute bottom-3 left-0 right-0 text-center font-serif text-[7px]">2</div>
    </div>
  );
}


// ── Pages 3–8: related work, setup, extended results, discussion, appendix ─

function Para({ children }: { children: React.ReactNode }) {
  return <p className={`${body} mt-1.5`}>{children}</p>;
}

function SmallTable({ caption, head, rows }: { caption: string; head: string[]; rows: string[][] }) {
  return (
    <div className="mt-2">
      <p className="text-center font-serif text-[7px]">
        <b>{caption.split(":")[0]}:</b>
        {caption.slice(caption.indexOf(":") + 1)}
      </p>
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
          {rows.map((r, i) => (
            <tr key={i} className={i === rows.length - 1 ? "border-b border-ink" : ""}>
              {r.map((v, j) => (
                <td key={j} className="px-1 py-[1px]">
                  {v.startsWith("**") ? <b>{v.slice(2, -2)}</b> : v}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Fig({ caption, children }: { caption: string; children: React.ReactNode }) {
  return (
    <div className="mt-2">
      <div className="grid grid-cols-2 gap-4 px-4">{children}</div>
      <p className="mt-1 font-serif text-[7px] leading-[1.35]">
        <b>{caption.split(":")[0]}:</b>
        {caption.slice(caption.indexOf(":") + 1)}
      </p>
    </div>
  );
}

function Page({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <div className={pageCls}>
      {children}
      <div className="absolute bottom-3 left-0 right-0 text-center font-serif text-[7px]">{n}</div>
    </div>
  );
}

const PAGES_3_TO_8 = [
  <Page n={3} key={3}>
    <div className={h1}>4&nbsp;&nbsp;Related Work</div>
    <Para>
      <b>Machine-learning weather prediction.</b> Graph neural networks [1], 3D transformers [2], cascaded models (FuXi) and hybrid
      neural GCMs now match or exceed IFS HRES on headline scores. Probabilistic successors such as GenCast improve calibration on average
      days but are trained with the same reanalysis record, so their behaviour beyond it is not constrained by data.
    </Para>
    <Para>
      <b>Extremes and out-of-distribution events.</b> Studies of extremes compare AI and physics models on fixed thresholds [6, 7] and
      find mixed results. Sun et al. [8] removed strong tropical cyclones from training and observed that models could not produce them.
      We extend this logic to heat, and quantify error as a continuous function of exceedance rather than a binary hit or miss.
    </Para>
    <Para>
      <b>Record-shattering heat.</b> Records are increasingly broken by large margins [4]; the 2021 Pacific Northwest event exceeded
      prior station records by up to 5 K [5]. Such events are exactly where operational warnings matter most.
    </Para>
    <div className={h1}>5&nbsp;&nbsp;Experimental Setup</div>
    <Para>
      <b>Events.</b> We flag every 0.25° cell where 2018–2023 daily maximum 2 m temperature exceeds its 1979–2017 ERA5 maximum by ≥ 1 K,
      merge cells connected in space and within 3 days, and keep regions larger than 50,000 km². This yields 47 events on six continents.
    </Para>
    <Para>
      <b>Forecasts.</b> For each event we initialise GraphCast (0.25°, 37 levels) and Pangu-Weather from ERA5 at leads of 1, 3, 5, 7 and 10
      days before the peak and roll out 10 days. HRES forecasts come from the WeatherBench 2 archive. All forecasts are regridded
      conservatively to the ERA5 grid before scoring.
    </Para>
    <SmallTable
      caption="Table 2: Event catalogue summary by region."
      head={["Region", "Events", "Median x (K)", "Max x (K)"]}
      rows={[
        ["North America", "11", "2.4", "6.1"],
        ["Europe", "14", "2.1", "4.7"],
        ["Asia", "12", "2.6", "5.3"],
        ["Other", "10", "1.9", "3.8"],
      ]}
    />
  </Page>,
  <Page n={4} key={4}>
    <div className={h1}>6&nbsp;&nbsp;Extended Results</div>
    <Para>
      <b>Lead-time dependence.</b> At day 1 all models are within 0.4 K of ERA5 peaks. The gap opens with lead time: by day 5 AI bias is
      2.4× that of HRES and by day 7 it is 2.9×, while HRES bias grows roughly linearly (Fig. 3a).
    </Para>
    <Fig caption="Figure 3: (a) Peak bias by lead time for each model. (b) Slope β against lead time with 95% CIs.">
      <Traces />
      <MiniScatter />
    </Fig>
    <Para>
      <b>Robustness.</b> The slope difference holds when events are weighted by area, when the record is defined from 1990–2017, and when
      the 2021 Pacific Northwest event is removed (Δβ = −0.33, 95% CI [−0.48, −0.19]). It also holds for daily mean temperature.
    </Para>
    <SmallTable
      caption="Table 3: Robustness of Δβ (GraphCast − HRES, K/K)."
      head={["Variant", "Δβ", "95% CI"]}
      rows={[
        ["Main analysis", "**−0.38**", "[−0.52, −0.25]"],
        ["Area-weighted", "−0.36", "[−0.50, −0.22]"],
        ["Record from 1990–2017", "−0.41", "[−0.57, −0.26]"],
        ["Without PNW 2021", "−0.33", "[−0.48, −0.19]"],
        ["Daily mean T2m", "−0.29", "[−0.43, −0.16]"],
      ]}
    />
    <Para>
      <b>Counterfactual.</b> GraphCast-small trained on 1979–2005 matches the full model on events below the 2005 record but is 1.8× more
      biased on events between the 2005 and 2017 records (−2.4 vs −1.3 K), which lie inside the full model’s training range.
    </Para>
  </Page>,
  <Page n={5} key={5}>
    <div className={h1}>7&nbsp;&nbsp;Mechanism</div>
    <Para>
      Under MSE training, uncertain forecasts are pulled toward the conditional mean. When the true state lies beyond anything in training,
      that mean sits closer to climatology. Spectra confirm this: day-5 AI forecasts retain 77% of ERA5 energy at wavenumbers above 40,
      versus 96% for HRES, and the loss concentrates over the ridge that drives each heat dome.
    </Para>
    <Fig caption="Figure 4: (a) Energy spectra at day 5. (b) Peak bias for the full and counterfactual models.">
      <Spectra />
      <Bars />
    </Fig>
    <div className={h1}>8&nbsp;&nbsp;Tail-Aware Fine-Tuning</div>
    <Para>
      We fine-tune GraphCast for 4,000 steps with Eq. (2), λ = 0.3, on 1979–2017 only, so no evaluation event is seen. Held-out evaluation
      uses leave-one-event-cluster-out folds. Peak bias falls from −2.6 to −1.5 K and the slope from −0.52 to −0.21 K/K, while everyday
      RMSE changes by +0.6%.
    </Para>
    <SmallTable
      caption="Table 4: Ablation of the fine-tuning objective."
      head={["Objective", "Peak bias", "β", "RMSE all"]}
      rows={[
        ["MSE only (continued)", "−2.5", "−0.50", "1.71"],
        ["+ pinball, q = 0.95", "−1.9", "−0.33", "1.71"],
        ["+ pinball, q = 0.99 (ours)", "**−1.5**", "**−0.21**", "1.72"],
        ["+ pinball, q = 0.999", "−1.6", "−0.24", "1.76"],
      ]}
    />
  </Page>,
  <Page n={6} key={6}>
    <div className={h1}>9&nbsp;&nbsp;Discussion</div>
    <Para>
      Our results reconcile two views in the literature: AI models are both more skilful than physics models on average and less reliable
      on the events that matter most. The failure is systematic rather than random — it grows with distance from the training record — and
      it is therefore predictable. Forecast centres could use exceedance of the model’s own training record as a flag for when to trust
      physics guidance.
    </Para>
    <Para>
      Because the climate is warming, the fraction of forecasts made outside the training distribution will rise each year. Retraining on
      newer data delays the problem but does not remove it; objectives that weight the tail, as here, address it directly.
    </Para>
    <div className={h1}>10&nbsp;&nbsp;Limitations</div>
    <Para>
      ERA5 itself underestimates station-level extremes, so absolute biases are conservative. We test two deterministic AI models; ensemble
      systems may behave differently. Only 47 events qualify, and few exceed the record by more than 5 K, widening uncertainty at the tail.
      Fine-tuning was evaluated on heat only; effects on cold extremes and precipitation remain to be tested.
    </Para>
    <div className={h1}>11&nbsp;&nbsp;Conclusion</div>
    <Para>
      AI weather models underpredict record-shattering heat in proportion to how far it exceeds their training record. A counterfactual
      shows the training record is the cause, and a simple tail-aware objective removes 42% of the error at negligible cost to everyday skill.
    </Para>
    <div className={h1}>Broader Impact</div>
    <Para>Heat is the deadliest weather hazard. Better calibrated warnings for unprecedented events could save lives; over-trusting AI forecasts during record heat could cost them.</Para>
  </Page>,
  <Page n={7} key={7}>
    <div className={h1}>References (continued)</div>
    <ol className="mt-1 grid gap-[2px] font-serif text-[6.8px] leading-[1.35]" start={11}>
      {[
        "R. Price et al. Probabilistic weather forecasting with machine learning. Nature, 2025.",
        "D. Kochkov et al. Neural general circulation models for weather and climate. Nature, 2024.",
        "L. Chen et al. FuXi: a cascade machine learning forecasting system. npj Clim. Atmos. Sci., 2023.",
        "C. Bodnar et al. A foundation model for the Earth system. Nature, 2025.",
        "S. Lang et al. AIFS – ECMWF’s data-driven forecasting system. arXiv, 2024.",
        "Z. Ben Bouallègue et al. The rise of data-driven weather forecasting. BAMS, 2024.",
        "T. Selz, G. Craig. Can AI-based weather prediction models simulate the butterfly effect? GRL, 2023.",
        "V. Thompson et al. The most at-risk regions in the world for high-impact heatwaves. Nat. Commun., 2023.",
        "S. Coles. An Introduction to Statistical Modeling of Extreme Values. Springer, 2001.",
        "S. Ravuri et al. Skilful precipitation nowcasting using deep generative models of radar. Nature, 2021.",
        "J. Pathak et al. FourCastNet. arXiv, 2022.",
      ].map((r, i) => (
        <li key={r} className="flex gap-1">
          <span>[{i + 11}]</span>
          <span className="flex-1">{r}</span>
          <span className="font-mono text-[6.5px]">✓</span>
        </li>
      ))}
    </ol>
    <p className="mt-2 font-serif text-[6.8px] italic text-muted">… 30 further references, all from the literature review.</p>
    <div className={h1}>A&nbsp;&nbsp;Reproducibility</div>
    <Para>
      All code, the event catalogue, 2,350 forecasts and fine-tuned weights are released with the research package. Data access uses three
      MCP servers written during the run (era5-arco, forecast-runner, hres-archive). Every number in this paper is regenerated from
      results/metrics.csv by a single script.
    </Para>
  </Page>,
  <Page n={8} key={8}>
    <div className={h1}>B&nbsp;&nbsp;Per-Event Results</div>
    <SmallTable
      caption="Table 5: Day-5 peak bias (K) for the ten largest record exceedances."
      head={["Event", "x (K)", "HRES", "GraphCast", "Pangu", "Ours"]}
      rows={[
        ["Pacific NW, Jun 2021", "6.1", "−1.9", "−4.6", "−5.0", "−2.4"],
        ["W. Siberia, Jun 2020", "5.3", "−1.4", "−3.9", "−4.4", "−2.1"],
        ["NW China, Jul 2023", "4.9", "−1.6", "−3.8", "−4.1", "−2.0"],
        ["UK, Jul 2022", "4.7", "−1.2", "−3.6", "−3.9", "−1.8"],
        ["Sicily, Aug 2021", "4.4", "−1.3", "−3.3", "−3.8", "−1.9"],
        ["Yangtze, Aug 2022", "4.1", "−1.0", "−3.1", "−3.4", "−1.6"],
        ["Iberia, Jul 2022", "3.9", "−1.1", "−3.0", "−3.3", "−1.7"],
        ["S. France, Jun 2019", "3.8", "−0.9", "−2.9", "−3.2", "−1.5"],
        ["Canada NWT, Jul 2021", "3.6", "−1.2", "−2.8", "−3.1", "−1.6"],
        ["Mexico, Jun 2023", "3.4", "−1.0", "−2.6", "−2.9", "−1.4"],
      ]}
    />
    <div className={h1}>C&nbsp;&nbsp;Hyperparameters</div>
    <SmallTable
      caption="Table 6: Fine-tuning configuration."
      head={["Setting", "Value"]}
      rows={[
        ["Base checkpoint", "GraphCast 0.25°, 37 levels"],
        ["Steps / batch", "4,000 / 16"],
        ["Learning rate", "3e-6, cosine"],
        ["λ (Eq. 2)", "0.3"],
        ["Quantile q", "0.99"],
        ["Training years", "1979–2017"],
      ]}
    />
  </Page>,
];

/** The heatwave paper's eight pages, full size. */
export function heatwavePages() {
  return [<PaperPage1 key={1} />, <PaperPage2 key={2} />, ...PAGES_3_TO_8];
}

/** All eight pages as thumbnails, for the report card. */
export function PaperPreview() {
  const pages = heatwavePages();
  return (
    <div className="grid w-full grid-cols-4 gap-3 px-4">
      {pages.map((pg, i) => (
        <div key={i} className="h-[200px] overflow-hidden">
          <div className="origin-top-left scale-[0.28]">{pg}</div>
        </div>
      ))}
    </div>
  );
}

const LATEX = String.raw`\documentclass{article}
\usepackage[preprint]{neurips_2025}
\usepackage{booktabs,amsmath,graphicx}
\title{Out of Distribution, Out of Reach: AI Weather
       Models Underpredict Record-Shattering Heatwaves}
\begin{document}\maketitle
\begin{abstract}
Machine-learning weather models now rival physics-based
forecasts on average skill, yet the deadliest heatwaves
are increasingly \emph{record-shattering}. We re-forecast
all 47 such events of 2018--2023 ... \citep{lam2023,bi2023}
\end{abstract}
\section{Introduction}
... broken by larger margins \citep{fischer2021} ...
\begin{figure}[t]\includegraphics{fig1_events}\end{figure}
\section{Method}
\begin{equation}
  b_e(\tau) = \max \hat{T}_\tau - \max T
\end{equation}
\begin{equation}
  \mathcal{L} = \mathcal{L}_{\mathrm{MSE}}
    + \lambda \sum \rho_{0.99}(T-\hat{T})\,\mathbb{1}[T>q_{0.99}]
\end{equation}
\section{Results}
\begin{table}\centering\begin{tabular}{lcccc}\toprule
Model & RMSE & Bias & $\beta$ & Hit \\ \midrule
GraphCast-TA (ours) & 1.72 & $-1.5$ & $-0.21$ & 0.55 \\
\bottomrule\end{tabular}\end{table}
\bibliography{references}`;

export function PaperWriter({ speed }: { speed: number }) {
  const t = useClock(speed);
  const src = typed(LATEX, t, 200, 170);
  const reveal = Math.floor(clamp((t - 400) / 5200) * 9.99);
  const scroll = ramp(t, 3600, 5600);
  const grid = t > 6000;
  return (
    <Scene
      kicker="07 · Report · writing"
      title="It writes the paper — NeurIPS format, citing only what it read"
      right={<span className="flex items-center gap-2">{t < 9200 ? <><Pulse /> tectonic paper.tex</> : "✓ paper.pdf · 8 pages"}</span>}
    >
      <div className="grid h-full grid-cols-[0.85fr_1.15fr] gap-6">
        <div className="flex min-h-0 flex-col border border-ink bg-ink text-paper">
          <div className="flex items-center justify-between border-b border-paper/20 px-4 py-2">
            <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-faint">paper/paper.tex · Report Agent</span>
            <span className="font-mono text-[10px] text-faint">{src.split("\n").length} lines</span>
          </div>
          <pre className="caret min-h-0 flex-1 overflow-hidden whitespace-pre-wrap px-4 py-3 font-mono text-[10.8px] leading-[1.55] text-paper/90">{src}</pre>
          {t > 8000 && (
            <div className="film-pop border-t-2 border-paper bg-paper px-5 py-4 text-ink">
              <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">Integrity check · references.bib built from the review</div>
              <div className="mt-1 font-serif text-[19px] leading-snug">52 citations · all 52 from the 118 papers it read · 0 invented</div>
            </div>
          )}
        </div>
        <div className="relative min-h-0 overflow-hidden">
          {grid ? (
            <div className="grid grid-cols-4 gap-x-3 gap-y-4 pt-1">
              {[<PaperPage1 key={1} />, <PaperPage2 key={2} />, ...PAGES_3_TO_8].map((pg, i) => (
                <div key={i} className="film-pop h-[250px] overflow-hidden" style={{ animationDelay: `${i * 110}ms` }}>
                  <div className="origin-top-left scale-[0.34]">{pg}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center gap-6 pt-1" style={{ transform: `translateY(${-scroll * 600}px)` }}>
              <div className="film-pop">
                <PaperPage1 reveal={reveal} />
              </div>
              <PaperPage2 reveal={reveal} />
            </div>
          )}
        </div>
      </div>
    </Scene>
  );
}
