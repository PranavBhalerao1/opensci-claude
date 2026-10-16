import { createClient } from "./supabase/client";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Stage =
  | "clarify" | "literature" | "gaps" | "plan" | "done" | "blueprint" | "ready" | "executing" | "executed"
  | "reporting" | "reviewing" | "complete";

export type Depth = "quick" | "standard" | "deep";

export interface ProjectSettings {
  depth?: Depth;
  max_papers?: number;
  citation_hops?: number;
  budget?: { llm_usd: number; gpu_hours: number };
  model_policy?: ModelPolicy;
  refinement?: { enabled: boolean; max_rounds?: number; max_usd?: number };
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
  review: ReviewState | null;
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

export const BETA_PENDING_MESSAGE =
  "OpenScientist is currently in private beta. Your account has been created successfully and is awaiting beta approval.";
export const BETA_LIMIT_MESSAGE =
  "You're out of credits. Upgrade your plan on the Pricing page, or wait for your credits to renew.";

/** A refusal from the private-beta gate, identified by the API's machine-readable code.
 * toString() is the plain message, so existing `setError(String(e))` sites show it as-is. */
export class BetaError extends Error {
  code: "beta_pending" | "beta_limit_reached";
  constructor(code: BetaError["code"], message: string) {
    super(message);
    this.code = code;
  }
  toString() {
    return this.message;
  }
}

async function failure(res: Response): Promise<Error> {
  const text = await res.text();
  let code: unknown;
  try {
    code = JSON.parse(text)?.detail?.code;
  } catch {
    // not JSON
  }
  if (code === "beta_limit_reached") return new BetaError(code, BETA_LIMIT_MESSAGE);
  if (code === "beta_pending") return new BetaError(code, BETA_PENDING_MESSAGE);
  return new Error(`${res.status} ${text}`);
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw await failure(res);
  return res.json() as Promise<T>;
}

/** The current Supabase access token, or null if signed out. Cheap: the SDK
 * caches the session in memory/localStorage and only hits the network to
 * refresh an expiring token. */
export async function accessToken(): Promise<string | null> {
  const supabase = createClient();
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

/** fetch() with the current user's bearer token attached, so FastAPI can verify
 * who is calling and never has to trust a user id from the request body. */
async function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const token = await accessToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(url, { ...init, headers });
}

const post = (url: string, body: unknown = {}) =>
  apiFetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

/** The signed-in user's private-beta status (GET /api/me). cap_usd and
 * remaining_usd are null for unlimited accounts. */
export interface Me {
  id: string;
  email: string | null;
  beta_approved: boolean;
  unlimited: boolean;
  cap_usd: number | null;
  spent_usd: number;
  remaining_usd: number | null;
  plan: "light" | "intensive" | "ultra" | null; // paid plan, if any
  period_end: string | null; // when the plan's credits renew
}

export const meApi = {
  get: () => apiFetch(`${API_URL}/api/me`).then(json<Me>),
};

export const api = {
  listProjects: () => apiFetch(`${API_URL}/api/projects`).then(json<Project[]>),
  getProject: (id: string) =>
    apiFetch(`${API_URL}/api/projects/${id}`).then(json<{ project: Project; messages: Message[] }>),
  createProject: (body: { autonomous?: boolean } = {}) =>
    apiFetch(`${API_URL}/api/projects`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }).then(json<Project>),
  deleteProject: (id: string) => apiFetch(`${API_URL}/api/projects/${id}`, { method: "DELETE" }),
  confirmBrief: (id: string, body: { depth: Depth; max_papers: number }) =>
    apiFetch(`${API_URL}/api/projects/${id}/brief/confirm`, {
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
  const res = await apiFetch(`${API_URL}/api/projects/${projectId}/messages`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(turn),
  });
  if (!res.ok || !res.body) throw await failure(res);

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
  get: (id: string) => apiFetch(`${API_URL}/api/projects/${id}/literature`).then(json<Literature>),
  rerun: (id: string) => post(`${API_URL}/api/projects/${id}/literature/run`).then(json<Run>),
  graph: (id: string) =>
    apiFetch(`${API_URL}/api/projects/${id}/graph`).then(json<{ nodes: GraphNode[]; links: GraphLink[] }>),
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
  get: (id: string) =>
    apiFetch(`${API_URL}/api/projects/${id}/gaps`).then(json<{ run: GapsRun | null; project: Project }>),
  rerun: (id: string, feedback?: string) =>
    post(`${API_URL}/api/projects/${id}/gaps/run`, { feedback: feedback ?? null }).then(json<GapsRun>),
  select: (id: string, gapId: string) =>
    post(`${API_URL}/api/projects/${id}/gaps/select`, { gap_id: gapId }).then(json<Project>),
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
    apiFetch(`${API_URL}/api/projects/${id}/plan`).then(json<{ run: PlanRun | null; project: Project; revisions: number }>),
  rerun: (id: string) => post(`${API_URL}/api/projects/${id}/plan/run`).then(json<PlanRun>),
  revise: (id: string, instruction: string) =>
    post(`${API_URL}/api/projects/${id}/plan/revise`, { instruction }).then(json<{ message: Message; run: PlanRun }>),
  edit: async (id: string, plan: unknown) => {
    const res = await apiFetch(`${API_URL}/api/projects/${id}/plan`, {
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
  approve: (id: string) => post(`${API_URL}/api/projects/${id}/plan/approve`).then(json<Project>),
  /** Signed for direct <a>/<img> use, which can't carry an Authorization header. */
  fileUrl: (id: string, name: string, token: string | null) =>
    `${API_URL}/api/projects/${id}/files/${name}${token ? `?token=${encodeURIComponent(token)}` : ""}`,
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
    apiFetch(`${API_URL}/api/projects/${id}/blueprint`).then(json<{ run: BlueprintRun | null; project: Project }>),
  run: (id: string) => post(`${API_URL}/api/projects/${id}/blueprint/run`).then(json<BlueprintRun>),
  revise: (id: string, instruction: string) =>
    post(`${API_URL}/api/projects/${id}/blueprint/revise`, { instruction }).then(
      json<{ message: Message; run: BlueprintRun }>,
    ),
  approve: (id: string) => post(`${API_URL}/api/projects/${id}/blueprint/approve`).then(json<Project>),
};

export const usageApi = {
  get: (id: string) =>
    apiFetch(`${API_URL}/api/projects/${id}/usage`).then(
      json<{
        total: number;
        by_tier: Record<string, number>; // "reasoning" | "standard" | "bulk" | "judge" | "other"
        calls: number;
        gpu: { spent: number; budget: number };
      }>,
    ),
};

// ── Execution ──────────────────────────────────────────────────────────────

export interface AgentEvent {
  type: "tool" | "message";
  sub?: string; // set when a sub-agent produced the event
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

export const executionApi = {
  get: (id: string) => apiFetch(`${API_URL}/api/projects/${id}/execution`).then(json<Execution>),
  start: (id: string, body: { budget_usd?: number; model_policy?: ModelPolicy }) =>
    post(`${API_URL}/api/projects/${id}/execution/start`, body).then(json<Run>),
  pause: (id: string) => post(`${API_URL}/api/projects/${id}/execution/pause`).then(json<unknown>),
  resume: (id: string, body: { budget_usd?: number } = {}) =>
    post(`${API_URL}/api/projects/${id}/execution/resume`, body).then(json<unknown>),
  cancel: (id: string) => post(`${API_URL}/api/projects/${id}/execution/cancel`).then(json<unknown>),
  task: (id: string, taskId: string, action: "complete" | "skip", note?: string) =>
    post(`${API_URL}/api/projects/${id}/execution/tasks/${taskId}/${action}`, { note }).then(json<TaskState>),
  requestChanges: (id: string, taskId: string, feedback: string) =>
    post(`${API_URL}/api/projects/${id}/execution/changes/${taskId}`, { feedback }).then(
      json<{ rerun: string[] }>,
    ),
  provideSecret: (id: string, name: string, value: string) =>
    post(`${API_URL}/api/projects/${id}/secrets`, { name, value }).then(json<{ name: string; requeued_tasks: number }>),
  files: (id: string) =>
    apiFetch(`${API_URL}/api/projects/${id}/workspace/files`).then(json<{ path: string; size: number }[]>),
  /** Signed for direct <a>/<img> use, which can't carry an Authorization header. */
  fileUrl: (id: string, path: string, token: string | null) =>
    `${API_URL}/api/projects/${id}/workspace/file?path=${encodeURIComponent(path)}${
      token ? `&token=${encodeURIComponent(token)}` : ""
    }`,
};

// ── Report ─────────────────────────────────────────────────────────────────

export interface Scaffold {
  title: string;
  one_sentence_summary: string;
  hypothesis_verdict: "supported" | "not_supported" | "inconclusive" | "mixed";
  verdict_explanation: string;
  findings: { claim: string; evidence: string[]; strength: "strong" | "moderate" | "weak"; relation: string }[];
  success_criteria: { criterion: string; status: "met" | "not_met" | "partial" | "unknown"; evidence: string }[];
  figures: { path: string; caption: string; section: string }[];
  limitations: string[];
  deviations: string[];
}

export interface ReportRun extends Omit<Run, "result"> {
  result: {
    scaffold: Scaffold;
    agent: { status: string; summary: string; cost: number; issues: string[] };
    files: { tex: boolean; pdf: boolean; bib: boolean };
    citations: { used: string[]; unknown: string[]; available: number };
    audit: { claim: string; problem: string; severity: "high" | "medium" | "low" }[];
  } | null;
}

export const stageApi = {
  cancel: (id: string, kind: "literature" | "gaps" | "plan" | "blueprint" | "report" | "review" | "repair") =>
    post(`${API_URL}/api/projects/${id}/runs/${kind}/cancel`).then(json<{ cancelled: string }>),
};

// ── Scientific review ──────────────────────────────────────────────────────

export type ReviewStatus =
  | "reviewing" | "repairing" | "attention" | "approved" | "unresolved" | "budget_exhausted" | "review_failed"
  | "stopped";

export interface ReviewIssueSummary {
  id: string;
  track_id: string | null;
  severity: "FATAL" | "MAJOR" | "MINOR";
  category: string;
  title: string;
  blocking: boolean;
  open_concern: boolean;
  verification: string;
  grounding: string;
  tracking: { status: "new" | "persisting" | "resurfaced" | "regression"; previous_ids: string[] } | null;
}

export interface ReviewIteration {
  n: number;
  session: number;
  review_run_id: string;
  verdict: "accept" | "minor_revision" | "major_revision" | "reject" | null;
  judged: boolean;
  decision: "approved" | "repair" | "repair_gates" | "unresolved" | "budget_exhausted" | "review_failed";
  reason: string;
  blocking: { FATAL: number; MAJOR: number };
  open_concerns: number;
  issues: ReviewIssueSummary[];
  cost_usd: number;
  level?: "report" | "execution" | "blueprint" | "plan";
  rerun_tasks?: string[];
  carried_over?: string[];
  skipped_unselected?: string[];
  objective_changes?: string[];
}

export interface ReviewTrack {
  title: string;
  category: string;
  severity: string;
  status: "open" | "concern" | "resolved" | "disclosed" | "refuted";
  seen: number[];
  needs_human?: boolean;
}

export interface ReviewState {
  status?: ReviewStatus;
  step?: "review" | "repair" | "execute" | "report" | null;
  stale?: boolean;
  iteration?: number;
  session_first_iteration?: number;
  max_rounds?: number;
  max_usd?: number;
  attention?: string | null;
  iterations?: ReviewIteration[];
  tracks?: Record<string, ReviewTrack>;
  outcome?: {
    status: ReviewStatus;
    reason: string;
    unresolved: { track: string; title: string; severity: string }[];
    open_concerns: { track: string; title: string }[];
    needs_human: { track: string; title: string }[];
  } | null;
}

export interface ReviewView extends ReviewState {
  spent_usd: number;
  live: Record<"review" | "repair" | "execute" | "report", boolean>;
}

export const reviewApi = {
  get: (id: string) =>
    apiFetch(`${API_URL}/api/projects/${id}/review`).then(
      json<{ review: ReviewView; run: Run | null; project: Project; enabled: boolean }>,
    ),
  start: (id: string) => post(`${API_URL}/api/projects/${id}/review/start`).then(json<{ review: ReviewView }>),
  resume: (id: string) => post(`${API_URL}/api/projects/${id}/review/resume`).then(json<{ review: ReviewView }>),
  stop: (id: string) => post(`${API_URL}/api/projects/${id}/review/stop`).then(json<{ review: ReviewView }>),
  /** Signed for direct <a> use, which can't carry an Authorization header. */
  fileUrl: (id: string, name: string, token: string | null, iteration?: number) =>
    `${API_URL}/api/projects/${id}/review/file?name=${encodeURIComponent(name)}${
      iteration !== undefined ? `&iteration=${iteration}` : ""
    }${token ? `&token=${encodeURIComponent(token)}` : ""}`,
};

/** The paper's scientific-review standing, for badges. */
export function reviewBadge(project: Project): { label: string; tone: "ok" | "warn" | "busy" | "none" } {
  const r = project.review;
  if (!r?.status) return { label: "Unreviewed", tone: "none" };
  if (r.stale) return { label: "Changed since review", tone: "warn" };
  switch (r.status) {
    case "approved":
      return { label: "Reviewed ✓", tone: "ok" };
    case "reviewing":
      return { label: "Under review", tone: "busy" };
    case "repairing":
      return { label: `Repairing · round ${r.iteration ?? 1}`, tone: "busy" };
    case "attention":
      return { label: "Review needs attention", tone: "warn" };
    case "review_failed":
      return { label: "Review failed", tone: "warn" };
    case "budget_exhausted":
      return { label: "Unresolved · budget used", tone: "warn" };
    case "stopped":
      return { label: "Review stopped", tone: "warn" };
    default:
      return { label: "Unresolved issues", tone: "warn" };
  }
}

export const reportApi = {
  get: (id: string) => apiFetch(`${API_URL}/api/projects/${id}/report`).then(json<{ run: ReportRun | null; project: Project }>),
  run: (id: string) => post(`${API_URL}/api/projects/${id}/report/run`).then(json<ReportRun>),
  /** Signed for direct <a>/<iframe> use, which can't carry an Authorization header. */
  packageUrl: (id: string, token: string | null) =>
    `${API_URL}/api/projects/${id}/package${token ? `?token=${encodeURIComponent(token)}` : ""}`,
};
