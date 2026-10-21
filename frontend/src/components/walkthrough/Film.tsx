"use client";

import "./film.css";

import { Fragment, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import BlueprintRun from "@/components/BlueprintRun";
import BriefCard from "@/components/BriefCard";
import { CreditsPanel } from "@/components/Credits";
import ExecutionRun from "@/components/ExecutionRun";
import GapsRun from "@/components/GapsRun";
import LiteratureRun from "@/components/LiteratureRun";
import PlanRun from "@/components/PlanRun";
import QuestionCards from "@/components/QuestionCards";
import ReviewRun from "@/components/ReviewRun";
import StageBar from "@/components/StageBar";
import type {
  BlueprintRun as BlueprintRunT,
  Execution,
  GapsRun as GapsRunT,
  Literature,
  Me,
  Message,
  PlanRun as PlanRunT,
  Project,
  ReportRun as ReportRunT,
  ReviewLogLine,
  ReviewView,
} from "@/lib/api";
import * as D from "./data";
import Notebook from "./Notebook";
import ReportRun from "./ReportRun";
import {
  Callout,
  Caption,
  Chapter,
  Cursor,
  EXEC_END,
  EXEC_SCHEDULE,
  ExpertCheck,
  Intro,
  MissionControl,
  NoveltyCheck,
  Outro,
  BuildTools,
  PaperWriter,
  SourceFinder,
} from "./overlays";

// ── Director: a cancellable, speed-scaled script runner ─────────────────────

class Cancelled extends Error {}

interface Director {
  speed: number;
  instant: boolean;
  wait: (ms: number) => Promise<void>;
  cancelled: () => boolean;
}

function director(speed: number): Director & { cancel: () => void } {
  let dead = false;
  const d = {
    speed,
    instant: false,
    cancelled: () => dead,
    cancel: () => void (dead = true),
    wait: (ms: number) =>
      new Promise<void>((resolve, reject) => {
        if (dead) return reject(new Cancelled());
        if (d.instant) return resolve();
        setTimeout(() => (dead ? reject(new Cancelled()) : resolve()), ms / speed);
      }),
  };
  return d;
}

type Overlay =
  | { kind: "intro" }
  | { kind: "chapter"; n: number; title: string; subtitle: string }
  | { kind: "sources" }
  | { kind: "novelty" }
  | { kind: "expert" }
  | { kind: "tools" }
  | { kind: "mission" }
  | { kind: "paper" }
  | { kind: "outro" };

const CHAPTERS = 8;
/** The execution scene plays a little faster than real time. */
const MISSION = 1.1;
/** Other scenes that play slightly faster than authored, to keep the film under three minutes. */
const SRC = 1.15;
const TOOLS = 1.1;
const PAPER = 1.12;

const fakeMe = (spent: number): Me => ({
  id: "demo",
  email: "researcher@university.edu",
  beta_approved: true,
  unlimited: false,
  cap_usd: 500,
  spent_usd: spent,
  remaining_usd: 500 - 61.2 - spent,
  plan: "ultra",
  period_end: new Date(Date.now() + 18 * 864e5).toISOString(),
});

export default function Film({
  from: fromProp = 0,
  speed: speedProp = 1.4,
  onChapter,
  onDone,
  hideCursor = true,
}: {
  /** Chapter to start at (earlier chapters are fast-forwarded). */
  from?: number;
  speed?: number;
  onChapter?: (n: number) => void;
  onDone?: () => void;
  /** Hide the real mouse pointer (for screen recordings). */
  hideCursor?: boolean;
} = {}) {
  const [project, setProject] = useState<Project>(D.baseProject);
  const [empty, setEmpty] = useState(true);
  const [autonomous, setAutonomous] = useState(false);
  const [composer, setComposer] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [answers, setAnswers] = useState<typeof D.AUTO_ANSWERS | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [lit, setLit] = useState<Literature | null>(null);
  const [gaps, setGaps] = useState<GapsRunT | null>(null);
  const [plan, setPlan] = useState<PlanRunT | null>(null);
  const [bp, setBp] = useState<BlueprintRunT | null>(null);
  const [exec, setExec] = useState<Execution | null>(null);
  const [report, setReport] = useState<ReportRunT | null>(null);
  const [review, setReview] = useState<{ view: ReviewView; log: ReviewLogLine[] } | null>(null);
  const [spent, setSpent] = useState(0);

  const [overlay, setOverlay] = useState<Overlay | null>(null);
  const [leaving, setLeaving] = useState(false);
  const [caption, setCaption] = useState<{ kicker: string; text: string } | null>(null);
  const [callout, setCallout] = useState<{ target: string; text: string; side?: "right" | "left" | "top" | "bottom"; dim?: boolean } | null>(null);
  const [cursor, setCursor] = useState({ x: 900, y: 700, visible: false, clicking: 0 });
  const [cam, setCam] = useState({ s: 1, x: 0, y: 0 });
  // ?speed= and ?from= override the props (handy for recording).
  const [speed] = useState(() =>
    typeof window === "undefined" ? speedProp : Number(new URLSearchParams(window.location.search).get("speed") || speedProp),
  );

  const thread = useRef<HTMLDivElement>(null);
  const camRef = useRef(cam);
  useEffect(() => {
    camRef.current = cam;
  });

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const from = Number(q.get("from") || fromProp);
    const d = director(speed);
    // eslint-disable-next-line react-hooks/immutability -- the script is declared below and only starts after mount
    void run(d, from).catch((e) => {
      if (!(e instanceof Cancelled)) console.error(e);
    });
    return () => d.cancel();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── camera & scrolling helpers ──────────────────────────────────────────

  const el = (sel: string) => document.querySelector(sel) as HTMLElement | null;

  const scrollTo = async (d: Director, sel: string, offset = 40, ms = 900) => {
    const box = thread.current;
    const target = el(sel);
    if (!box || !target) return;
    const to = Math.max(0, Math.min(box.scrollHeight - box.clientHeight, target.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop - offset));
    await animateScroll(d, box, to, ms);
  };

  const scrollBy = async (d: Director, dy: number, ms: number) => {
    const box = thread.current;
    if (!box) return;
    await animateScroll(d, box, Math.max(0, Math.min(box.scrollHeight - box.clientHeight, box.scrollTop + dy)), ms);
  };

  const zoomTo = (sel: string, maxScale = 1.6, pad = 60) => {
    const target = el(sel);
    if (!target) return;
    const r = target.getBoundingClientRect();
    const c = camRef.current;
    // Undo the current camera to get untransformed coordinates.
    const left = (r.left - c.x) / c.s;
    const top = (r.top - c.y) / c.s;
    const w = r.width / c.s;
    const h = r.height / c.s;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const s = Math.min(maxScale, (vw - pad * 2) / w, (vh - pad * 2) / h);
    setCam({ s, x: vw / 2 - s * (left + w / 2), y: vh / 2 - s * (top + h / 2) });
  };
  const zoomReset = () => setCam({ s: 1, x: 0, y: 0 });

  const moveCursor = async (d: Director, sel: string, ms = 950) => {
    const target = el(sel);
    if (!target) return;
    const r = target.getBoundingClientRect();
    setCursor((c) => ({ ...c, visible: true, x: r.left + r.width * 0.55, y: r.top + r.height * 0.55 }));
    await d.wait(ms);
  };
  const click = async (d: Director) => {
    setCursor((c) => ({ ...c, clicking: c.clicking + 1 }));
    await d.wait(260);
  };

  const show = async (d: Director, o: Overlay, ms: number) => {
    setLeaving(false);
    setOverlay(o);
    await d.wait(ms);
  };
  const hide = async (d: Director) => {
    setLeaving(true);
    await d.wait(450);
    setOverlay(null);
    setLeaving(false);
  };
  const chapter = async (d: Director, n: number, title: string, subtitle: string, during?: () => void) => {
    setCallout(null);
    setCaption(null);
    zoomReset();
    onChapter?.(n);
    await show(d, { kind: "chapter", n, title, subtitle }, 300);
    during?.();
    await d.wait(1350);
  };

  // ── the script ──────────────────────────────────────────────────────────

  async function run(d: ReturnType<typeof director>, from: number) {
    const skipping = (n: number) => (d.instant = n < from);
    const W = d.wait;
    let p = D.baseProject();
    const setP = (patch: Partial<Project>) => {
      p = { ...p, ...patch, updated_at: D.now() };
      setProject(p);
    };

    await W(500);

    // Intro
    skipping(1);
    await show(d, { kind: "intro" }, 2900);

    // 01 · Question & clarification
    await chapter(d, 1, "Ask a question", "In plain words. No PhD required.");
    await hide(d);
    setCaption({ kicker: "01 · Question", text: "Start with a question that matters — in plain words." });
    setCursor((c) => ({ ...c, visible: true, x: window.innerWidth * 0.62, y: window.innerHeight * 0.78 }));
    await W(600);
    await moveCursor(d, "#mode-auto");
    await click(d);
    setAutonomous(true);
    setCallout({ target: "#mode-toggle", text: "Autonomous mode: OpenScientist makes every decision itself, from question to reviewed paper.", side: "right" });
    await W(2100);
    setCallout(null);
    await moveCursor(d, "#composer", 800);
    await click(d);
    for (let i = 1; i <= D.QUESTION.length; i += 2) {
      setComposer(D.QUESTION.slice(0, i));
      await W(26);
    }
    setComposer(D.QUESTION);
    await W(450);
    await moveCursor(d, "#send", 700);
    await click(d);
    setCursor((c) => ({ ...c, visible: false }));

    setEmpty(false);
    setComposer("");
    setP({ title: "AI weather models vs. record heat" });
    setMessages([D.USER_MSG]);
    setStatus("Reading your question");
    setCaption({ kicker: "01 · Clarify", text: "First, it asks what a good advisor would ask." });
    await W(1200);
    setStatus("Drafting clarifying questions");
    await W(1100);
    setStatus(null);
    setMessages([D.USER_MSG, D.QUESTIONS_MSG]);
    await W(200);
    await scrollTo(d, "#card-questions", 30, 700);
    await W(900);
    for (let k = 1; k <= 3; k++) {
      setAnswers(D.AUTO_ANSWERS.slice(0, k));
      if (k === 1) setCallout({ target: "#card-questions p.font-mono", text: "No one to ask? A proxy answers for you — and writes down why.", side: "right" });
      await W(950);
      await scrollBy(d, k === 3 ? 260 : 220, 500);
    }
    setCallout(null);
    setStatus("Writing the research brief");
    await W(1100);
    setStatus(null);
    setMessages([D.USER_MSG, D.QUESTIONS_MSG, D.BRIEF_MSG]);
    setP({ brief: D.BRIEF, title: D.BRIEF.title });
    await W(150);
    await scrollTo(d, "#card-brief", 20, 700);
    setCaption({ kicker: "01 · Brief", text: "Your question becomes a precise, testable research brief." });
    await W(500);
    setP({ stage: "literature" });
    setCallout({ target: "#card-brief blockquote", text: "One sharp, testable question — with scope, data and assumptions spelled out.", side: "right" });
    await W(2300);
    setCallout(null);
    await scrollBy(d, 520, 1200);
    await W(300);

    // 02 · Literature
    skipping(2);
    await chapter(d, 2, "Literature review", "It finds its own sources.", () => {
      setLit({ run: D.litRun({ phase: "searching", counts: { queries_done: 1, queries_total: 8, found: 40 } }), papers: [] });
    });
    setCaption({ kicker: "02 · Literature", text: "It writes its own search queries and pulls papers from Semantic Scholar and OpenAlex." });
    await show(d, { kind: "sources" }, 0);
    await W(4300 / SRC);
    setCaption({ kicker: "02 · Literature", text: "Every hit is screened for relevance. Off-topic papers are dropped." });
    await W(4400 / SRC);
    setCaption({ kicker: "02 · Literature", text: "Then it reads each paper and extracts structured notes: methods, data, findings, limits." });
    await W(5000 / SRC);
    setCaption({ kicker: "02 · Literature", text: "It follows citations, and links everything into a knowledge graph." });
    await W(3600 / SRC);
    const t = (s: number) => new Date(Date.now() - s * 1000).toISOString();
    setLit({
      run: D.litRun({
        phase: "synthesising",
        counts: { queries_done: 8, queries_total: 8, found: 2106, candidates: 486, screened: 486, included: 118, extracted: 118 },
        log: [
          { t: t(9), text: "Followed 302 citations → 44 new candidates" },
          { t: t(6), text: "Extracted notes for 118/118 papers" },
          { t: t(3), text: "Linked 1,862 citations between papers" },
          { t: t(1), text: "Synthesising themes and open problems" },
        ],
      }),
      papers: D.PAPERS,
    });
    await hide(d);
    setCaption(null);
    await scrollTo(d, "#card-lit", 30, 600);
    await W(900);
    setLit({
      run: D.litRun({
        status: "done",
        phase: "done",
        counts: { queries_done: 8, queries_total: 8, found: 2106, candidates: 486, screened: 486, included: 118, extracted: 118 },
        result: { overview: D.OVERVIEW },
      }),
      papers: [...D.PAPERS, ...Array.from({ length: 100 }, (_, i) => ({ ...D.PAPERS[i % D.PAPERS.length], id: `x${i}` }))],
    });
    setP({ stage: "gaps" });
    setSpent(1.12);
    await W(300);
    await scrollTo(d, "#card-lit h3", 30, 900);
    setCaption({ kicker: "02 · Literature", text: "118 papers distilled into the state of the field." });
    await W(1400);
    await scrollTo(d, "#card-lit ul", 120, 900);
    setCallout({ target: "#card-lit ul", text: "Open problems — this is where research gaps hide.", side: "top", dim: true });
    await W(2300);

    // 03 · Gaps
    skipping(3);
    await chapter(d, 3, "Research gaps", "It finds what nobody has done yet.", () => {
      setGaps(D.gapsRun({ phase: "proposing", started_at: t(74), log: [{ t: t(2), text: "Reasoning over 118 papers’ notes" }] }));
    });
    await hide(d);
    await scrollTo(d, "#card-gaps", 30, 600);
    setCaption({ kicker: "03 · Gaps", text: "A reasoning model reads all 118 papers’ notes and proposes candidate gaps." });
    await W(1900);
    setGaps(D.gapsRun({ phase: "checking", started_at: t(141), counts: { proposed: 5, checked: 1 } as never, log: [{ t: t(1), text: "Novelty check · gap 1" }] }));
    await W(700);
    setCaption({ kicker: "03 · Gaps", text: "Each gap is searched against prior work, so it never “discovers” something already published." });
    await show(d, { kind: "novelty" }, 6600);
    const gapsDone = D.gapsRun({
      status: "done",
      phase: "done",
      result: { gaps: D.GAPS, recommended: "g1", feedback: null },
    });
    setGaps(gapsDone);
    setP({ chosen_gap: { ...D.GAPS[0], run_id: gapsDone.id }, stage: "plan" });
    setPlan(D.planRun({ phase: "drafting" }));
    setSpent(3.4);
    await hide(d);
    await scrollTo(d, "#card-gaps", 30, 700);
    setCaption({ kicker: "03 · Gaps", text: "Ranked on novelty, feasibility, impact and testability. The best one is chosen." });
    setCallout({ target: "#card-gaps article", text: "Novel and high-impact: heat warnings increasingly rely on AI forecasts.", side: "right" });
    await W(2500);
    setCallout(null);
    await scrollBy(d, 600, 1200);

    // 04 · Plan
    skipping(4);
    await chapter(d, 4, "Research plan", "An expert checks the science first.");
    await hide(d);
    await scrollTo(d, "#card-plan", 30, 600);
    setCaption({ kicker: "04 · Plan", text: "It drafts a full research plan: hypotheses, data, methods, baselines, metrics." });
    await W(1800);
    setCaption({ kicker: "04 · Plan", text: "Before any compute is spent, a domain-expert model audits the design." });
    await show(d, { kind: "expert" }, 7300);
    const planDone = D.planRun({ status: "done", phase: "done", result: { plan: D.PLAN, gap_id: "g1", gaps_run_id: gapsDone.id, audit: D.PLAN_AUDIT } });
    setPlan(planDone);
    setP({ plan: { ...D.PLAN, run_id: planDone.id, approved_at: D.now() }, stage: "done" });
    setBp(D.bpRun({ phase: "resolving", log: [{ t: t(1), text: "Locating ARCO-ERA5, WeatherBench 2 and model checkpoints" }] }));
    setSpent(5.1);
    await hide(d);
    await scrollTo(d, "#card-plan", 30, 600);
    setCaption({ kicker: "04 · Plan", text: "The fixed plan: 5 phases, 12 tasks, a causal test and pre-set success thresholds." });
    setCallout({ target: "#card-plan .border-b.border-ink.px-6.py-4", text: "The audit caught training-period leakage in the first draft and fixed it before approval.", side: "right" });
    await W(2800);
    setCallout(null);
    await scrollBy(d, 900, 1400);

    // 05 · Blueprint
    skipping(5);
    await chapter(d, 5, "Blueprint", "It builds its own tools.");
    await hide(d);
    await scrollTo(d, "#card-bp", 30, 600);
    setCaption({ kicker: "05 · Blueprint", text: "The plan is compiled into an agent team with exact tasks, checks and a budget." });
    await W(800);
    setBp(D.bpRun({ phase: "compiling", started_at: t(48), log: [{ t: t(1), text: "Compiling 6 agents · 12 tasks" }] }));
    await W(800);
    setBp(D.bpRun({ phase: "validating", started_at: t(131), log: [{ t: t(1), text: "Validating data flow, tools and budget" }] }));
    await W(900);
    const bpDone = D.bpRun({ status: "done", phase: "done", result: D.BP_RESULT });
    setBp(bpDone);
    setP({ blueprint: { run_id: bpDone.id, approved_at: D.now() }, stage: "ready" });
    setSpent(6.3);
    await W(200);
    await scrollTo(d, "#card-bp h2", 30, 700);
    await W(200);
    zoomTo("#card-bp dl", 1.5, 90);
    setCallout({ target: "#card-bp dl", text: "6 agents · 12 tasks · cost and compute estimated up front.", side: "bottom" });
    await W(2300);
    setCallout(null);
    zoomReset();
    await W(600);
    setCaption({ kicker: "05 · Infrastructure", text: "Compute is handled for you on OpenScientist Cloud — no servers, no setup." });
    await show(d, { kind: "tools" }, 4300 / TOOLS);
    setCaption({ kicker: "05 · Infrastructure", text: "It writes, tests and registers its own MCP servers — tools its agents will use." });
    await W(5000 / TOOLS);
    setCaption({ kicker: "05 · Infrastructure", text: "Every data source and model checkpoint is located and verified before execution." });
    await W(4000 / TOOLS);
    setSpent(7.2);

    // 06 · Execution
    skipping(6);
    const tasksAt = (ms: number) =>
      D.MASTER.tasks.map((tk) => {
        const s = EXEC_SCHEDULE[tk.id];
        const st = ms >= s.end ? "done" : ms >= s.start ? "running" : "pending";
        return D.taskState(tk.id, tk.agent, {
          status: st,
          attempts: s.fail && ms > s.fail ? 2 : st === "pending" ? 0 : 1,
          cost: st === "done" ? D.TASK_COST[tk.id] : 0,
          started_at: st !== "pending" ? new Date(Date.now() - 64000e3).toISOString() : null,
          finished_at: st === "done" ? new Date(Date.now() - 64000e3 + (s.end - s.start) * 2300).toISOString() : null,
          summary: st === "done" ? (D.TOOL_SCRIPT[tk.id]?.at(-1)?.args ?? null) : null,
          checks: st === "done" ? [{ check: "Declared outputs exist", passed: true, reason: "verified by the platform" }] : [],
          events: (D.TOOL_SCRIPT[tk.id] ?? []).map((e, i) => ({ type: "tool" as const, step: i + 1, tool: e.tool, args: e.args, sub: e.sub, cost: 0.01, t: D.now() })),
        });
      });
    await chapter(d, 6, "Execution", "The agents run the experiment — and improve.", () => {
      setExec({
        run: D.litRun({ id: "ex1", kind: "execution", phase: "running" }),
        project: p,
        tasks: tasksAt(0),
        spent: 0,
        budget: 100,
        model_policy: "default",
        paused: null,
        live: true,
      });
      setP({ stage: "executing" });
    });
    setCaption({ kicker: "06 · Execution", text: "Agents pull ERA5 through their own MCP server and catalogue every record heatwave since 2018." });
    await show(d, { kind: "mission" }, 0);
    await W(7600 / MISSION);
    setCaption({ kicker: "06 · Execution", text: "Four sub-agents re-run 2,350 forecasts in the cloud — while another retrains a counterfactual model." });
    await W(3000 / MISSION);
    setCaption({ kicker: "06 · Execution", text: "Out of memory? It writes itself a new skill, saves it, and every agent reuses it." });
    await W(6300 / MISSION);
    setCaption({ kicker: "06 · Execution", text: "A verifier catches a grid mismatch. The fix becomes another reusable skill." });
    await W(3600 / MISSION);
    setCaption({ kicker: "06 · Execution", text: "The result appears live: AI error grows with how far heat beats the record. Then it fine-tunes a fix." });
    await W((EXEC_END - 20500 + 1300) / MISSION);
    setExec({
      run: D.litRun({ id: "ex1", kind: "execution", status: "done", phase: "done", result: { counts: { done: 12 } } as never }),
      project: p,
      tasks: tasksAt(1e9),
      spent: 72.4,
      budget: 100,
      model_policy: "default",
      paused: null,
      live: false,
    });
    setP({ stage: "executed" });
    setSpent(79.6);
    setReport(D.reportRun({ phase: "consolidating" }));
    await hide(d);
    setCaption(null);
    await scrollTo(d, "#card-exec", 30, 700);
    setCallout({ target: "#card-exec", text: "12 / 12 tasks verified, for $72.40 of a $100 budget.", side: "left" });
    await W(2100);
    setCallout(null);

    // 07 · Report
    skipping(7);
    await chapter(d, 7, "The paper", "Written, compiled and cited.");
    setP({ stage: "reporting" });
    setCaption({ kicker: "07 · Report", text: "Findings with evidence become a NeurIPS-format LaTeX paper, compiled to PDF." });
    await show(d, { kind: "paper" }, 8000 / PAPER);
    setCaption({ kicker: "07 · Report", text: "References are generated from the literature review — it cannot invent a citation." });
    await W(3000 / PAPER);
    setReport(D.reportRun({ status: "done", phase: "done", result: D.REPORT_RESULT }));
    const reviewStart: ReviewView = {
      status: "reviewing",
      step: "review",
      iteration: 1,
      session_first_iteration: 1,
      max_rounds: 5,
      max_usd: 10,
      target_score: 9,
      iterations: [],
      spent_usd: 0,
      live: { review: true, repair: false, execute: false, report: false },
    };
    setP({ stage: "reviewing", review: { status: "reviewing", iteration: 1 } });
    setReview({ view: reviewStart, log: [{ t: D.now(), text: "Reviewer panel assembled: lead, methods, theory", kind: "review" }] });
    await hide(d);
    setCaption(null);
    await scrollTo(d, "#card-report", 30, 700);
    setCallout({ target: "#card-report .border.border-ink.px-4.py-3", text: "Hypothesis supported, with a causal test — and every finding points to its evidence.", side: "right" });
    await W(2100);
    setCallout(null);
    await scrollTo(d, "#card-report ol", 60, 900);
    await W(700);

    // 08 · Review
    skipping(8);
    await chapter(d, 8, "Scientific review", "Then it reviews itself.");
    await hide(d);
    await scrollTo(d, "#card-review", 30, 600);
    setCaption({ kicker: "08 · Review", text: "A fresh reviewer panel that has never seen the paper checks it against the data, code and figures." });
    const log: ReviewLogLine[] = [
      { t: D.now(), text: "Reviewer panel assembled: lead, methods, theory", kind: "review" },
      { t: D.now(), text: "Recomputed Table 1 from results/metrics.csv", kind: "review" },
      { t: D.now(), text: "Pangu peak bias: table −3.0 K, data −2.8 K — mismatch", kind: "review" },
    ];
    setReview({ view: reviewStart, log });
    await W(1500);
    const it1 = { ...D.ITERATIONS[0], issues: D.ROUND1_ISSUES };
    const repairing: ReviewView = {
      ...reviewStart,
      status: "repairing",
      step: "execute",
      iterations: [it1],
      spent_usd: 1.1,
      live: { review: false, repair: false, execute: true, report: false },
    };
    const log2 = [
      ...log,
      { t: D.now(), text: "Round 1 · score 6.1 · 2 major issues", kind: "review" as const },
      { t: D.now(), text: "Re-evaluating T10, T11 on held-out heatwave clusters; reusing 10 finished tasks", kind: "repair" as const },
    ];
    setP({ review: { status: "repairing", iteration: 1 } });
    setReview({ view: repairing, log: log2 });
    await W(300);
    zoomTo("#card-review section > div:nth-child(2)", 1.3, 30);
    setCallout({ target: "#card-review ol", text: "It found two real problems in its own paper — and re-runs only the affected experiments.", side: "right" });
    await W(3200);
    setCallout(null);
    zoomReset();
    setReview({ view: { ...repairing, step: "report", live: { review: false, repair: false, execute: false, report: true } }, log: [...log2, { t: D.now(), text: "Fix holds on held-out clusters (−42%). Rewriting §3 and Table 1", kind: "repair" }] });
    await W(1300);
    const it2 = { ...D.ITERATIONS[1], issues: [D.ROUND1_ISSUES[2]] };
    setReview({
      view: { ...repairing, status: "reviewing", step: "review", iteration: 2, iterations: [it1, it2], spent_usd: 2.3, live: { review: true, repair: false, execute: false, report: false } },
      log: [...log2, { t: D.now(), text: "Round 2 · score 8.2 · adding ERA5 caveat", kind: "review" }],
    });
    await W(1500);
    const approved: ReviewView = {
      ...repairing,
      status: "approved",
      step: null,
      iteration: 3,
      iterations: [it1, it2, { ...D.ITERATIONS[2], issues: [] }],
      spent_usd: 3.1,
      live: { review: false, repair: false, execute: false, report: false },
      outcome: { status: "approved", reason: "Score 9.2 / 10 meets the target. No blocking issues remain.", unresolved: [], open_concerns: [], needs_human: [] },
    };
    setP({ stage: "complete", review: { status: "approved", iteration: 3 } });
    setReview({ view: approved, log: [...log2, { t: D.now(), text: "Round 3 · score 9.2 · accept", kind: "review" }] });
    setSpent(84.62);
    setCaption({ kicker: "08 · Review", text: "6.1 → 8.2 → 9.2. Approved — a finished, reviewed paper." });
    await W(200);
    await scrollTo(d, "#card-review", 30, 400);
    zoomTo("#card-review .mb-5", 1.7, 80);
    await W(3000);
    zoomReset();
    setCaption(null);
    await W(500);

    // Outro
    d.instant = false;
    onChapter?.(9);
    await show(d, { kind: "outro" }, 0);
    await W(9000);
    onDone?.();
  }

  // ── render ──────────────────────────────────────────────────────────────

  const runningStage = (
    [
      ["literature", lit?.run?.status],
      ["gaps", gaps?.status],
      ["plan", plan?.status],
      ["blueprint", bp?.status],
      ["report", report?.status],
      ["review", review?.view.live.review ? "running" : undefined],
    ] as const
  ).find(([, s]) => s === "running")?.[0];

  const answered: Extract<Message, { kind: "answers" }> | undefined = answers
    ? {
        id: "m3",
        project_id: D.PID,
        role: "user",
        content: "",
        created_at: D.now(),
        kind: "answers",
        payload: { question_message_id: "m2", answers, auto: true },
      }
    : undefined;

  const noop = async () => {};
  const projects = [{ id: D.PID, title: empty ? "New investigation" : project.title, stage: project.stage }, ...D.OLD_PROJECTS];

  const stageCards = (
    <>
      {lit && (
        <div id="card-lit" className="film-new">
          <LiteratureRun project={project} lit={lit} onRetry={noop} onOpenLibrary={() => {}} />
        </div>
      )}
      {gaps && (
        <div id="card-gaps" className="film-new">
          <GapsRun project={project} run={gaps} papers={lit?.papers ?? []} onSelect={noop} onRegenerate={noop} onOpenPaper={() => {}} />
        </div>
      )}
      {plan && (
        <div id="card-plan" className="film-new">
          <PlanRun project={project} run={plan} revisions={0} onApprove={noop} onRetry={noop} onSaved={() => {}} />
        </div>
      )}
      {bp && (
        <div id="card-bp" className="film-new">
          <BlueprintRun project={project} run={bp} onStart={noop} onApprove={noop} />
        </div>
      )}
      {exec && (
        <div id="card-exec" className="film-new">
          <ExecutionRun
            project={project}
            exec={exec}
            mp={D.MASTER}
            onStart={noop}
            onPause={noop}
            onResume={noop}
            onCancel={noop}
            onTask={noop}
            onSecret={noop}
            onRequestChanges={noop}
            onOpenFiles={() => {}}
          />
        </div>
      )}
      {report && (
        <div id="card-report" className="film-new">
          <ReportRun project={project} run={report} onStart={noop} onOpenFiles={() => {}} />
        </div>
      )}
      {review && (
        <div id="card-review" className="film-new">
          <ReviewRun project={project} review={review.view} enabled run={null} log={review.log} onAction={noop} />
        </div>
      )}
    </>
  );

  return (
    <div className={`film fixed inset-0 overflow-hidden bg-paper ${hideCursor ? "film-nocursor" : ""}`}>
      <div
        className="flex h-full origin-top-left transition-transform duration-[1100ms] ease-[cubic-bezier(.6,0,.2,1)]"
        style={{ transform: `translate(${cam.x}px, ${cam.y}px) scale(${cam.s})` }}
      >
        <DemoSidebar projects={projects} me={fakeMe(spent)} />

        <main className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-14 shrink-0 items-center justify-between border-b border-rule px-6">
            <StageBar stage={project.stage} />
            <span className="flex shrink-0 items-center gap-3 pl-4 font-mono text-[11px] uppercase tracking-[0.12em] text-faint">
              {runningStage && <span className="border border-ink px-2 py-0.5 text-ink">■ Stop {runningStage}</span>}
            </span>
          </header>

          {empty ? (
            <EmptyState autonomous={autonomous} text={composer} />
          ) : (
            <>
              <div ref={thread} className="flex-1 overflow-y-auto">
                <div className="mx-auto max-w-3xl px-6 py-10">
                  {messages.map((m) => {
                    if (m.kind === "questions")
                      return (
                        <div id="card-questions" key={m.id} className="film-new">
                          <QuestionCards message={m} answered={answered} busy={false} onSubmit={() => {}} />
                        </div>
                      );
                    if (m.kind === "brief")
                      return (
                        <Fragment key={m.id}>
                          <div id="card-brief" className="film-new">
                            <BriefCard message={m} project={project} latest busy={false} onConfirm={noop} />
                          </div>
                          {stageCards}
                        </Fragment>
                      );
                    if (m.kind === "text") return <Bubble key={m.id} role={m.role} content={m.content} />;
                    return null;
                  })}
                  {status && <StatusLine text={status} />}
                  <div className="h-[40vh]" />
                </div>
              </div>
              <div className="mx-auto w-full max-w-3xl px-6 pb-6">
                <Composer text="" placeholder={composerHint(project)} />
              </div>
            </>
          )}
        </main>

        <Notebook
          project={empty ? null : project}
          lit={lit}
          gapsRun={gaps}
          planRun={plan}
          bpRun={bp}
          exec={exec}
          onOpenFiles={() => {}}
          onOpenLibrary={() => {}}
          spent={spent}
        />
      </div>

      {callout && <Callout {...callout} />}
      {caption && <Caption {...caption} />}

      {overlay && (
        <div className={`fixed inset-0 z-[50] ${leaving ? "film-out" : ""}`}>
          {overlay.kind === "intro" && <Intro />}
          {overlay.kind === "chapter" && <Chapter n={overlay.n} total={CHAPTERS} title={overlay.title} subtitle={overlay.subtitle} />}
          {overlay.kind === "sources" && <SourceFinder speed={speed * SRC} />}
          {overlay.kind === "novelty" && <NoveltyCheck speed={speed} />}
          {overlay.kind === "expert" && <ExpertCheck speed={speed} />}
          {overlay.kind === "tools" && <BuildTools speed={speed * TOOLS} />}
          {overlay.kind === "mission" && <MissionControl speed={speed * MISSION} />}
          {overlay.kind === "paper" && <PaperWriter speed={speed * PAPER} />}
          {overlay.kind === "outro" && <Outro speed={speed} />}
        </div>
      )}

      <Cursor {...cursor} />
    </div>
  );
}

async function animateScroll(d: Director, box: HTMLElement, to: number, ms: number) {
  if (d.instant) {
    box.scrollTop = to;
    return;
  }
  const from = box.scrollTop;
  const dur = ms / d.speed;
  const start = performance.now();
  await new Promise<void>((resolve) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      box.scrollTop = to;
      resolve();
    };
    const step = (now: number) => {
      if (done) return;
      const x = Math.min(1, (now - start) / dur);
      const e = x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
      box.scrollTop = from + (to - from) * e;
      if (x < 1 && !d.cancelled()) requestAnimationFrame(step);
      else finish();
    };
    requestAnimationFrame(step);
    // Never let a paused animation frame (hidden tab) stall the script.
    setTimeout(finish, dur + 250);
  });
  if (d.cancelled()) throw new Cancelled();
}

function composerHint(project: Project) {
  if (project.stage === "plan" || project.stage === "done") return "Ask for changes to the plan, e.g. “add an ablation study”…";
  if (project.stage === "blueprint" || project.stage === "ready") return "Ask for changes to the blueprint, e.g. “merge the two data agents”…";
  return "Reply…";
}

// ── Copies of the workspace's private pieces, driven by the script ─────────

function DemoSidebar({ projects, me }: { projects: { id: string; title: string; stage: string }[]; me: Me }) {
  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-rule bg-paper max-md:hidden">
      <div className="px-5 pt-5 pb-4">
        <div className="font-serif text-[22px] leading-none tracking-tight">
          Open<span className="italic">Scientist</span>
        </div>
        <div className="mt-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">Research, for everyone</div>
      </div>
      <div className="px-3">
        <div className="flex w-full items-center justify-between border border-ink px-3 py-2 text-[13px]">
          New investigation <span className="font-mono">+</span>
        </div>
      </div>
      <div className="mt-6 px-5 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">Investigations</div>
      <nav className="mt-2 flex-1 overflow-y-auto px-2 pb-4">
        {projects.map((p, i) => (
          <div key={p.id} className={`flex items-center rounded-sm ${i === 0 ? "bg-wash" : ""}`}>
            <div className="min-w-0 flex-1 px-3 py-2 text-left">
              <div className={`truncate text-[13px] ${i === 0 ? "text-ink" : "text-muted"}`}>{p.title}</div>
              <div className="font-mono text-[10px] uppercase tracking-wider text-faint">
                {p.stage}
                {p.stage === "complete" ? " · Reviewed ✓" : ""}
              </div>
            </div>
          </div>
        ))}
      </nav>
      <CreditsPanel me={me} />
      <div className="flex items-center justify-between gap-2 border-t border-rule px-3 py-3">
        <span className="min-w-0 truncate font-mono text-[11px] text-faint">{me.email}</span>
        <span className="shrink-0 font-mono text-[11px] uppercase tracking-wider text-muted">Sign out</span>
      </div>
    </aside>
  );
}

function EmptyState({ autonomous, text }: { autonomous: boolean; text: string }) {
  const examples = [
    "Can small language models predict protein stability changes from mutations?",
    "Does sleep timing affect how well people remember what they learned that day?",
    "Which material properties best predict battery electrode degradation?",
  ];
  return (
    <div className="flex flex-1 items-center justify-center overflow-y-auto px-6">
      <div className="w-full max-w-2xl py-16">
        <div className="font-mono text-[11px] uppercase tracking-[0.14em] text-faint">New investigation</div>
        <h1 className="mt-3 font-serif text-[44px] leading-[1.05] tracking-tight">
          What do you want to <span className="italic">discover</span>?
        </h1>
        <p className="mt-3 max-w-lg text-[15px] leading-relaxed text-muted">
          Describe a question in plain words. OpenScientist will sharpen it, read the literature, find an open gap and
          draft a research plan with you.
        </p>
        <div className="mt-8">
          <Composer text={text} placeholder="e.g. I wonder whether…" focused={text.length > 0} />
        </div>
        <div className="mt-3 flex items-center justify-between">
          <div id="mode-toggle" className="flex border border-rule font-mono text-[11px] uppercase tracking-[0.1em]">
            {[
              { v: false, label: "Guided", id: "mode-guided" },
              { v: true, label: "Autonomous", id: "mode-auto" },
            ].map((o) => (
              <span
                id={o.id}
                key={o.label}
                className={`px-3 py-1.5 transition-colors duration-300 ${autonomous === o.v ? "bg-ink text-paper" : "text-muted"}`}
              >
                {o.label}
              </span>
            ))}
          </div>
          <span className="font-mono text-[11px] text-faint">↵ to begin · ⇧↵ new line</span>
        </div>
        <div className="mt-10 border-t border-rule">
          {examples.map((ex, i) => (
            <div key={ex} className="flex w-full items-baseline gap-4 border-b border-rule py-3 text-left text-[14px] text-muted">
              <span className="font-mono text-[11px] text-faint">{String(i + 1).padStart(2, "0")}</span>
              <span className="flex-1">{ex}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Composer({ text, placeholder, focused }: { text: string; placeholder: string; focused?: boolean }) {
  return (
    <div
      id="composer"
      className={`flex items-end gap-2 border border-ink bg-paper px-4 py-3 transition-shadow ${focused ? "shadow-[4px_4px_0_0_#0a0a0a]" : ""}`}
    >
      <div className="min-h-[26px] flex-1 whitespace-pre-wrap text-[15px] leading-relaxed">
        {text ? <span className={focused ? "caret" : ""}>{text}</span> : <span className="text-faint">{placeholder}</span>}
      </div>
      <span
        id="send"
        className={`flex h-8 w-8 shrink-0 items-center justify-center font-mono transition-colors ${text.trim() ? "bg-ink text-paper" : "bg-rule text-faint"}`}
      >
        ↑
      </span>
    </div>
  );
}

function StatusLine({ text }: { text: string }) {
  return (
    <div className="mb-8">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">OpenScientist</div>
      <div className="flex items-center gap-3 font-mono text-[12px] text-muted">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping bg-ink opacity-40" />
          <span className="relative inline-flex h-2 w-2 bg-ink" />
        </span>
        {text}…
      </div>
    </div>
  );
}

function Bubble({ role, content }: { role: Message["role"]; content: string }) {
  if (role === "user") {
    return (
      <div className="film-new mb-8 flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap bg-ink px-4 py-3 text-[15px] leading-relaxed text-paper">{content}</div>
      </div>
    );
  }
  return (
    <div className="mb-8">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">OpenScientist</div>
      <div className="prose-os">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>
    </div>
  );
}
