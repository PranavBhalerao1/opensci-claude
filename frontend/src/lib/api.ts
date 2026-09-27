export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Stage = "clarify" | "literature" | "gaps" | "plan" | "done" | "blueprint" | "ready" | "executing" | "executed";

export type Depth = "quick" | "standard" | "deep";

export interface ProjectSettings {
  depth?: Depth;
  max_papers?: number;
  citation_hops?: number;
  budget?: { llm_usd: number; gpu_hours: number };
  model_policy?: ModelPolicy;
}

export type ModelPolicy = "default" | "economy" | "minimal";

export interface KeyConcept {
  term: string;
  definition: string;
}

export interface ResearchBrief {
  title: string;
  core_question: string;
  summary: string;
  domain: string;
  subfields: string[];
  key_concepts: KeyConcept[];
  scope_in: string[];
  scope_out: string[];
  result_type: string;
  data_resources: string;
  compute_resources: string;
  user_expertise: string;
  constraints: string[];
  search_keywords: string[];
  assumptions: string[];
}

export interface Project {
  id: string;
  title: string;
  stage: Stage;
  autonomous: boolean;
  settings: ProjectSettings;
  brief: ResearchBrief | null;
  chosen_gap: (Gap & { run_id: string }) | null;
  plan: (ResearchPlan & { run_id: string; approved_at: string }) | null;
  blueprint: { run_id: string; approved_at: string } | null;
  created_at: string;
  updated_at: string;
}

export interface Option {
  label: string;
  detail: string;
}

export interface Question {
  id: string;
  question: string;
  why: string;
  options: Option[];
  multi: boolean;
}

export interface Answer {
  question_id: string;
  selected: string[];
  other: string | null;
  rationale?: string;
}

interface BaseMessage {
  id: string;
  project_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export type Message =
  | (BaseMessage & { kind: "text"; payload: null })
  | (BaseMessage & { kind: "questions"; payload: { message: string; questions: Question[]; round: number } })
  | (BaseMessage & { kind: "answers"; payload: { question_message_id: string; answers: Answer[]; auto: boolean } })
  | (BaseMessage & { kind: "brief"; payload: { message: string; brief: ResearchBrief } });

export const NOT_SURE = "Not sure — decide for me";

export const DEPTHS: { key: Depth; label: string; papers: number; note: string }[] = [
  { key: "quick", label: "Quick", papers: 30, note: "~30 papers" },
  { key: "standard", label: "Standard", papers: 100, note: "~100 papers" },
  { key: "deep", label: "Deep", papers: 300, note: "~300 papers + citations" },
];

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  listProjects: () => fetch(`${API_URL}/api/projects`).then(json<Project[]>),
  getProject: (id: string) =>
    fetch(`${API_URL}/api/projects/${id}`).then(json<{ project: Project; messages: Message[] }>),
  createProject: (body: { autonomous?: boolean } = {}) =>
    fetch(`${API_URL}/api/projects`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }).then(json<Project>),
  deleteProject: (id: string) => fetch(`${API_URL}/api/projects/${id}`, { method: "DELETE" }),
  confirmBrief: (id: string, body: { depth: Depth; max_papers: number }) =>
    fetch(`${API_URL}/api/projects/${id}/brief/confirm`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }).then(json<Project>),
};

export type Turn =
  | { kind: "text"; content: string }
  | { kind: "answers"; question_message_id: string; answers: Answer[] };

export type StreamEvent =
  | { event: "message"; data: Message }
  | { event: "status"; data: { text: string } }
  | { event: "delta"; data: { text: string } }
  | { event: "project"; data: Project }
  | { event: "error"; data: { message: string } }
  | { event: "done"; data: Record<string, never> };

/** POST a user turn and yield server-sent events as they arrive. */
export async function* sendTurn(projectId: string, turn: Turn): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${API_URL}/api/projects/${projectId}/messages`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(turn),
  });
  if (!res.ok || !res.body) throw new Error(`${res.status} ${await res.text()}`);

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value.replace(/\r\n/g, "\n");
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
      }
      if (data.length) yield { event, data: JSON.parse(data.join("\n")) } as StreamEvent;
    }
  }
}

// ── Literature ─────────────────────────────────────────────────────────────

export interface PaperNotes {
  contribution: string;
  problem: string;
  study_type: string;
  methods: string[];
  datasets: string[];
  tasks: string[];
  metrics: string[];
  key_findings: string[];
  limitations: string[];
}

export interface LitPaper {
  id: string;
  title: string;
  abstract: string | null;
  tldr: string | null;
  year: number | null;
  venue: string | null;
  authors: string[];
  citation_count: number;
  doi: string | null;
  url: string | null;
  pdf_url: string | null;
  notes: PaperNotes | null;
  relevance: number | null;
  reason: string | null;
  origin: "search" | "citation";
}

export interface Theme {
  name: string;
  description: string;
  paper_ids: string[];
}

export interface Overview {
  summary: string;
  themes: Theme[];
  common_methods: string[];
  common_datasets: string[];
  open_problems: string[];
}

export interface Run {
  id: string;
  kind: string;
  status: "running" | "done" | "error";
  phase: string;
  counts: Partial<Record<
    "queries_done" | "queries_total" | "found" | "candidates" | "screened" | "included" | "extracted",
    number
  >>;
  log: { t: string; text: string }[];
  result: { overview: Overview } | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface Literature {
  run: Run | null;
  papers: LitPaper[];
}

export interface GraphNode {
  id: string;
  kind: "paper" | "method" | "dataset" | "task";
  label: string;
  year?: number | null;
  citations?: number;
  relevance?: number | null;
  count?: number;
}

export interface GraphLink {
  source: string;
  target: string;
  kind: "mentions" | "cites";
}

export const literatureApi = {
  get: (id: string) => fetch(`${API_URL}/api/projects/${id}/literature`).then(json<Literature>),
  rerun: (id: string) => fetch(`${API_URL}/api/projects/${id}/literature/run`, { method: "POST" }).then(json<Run>),
  graph: (id: string) =>
    fetch(`${API_URL}/api/projects/${id}/graph`).then(json<{ nodes: GraphNode[]; links: GraphLink[] }>),
};

// ── Gaps ───────────────────────────────────────────────────────────────────

export interface GapScore {
  score: number;
  why: string;
}

export interface ClosestWork {
  title: string;
  year: number | null;
  url: string | null;
  in_review: boolean;
  overlap: string;
}

export interface Gap {
  id: string;
  title: string;
  question: string;
  gap_type: string;
  why_open: string;
  hypothesis: string;
  approach: string;
  data_needed: string;
  compute_needed: string;
  risks: string[];
  supporting_paper_ids: string[];
  novelty_queries: string[];
  scores: Record<"novelty" | "feasibility" | "impact" | "testability", GapScore>;
  novelty_check: {
    status: "novel" | "partially_addressed" | "already_done" | "unchecked";
    explanation: string;
    closest: ClosestWork[];
  };
  overall: number;
}

export interface GapsRun extends Omit<Run, "result"> {
  result: { gaps: Gap[]; recommended: string; feedback: string | null } | null;
}

export const gapsApi = {
  get: (id: string) => fetch(`${API_URL}/api/projects/${id}/gaps`).then(json<{ run: GapsRun | null; project: Project }>),
  rerun: (id: string, feedback?: string) =>
    fetch(`${API_URL}/api/projects/${id}/gaps/run`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ feedback: feedback ?? null }),
    }).then(json<GapsRun>),
  select: (id: string, gapId: string) =>
    fetch(`${API_URL}/api/projects/${id}/gaps/select`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ gap_id: gapId }),
    }).then(json<Project>),
};

// ── Plan ───────────────────────────────────────────────────────────────────

export interface PlanTask {
  id: string;
  title: string;
  description: string;
  kind: string;
  inputs: string[];
  outputs: string[];
  depends_on: string[];
  effort: "S" | "M" | "L";
  tools_hint: string[];
}

export interface ResearchPlan {
  title: string;
  research_question: string;
  hypothesis: string;
  null_hypothesis: string;
  objectives: string[];
  background: string;
  study_type: string;
  phases: { id: string; name: string; goal: string; tasks: PlanTask[] }[];
  datasets: { name: string; description: string; source: string; access: string; role: string }[];
  methods: { name: string; purpose: string }[];
  baselines: string[];
  metrics: { name: string; definition: string; success_threshold: string }[];
  validation_strategy: string;
  success_criteria: string[];
  compute_estimate: string;
  duration_estimate: string;
  risks: { risk: string; likelihood: "low" | "medium" | "high"; mitigation: string }[];
  deliverables: string[];
  open_questions: string[];
}

export interface PlanRun extends Omit<Run, "result"> {
  result: { plan: ResearchPlan; gap_id: string; gaps_run_id: string; instruction?: string } | null;
}

export class PlanEditError extends Error {
  constructor(public errors: string[]) {
    super(errors.join("\n"));
  }
}

export const planApi = {
  get: (id: string) =>
    fetch(`${API_URL}/api/projects/${id}/plan`).then(json<{ run: PlanRun | null; project: Project; revisions: number }>),
  rerun: (id: string) => fetch(`${API_URL}/api/projects/${id}/plan/run`, { method: "POST" }).then(json<PlanRun>),
  revise: (id: string, instruction: string) =>
    fetch(`${API_URL}/api/projects/${id}/plan/revise`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ instruction }),
    }).then(json<{ message: Message; run: PlanRun }>),
  edit: async (id: string, plan: unknown) => {
    const res = await fetch(`${API_URL}/api/projects/${id}/plan`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ plan }),
    });
    if (res.status === 422) {
      const body = await res.json();
      throw new PlanEditError(body.detail?.errors ?? ["Invalid plan"]);
    }
    return json<PlanRun>(res);
  },
  approve: (id: string) =>
    fetch(`${API_URL}/api/projects/${id}/plan/approve`, { method: "POST" }).then(json<Project>),
  fileUrl: (id: string, name: string) => `${API_URL}/api/projects/${id}/files/${name}`,
};

// ── Blueprint ──────────────────────────────────────────────────────────────

export interface BpAgent {
  id: string;
  name: string;
  model_tier: "reasoning" | "standard" | "bulk";
  tools: string[];
  instructions: string;
}

export interface BpTask {
  id: string;
  title: string;
  agent: string;
  objective: string;
  steps: string[];
  inputs: { path: string; source: string }[];
  outputs: { path: string; format: string; description: string }[];
  acceptance_checks: string[];
  depends_on: string[];
  tools: string[];
  resources: string[];
  compute: { kind: "cpu" | "apple_gpu" | "cuda_gpu"; est_minutes: number; timeout_minutes: number };
  max_cost_usd: number;
  retries: number;
  human_required: boolean;
}

export interface MasterPlan {
  title: string;
  summary: string;
  python_packages: string[];
  system_requirements: string[];
  agents: BpAgent[];
  datasets: {
    id: string;
    name: string;
    url: string | null;
    access_method: string;
    format: string;
    license: string;
    notes: string;
    verified: boolean;
  }[];
  tasks: BpTask[];
  checkpoints: { after_task: string; reason: string }[];
  llm_usd_estimate: number;
  compute_hours_estimate: number;
  execution_notes: string[];
}

export interface BlueprintRun extends Omit<Run, "result"> {
  result: {
    master_plan: MasterPlan;
    warnings: string[];
    capabilities: string[];
    budget: { llm_usd: number; gpu_hours: number };
    instruction?: string;
  } | null;
}

export const blueprintApi = {
  get: (id: string) =>
    fetch(`${API_URL}/api/projects/${id}/blueprint`).then(json<{ run: BlueprintRun | null; project: Project }>),
  run: (id: string) => fetch(`${API_URL}/api/projects/${id}/blueprint/run`, { method: "POST" }).then(json<BlueprintRun>),
  revise: (id: string, instruction: string) =>
    fetch(`${API_URL}/api/projects/${id}/blueprint/revise`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ instruction }),
    }).then(json<{ message: Message; run: BlueprintRun }>),
  approve: (id: string) =>
    fetch(`${API_URL}/api/projects/${id}/blueprint/approve`, { method: "POST" }).then(json<Project>),
};

export const usageApi = {
  get: (id: string) =>
    fetch(`${API_URL}/api/projects/${id}/usage`).then(
      json<{ total: number; by_model: Record<string, number>; calls: number }>,
    ),
};

// ── Execution ──────────────────────────────────────────────────────────────

export interface AgentEvent {
  type: "tool" | "message";
  step: number;
  tool?: string;
  args?: string;
  result?: string;
  text?: string;
  cost: number;
  t: string;
}

export interface TaskState {
  id: string;
  task_id: string;
  agent: string;
  status: "pending" | "running" | "done" | "failed" | "blocked" | "human" | "skipped" | "cancelled";
  attempts: number;
  cost: number;
  summary: string | null;
  artifacts: string[];
  checks: { check: string; passed: boolean; reason: string }[];
  issues: string[];
  events: AgentEvent[];
  note: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface Execution {
  run: Run | null;
  project: Project;
  tasks: TaskState[];
  spent: number;
  budget: number;
  model_policy: ModelPolicy;
  paused: string | null;
  live: boolean;
}

const post = (url: string, body: unknown = {}) =>
  fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

export const executionApi = {
  get: (id: string) => fetch(`${API_URL}/api/projects/${id}/execution`).then(json<Execution>),
  start: (id: string, body: { budget_usd?: number; model_policy?: ModelPolicy }) =>
    post(`${API_URL}/api/projects/${id}/execution/start`, body).then(json<Run>),
  pause: (id: string) => post(`${API_URL}/api/projects/${id}/execution/pause`).then(json<unknown>),
  resume: (id: string, body: { budget_usd?: number } = {}) =>
    post(`${API_URL}/api/projects/${id}/execution/resume`, body).then(json<unknown>),
  cancel: (id: string) => post(`${API_URL}/api/projects/${id}/execution/cancel`).then(json<unknown>),
  task: (id: string, taskId: string, action: "complete" | "skip", note?: string) =>
    post(`${API_URL}/api/projects/${id}/execution/tasks/${taskId}/${action}`, { note }).then(json<TaskState>),
  files: (id: string) =>
    fetch(`${API_URL}/api/projects/${id}/workspace/files`).then(json<{ path: string; size: number }[]>),
  fileUrl: (id: string, path: string) =>
    `${API_URL}/api/projects/${id}/workspace/file?path=${encodeURIComponent(path)}`,
};
