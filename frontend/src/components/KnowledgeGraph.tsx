"use client";

import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import { useEffect, useMemo, useRef, useState } from "react";

import { literatureApi, type GraphLink, type GraphNode } from "@/lib/api";

type Node = GraphNode & SimulationNodeDatum & { r: number };
type Link = SimulationLinkDatum<Node> & { kind: GraphLink["kind"] };

const W = 900;
const H = 640;
const KINDS = ["method", "dataset", "task"] as const;

function radius(n: GraphNode) {
  if (n.kind === "paper") return 3 + Math.min(7, Math.log10((n.citations ?? 0) + 1) * 2.4);
  return 4 + Math.min(10, Math.sqrt(n.count ?? 1) * 2.2);
}

/** Lays out once (synchronously) so the graph is stable and cheap to hover. */
function layout(nodes: GraphNode[], links: GraphLink[]) {
  const ns: Node[] = nodes.map((n) => ({ ...n, r: radius(n) }));
  const ls: Link[] = links.map((l) => ({ source: l.source, target: l.target, kind: l.kind }));
  forceSimulation(ns)
    .force(
      "link",
      forceLink<Node, Link>(ls)
        .id((d) => d.id)
        .distance((l) => (l.kind === "cites" ? 40 : 60))
        .strength((l) => (l.kind === "cites" ? 0.25 : 0.12)),
    )
    .force("charge", forceManyBody<Node>().strength((d) => (d.kind === "paper" ? -30 : -120)))
    .force("collide", forceCollide<Node>((d) => d.r + 3))
    .force("center", forceCenter(W / 2, H / 2))
    .stop()
    .tick(320);

  // Fit to the viewBox.
  const xs = ns.map((n) => n.x ?? 0);
  const ys = ns.map((n) => n.y ?? 0);
  const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const s = Math.min((W - 80) / (maxX - minX || 1), (H - 80) / (maxY - minY || 1), 2);
  for (const n of ns) {
    n.x = 40 + ((n.x ?? 0) - minX) * s + (W - 80 - (maxX - minX) * s) / 2;
    n.y = 40 + ((n.y ?? 0) - minY) * s + (H - 80 - (maxY - minY) * s) / 2;
  }
  return { nodes: ns, links: ls };
}

export default function KnowledgeGraph({
  projectId,
  onSelectPaper,
}: {
  projectId: string;
  onSelectPaper: (id: string) => void;
}) {
  const [data, setData] = useState<{ nodes: GraphNode[]; links: GraphLink[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [showCites, setShowCites] = useState(true);
  const svg = useRef<SVGSVGElement>(null);

  useEffect(() => {
    literatureApi.graph(projectId).then(setData).catch((e) => setError(String(e)));
  }, [projectId]);

  const graph = useMemo(() => (data ? layout(data.nodes, data.links) : null), [data]);

  const neighbours = useMemo(() => {
    const m = new Map<string, Set<string>>();
    for (const l of graph?.links ?? []) {
      const [a, b] = [(l.source as Node).id, (l.target as Node).id];
      if (!m.has(a)) m.set(a, new Set());
      if (!m.has(b)) m.set(b, new Set());
      m.get(a)!.add(b);
      m.get(b)!.add(a);
    }
    return m;
  }, [graph]);

  if (error) return <p className="p-6 font-mono text-[12px]">{error}</p>;
  if (!graph) return <p className="p-6 font-mono text-[12px] text-muted">Laying out graph…</p>;

  const visible = (n: Node) => !hidden.has(n.kind);
  const lit = (id: string) => !hover || hover === id || neighbours.get(hover)?.has(id);
  const hovered = graph.nodes.find((n) => n.id === hover);
  const counts = Object.fromEntries(KINDS.map((k) => [k, graph.nodes.filter((n) => n.kind === k).length]));
  const citeCount = graph.links.filter((l) => l.kind === "cites").length;

  const toggle = (k: string) =>
    setHidden((h) => {
      const next = new Set(h);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-x-5 gap-y-2 border-b border-rule px-6 py-3 font-mono text-[11px] text-muted">
        <Legend shape="paper" label={`Papers ${graph.nodes.length - KINDS.reduce((a, k) => a + counts[k], 0)}`} />
        {KINDS.map((k) => (
          <button key={k} onClick={() => toggle(k)} className={hidden.has(k) ? "opacity-30" : ""}>
            <Legend shape={k} label={`${k[0].toUpperCase()}${k.slice(1)}s ${counts[k]}`} />
          </button>
        ))}
        <button onClick={() => setShowCites(!showCites)} className={showCites ? "" : "opacity-30"}>
          <span className="mr-1.5 inline-block h-px w-4 bg-ink align-middle" />
          Citations {citeCount}
        </button>
        <span className="ml-auto text-faint">Hover to trace · click a paper to open it</span>
      </div>

      <div className="relative min-h-0 flex-1">
        <svg ref={svg} viewBox={`0 0 ${W} ${H}`} className="h-full w-full" role="img" aria-label="Knowledge graph">
          <g>
            {graph.links.map((l, i) => {
              const s = l.source as Node;
              const t = l.target as Node;
              if (!visible(s) || !visible(t) || (l.kind === "cites" && !showCites)) return null;
              const on = hover && (hover === s.id || hover === t.id);
              return (
                <line
                  key={i}
                  x1={s.x}
                  y1={s.y}
                  x2={t.x}
                  y2={t.y}
                  stroke="#0a0a0a"
                  strokeOpacity={on ? 0.7 : hover ? 0.03 : l.kind === "cites" ? 0.22 : 0.08}
                  strokeWidth={on ? 1 : 0.6}
                  strokeDasharray={l.kind === "mentions" ? "2 2" : undefined}
                />
              );
            })}
          </g>
          <g>
            {graph.nodes.filter(visible).map((n) => (
              <g
                key={n.id}
                transform={`translate(${n.x},${n.y})`}
                opacity={lit(n.id) ? 1 : 0.12}
                onMouseEnter={() => setHover(n.id)}
                onMouseLeave={() => setHover(null)}
                onClick={() => n.kind === "paper" && onSelectPaper(n.id)}
                className={n.kind === "paper" ? "cursor-pointer" : "cursor-default"}
              >
                <Shape kind={n.kind} r={n.r} />
                {n.kind !== "paper" && (n.count ?? 0) >= 4 && (
                  <text y={n.r + 11} textAnchor="middle" className="fill-ink font-mono text-[9px]">
                    {n.label.length > 22 ? n.label.slice(0, 21) + "…" : n.label}
                  </text>
                )}
              </g>
            ))}
          </g>
        </svg>

        {hovered && (
          <div className="pointer-events-none absolute left-6 top-4 max-w-sm border border-ink bg-paper px-3 py-2">
            <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-faint">{hovered.kind}</div>
            <div className="text-[13px] leading-snug">{hovered.label}</div>
            <div className="mt-0.5 font-mono text-[11px] text-muted">
              {hovered.kind === "paper"
                ? `${hovered.year ?? "n.d."} · ${hovered.citations ?? 0} citations · ${neighbours.get(hovered.id)?.size ?? 0} links`
                : `in ${hovered.count} papers`}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Shape({ kind, r }: { kind: GraphNode["kind"]; r: number }) {
  switch (kind) {
    case "paper":
      return <circle r={r} fill="#0a0a0a" />;
    case "method":
      return <rect x={-r} y={-r} width={2 * r} height={2 * r} fill="#fff" stroke="#0a0a0a" strokeWidth={1.2} />;
    case "dataset":
      return <polygon points={`0,${-r * 1.3} ${r * 1.3},0 0,${r * 1.3} ${-r * 1.3},0`} fill="#fff" stroke="#0a0a0a" strokeWidth={1.2} />;
    case "task":
      return <circle r={r} fill="#fff" stroke="#0a0a0a" strokeWidth={1.2} strokeDasharray="2 1.5" />;
  }
}

function Legend({ shape, label }: { shape: GraphNode["kind"]; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <svg width="12" height="12" viewBox="-6 -6 12 12" aria-hidden>
        <Shape kind={shape} r={4} />
      </svg>
      {label}
    </span>
  );
}
