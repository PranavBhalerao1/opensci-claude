import type {
  Gap,
  LitPaper,
  MasterPlan,
  Message,
  Overview,
  ReportRun,
  ResearchBrief,
  ResearchPlan,
  ReviewIteration,
} from "@/lib/api";

export type QuestionsPayload = Extract<Message, { kind: "questions" }>["payload"];
export type AutoAnswer = { question_id: string; selected: string[]; other: string | null; rationale: string };
export type ReviewIssue = {
  id: string;
  track_id: string;
  severity: "FATAL" | "MAJOR" | "MINOR";
  category: string;
  title: string;
  blocking: boolean;
  open_concern: boolean;
  verification: string;
  grounding: string;
  tracking: { status: "new"; previous_ids: string[] };
  referee: string;
};
export type ToolLine = { tool: string; args: string; sub?: string };

export interface PaperDocument {
  title: string;
  authors: string;
  affiliation: string;
  abstract: string;
  sections: {
    heading: string;
    paragraphs: string[];
    table?: { caption: string; head: string[]; rows: string[][] };
    figure?: { caption: string; kind: "scatter" | "bars" | "lines" | "heat" };
  }[];
  references: string[];
}

/** One pre-made research run, replayed stage by stage in the real interface. */
export interface ReplayData {
  slug: string;
  question: string;
  /** Sidebar title before the brief arrives. */
  shortTitle: string;
  brief: ResearchBrief;
  questions: QuestionsPayload;
  answers: AutoAnswer[];
  papers: LitPaper[];
  lit: { queries: number; found: number; screened: number; included: number; citations: number; links: number };
  overview: Overview;
  gaps: Gap[];
  plan: ResearchPlan;
  planAudit: unknown;
  planLog: string[];
  master: MasterPlan;
  bpLog: string[];
  taskCost: Record<string, number>;
  toolScript: Record<string, ToolLine[]>;
  budget: number;
  report: NonNullable<ReportRun["result"]>;
  iterations: ReviewIteration[];
  round1Issues: ReviewIssue[];
  reviewLog: { round1: string[]; repair: string[]; round2: string[]; round3: string[] };
  /** Total spend after each stage, in USD. */
  spend: { literature: number; gaps: number; plan: number; blueprint: number; execution: number; report: number; review: number };
  paper: PaperDocument | "heatwave";
}
