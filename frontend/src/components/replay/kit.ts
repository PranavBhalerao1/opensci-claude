// Builders shared by the replay datasets and the player.
import type { Gap, LitPaper, MasterPlan, Message, ResearchPlan, Run, TaskState } from "@/lib/api";

export const now = () => new Date().toISOString();
export const ago = (s: number) => new Date(Date.now() - s * 1000).toISOString();

export function run<T = Run>(kind: string, id: string, over: Partial<T> = {}): T {
  return {
    id,
    kind,
    status: "running",
    phase: "starting",
    counts: {},
    log: [],
    result: null,
    error: null,
    started_at: now(),
    finished_at: null,
    ...over,
  } as unknown as T;
}

export function message<K extends Message["kind"]>(
  pid: string,
  id: string,
  role: "user" | "assistant",
  kind: K,
  payload: Extract<Message, { kind: K }>["payload"],
  content = "",
): Extract<Message, { kind: K }> {
  return { id, project_id: pid, role, content, created_at: now(), kind, payload } as Extract<Message, { kind: K }>;
}

export const paper = (
  id: string,
  title: string,
  authors: string[],
  year: number,
  venue: string,
  citations: number,
  relevance: number,
  origin: "search" | "citation" = "search",
): LitPaper => ({
  id,
  title,
  abstract: null,
  tldr: null,
  year,
  venue,
  authors,
  citation_count: citations,
  doi: null,
  url: null,
  pdf_url: null,
  notes: null,
  relevance,
  reason: null,
  origin,
});

export const score = (s: number, why = "") => ({ score: s, why });

/** A short candidate gap (the runners-up below the chosen one). */
export function minorGap(id: string, title: string, gap_type: string, scores: [number, number, number, number], status: "partially_addressed" | "unchecked", explanation: string): Gap {
  const [novelty, feasibility, impact, testability] = scores;
  return {
    id,
    title,
    question: title,
    gap_type,
    why_open: explanation,
    hypothesis: "",
    approach: "",
    data_needed: "",
    compute_needed: "OpenScientist Cloud",
    risks: [],
    supporting_paper_ids: [],
    novelty_queries: [],
    scores: { novelty: score(novelty), feasibility: score(feasibility), impact: score(impact), testability: score(testability) },
    novelty_check: { status, explanation, closest: [] },
    overall: Math.round(((novelty + feasibility + impact + testability) / 4) * 100) / 100,
  };
}

export const planTask = (id: string, title: string, kind: string, depends_on: string[], effort: "S" | "M" | "L" = "M"): ResearchPlan["phases"][number]["tasks"][number] => ({
  id,
  title,
  description: "",
  kind,
  inputs: [],
  outputs: [],
  depends_on,
  effort,
  tools_hint: [],
});

export const bpTask = (id: string, title: string, agent: string, depends_on: string[], objective: string, est = 30, cost = 2): MasterPlan["tasks"][number] => ({
  id,
  title,
  agent,
  objective,
  steps: [],
  inputs: [],
  outputs: [],
  acceptance_checks: [],
  depends_on,
  tools: ["run_python"],
  resources: [],
  compute: { kind: "cpu", est_minutes: est, timeout_minutes: est * 3 },
  max_cost_usd: cost,
  retries: 2,
  human_required: false,
});

export function taskState(id: string, agent: string, over: Partial<TaskState> = {}): TaskState {
  return {
    id: `ts-${id}`,
    task_id: id,
    agent,
    status: "pending",
    attempts: 0,
    cost: 0,
    summary: null,
    artifacts: [],
    checks: [],
    issues: [],
    events: [],
    note: null,
    started_at: null,
    finished_at: null,
    ...over,
  };
}

/**
 * When each task runs during the replay, in ms from the start of execution: every task starts once
 * its dependencies are done (at most `parallel` at a time) and runs for a time that grows with its
 * estimated minutes, scaled so the whole stage lasts about `total` ms.
 */
export function schedule(master: MasterPlan, total: number, parallel = 4): Record<string, { start: number; end: number }> {
  const dur: Record<string, number> = {};
  for (const t of master.tasks) dur[t.id] = 8 + Math.sqrt(t.compute.est_minutes) * 3;
  const out: Record<string, { start: number; end: number }> = {};
  const done = new Set<string>();
  const running: { id: string; end: number }[] = [];
  let clock = 0;
  while (done.size < master.tasks.length) {
    for (const t of master.tasks) {
      if (out[t.id] || running.length >= parallel) continue;
      if (t.depends_on.every((d) => done.has(d))) {
        out[t.id] = { start: clock, end: clock + dur[t.id] };
        running.push({ id: t.id, end: clock + dur[t.id] });
      }
    }
    running.sort((a, b) => a.end - b.end);
    const next = running.shift();
    if (!next) break; // a cycle; never happens with a valid blueprint
    clock = next.end;
    done.add(next.id);
  }
  const scale = total / Math.max(clock, 1);
  for (const id in out) out[id] = { start: out[id].start * scale, end: out[id].end * scale };
  return out;
}
