"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import BlueprintRun from "@/components/BlueprintRun";
import BriefCard from "@/components/BriefCard";
import ExecutionRun from "@/components/ExecutionRun";
import GapsRun from "@/components/GapsRun";
import LiteratureRun from "@/components/LiteratureRun";
import PlanRun from "@/components/PlanRun";
import QuestionCards from "@/components/QuestionCards";
import ReviewRun from "@/components/ReviewRun";
import Sidebar from "@/components/Sidebar";
import StageBar from "@/components/StageBar";
import Notebook from "@/components/walkthrough/Notebook";
import ReportRun from "@/components/walkthrough/ReportRun";
import { heatwavePages } from "@/components/walkthrough/overlays";
import "@/components/walkthrough/film.css";
import {
  api,
  type BlueprintRun as BlueprintRunT,
  type Execution,
  type GapsRun as GapsRunT,
  type Literature,
  type Message,
  type PlanRun as PlanRunT,
  type Project,
  type ProjectSummary,
  type ReportRun as ReportRunT,
  type ReviewLogLine,
  type ReviewView,
  type Run,
} from "@/lib/api";
import { ago, message, now, run, schedule, taskState } from "./kit";
import { documentPages, PaperGrid } from "./PaperDoc";
import type { ReplayData } from "./types";

class Stopped extends Error {}

/** Total length of the execution stage at speed 1, in ms. */
const EXEC_MS = 180_000;

/** A pre-made run, replayed stage by stage in the workspace, at a pace that reads as live. */
export default function Replay({ data, speed = 1 }: { data: ReplayData; speed?: number }) {
  const router = useRouter();
  const pid = `replay-${data.slug}`;
  const [project, setProject] = useState<Project>(() => baseProject(pid));
  const [messages, setMessages] = useState<Message[]>([]);
  const [answers, setAnswers] = useState<ReplayData["answers"] | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [lit, setLit] = useState<Literature | null>(null);
  const [gaps, setGaps] = useState<GapsRunT | null>(null);
  const [plan, setPlan] = useState<PlanRunT | null>(null);
  const [bp, setBp] = useState<BlueprintRunT | null>(null);
  const [exec, setExec] = useState<Execution | null>(null);
  const [report, setReport] = useState<ReportRunT | null>(null);
  const [review, setReview] = useState<{ view: ReviewView; log: ReviewLogLine[] } | null>(null);
  const [spent, setSpent] = useState(0);
  const [others, setOthers] = useState<ProjectSummary[]>([]);
  const thread = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.listProjects().then(setOthers, () => {});
  }, []);

  useEffect(() => {
    let dead = false;
    const W = (ms: number) =>
      new Promise<void>((resolve, reject) => setTimeout(() => (dead ? reject(new Stopped()) : resolve()), ms / speed));
    // Scroll a newly added card into view once it has rendered.
    const reveal = (id: string, tries = 20) => {
      setTimeout(() => {
        const el = document.getElementById(id);
        if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
        else if (tries > 0 && !dead) reveal(id, tries - 1);
      }, 150);
    };
    // eslint-disable-next-line react-hooks/immutability -- the script is declared below and only starts after mount
    void script(W, reveal).catch((e) => {
      if (!(e instanceof Stopped)) console.error(e);
    });
    return () => {
      dead = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function script(W: (ms: number) => Promise<void>, reveal: (id: string) => void) {
    const d = data;
    let p = baseProject(pid);
    const setP = (patch: Partial<Project>) => {
      p = { ...p, ...patch, updated_at: now() };
      setProject(p);
    };
    const userMsg = message(pid, "m1", "user", "text", null, d.question);
    const questionsMsg = message(pid, "m2", "assistant", "questions", d.questions);
    const briefMsg = message(pid, "m4", "assistant", "brief", {
      message: "Here is the research brief I'll work from. Confirming automatically at **deep** depth.",
      brief: d.brief,
    });

    // 01 · Clarify
    setP({ title: d.shortTitle });
    setMessages([userMsg]);
    setStatus("Reading your question");
    await W(2600);
    setStatus("Drafting clarifying questions");
    await W(4200);
    setStatus(null);
    setMessages([userMsg, questionsMsg]);
    reveal("card-questions");
    await W(3500);
    for (let k = 1; k <= d.answers.length; k++) {
      setAnswers(d.answers.slice(0, k));
      await W(2600);
    }
    setStatus("Writing the research brief");
    await W(5200);
    setStatus(null);
    setMessages([userMsg, questionsMsg, briefMsg]);
    setP({ brief: d.brief, title: d.brief.title });
    reveal("card-brief");
    await W(4500);

    // 02 · Literature
    setP({ stage: "literature" });
    const L = d.lit;
    const queries = [...d.brief.search_keywords, ...d.overview.common_methods].slice(0, L.queries);
    const litLog: Run["log"] = [];
    const log = (text: string) => litLog.push({ t: now(), text });
    const litAt = (over: Partial<Run>, papers = 0) =>
      setLit({ run: run<Run>("literature", "lit1", { started_at: ago(5), log: [...litLog].slice(-6), ...over }), papers: d.papers.slice(0, papers) });
    litAt({ phase: "starting" });
    reveal("card-lit");
    await W(2500);
    for (let q = 1; q <= L.queries; q++) {
      log(`Searched “${queries[q - 1] ?? d.brief.title}” · Semantic Scholar + OpenAlex`);
      litAt({ phase: "searching", counts: { queries_done: q, queries_total: L.queries, found: Math.round((L.found * q) / L.queries) } });
      await W(2800);
    }
    const candidates = L.screened;
    for (let k = 1; k <= 6; k++) {
      litAt({
        phase: "screening",
        counts: { queries_done: L.queries, queries_total: L.queries, found: L.found, candidates, screened: Math.round((candidates * k) / 6), included: Math.round((L.included * k) / 6) },
      });
      await W(2600);
    }
    log(`Screened ${candidates} candidates → ${L.included} relevant`);
    log(`Followed ${L.citations} citations → ${Math.round(L.citations / 7)} new candidates`);
    const base = { queries_done: L.queries, queries_total: L.queries, found: L.found, candidates, screened: candidates, included: L.included };
    litAt({ phase: "expanding", counts: base });
    await W(6000);
    for (let k = 1; k <= 8; k++) {
      litAt({ phase: "reading", counts: { ...base, extracted: Math.round((L.included * k) / 8) } }, Math.round((d.papers.length * k) / 8));
      if (k === 4) log(`Extracting structured notes · ${Math.round(L.included / 2)}/${L.included}`);
      await W(3200);
    }
    log(`Extracted notes for ${L.included}/${L.included} papers`);
    litAt({ phase: "linking", counts: { ...base, extracted: L.included } }, d.papers.length);
    await W(4500);
    log(`Linked ${L.links.toLocaleString("en-US")} citations between papers`);
    log("Synthesising themes and open problems");
    litAt({ phase: "synthesising", counts: { ...base, extracted: L.included } }, d.papers.length);
    await W(7000);
    const morePapers = Array.from({ length: Math.max(0, L.included - d.papers.length) }, (_, i) => ({ ...d.papers[i % d.papers.length], id: `x${i}` }));
    setLit({
      run: run<Run>("literature", "lit1", { status: "done", phase: "done", counts: { ...base, extracted: L.included }, result: { overview: d.overview }, finished_at: now() }),
      papers: [...d.papers, ...morePapers],
    });
    setSpent(d.spend.literature);
    await W(4000);

    // 03 · Gaps
    setP({ stage: "gaps" });
    setGaps(run<GapsRunT>("gaps", "gap1", { phase: "proposing", log: [{ t: now(), text: `Reasoning over ${L.included} papers’ notes` }] }));
    reveal("card-gaps");
    await W(16000);
    const n = d.gaps.length;
    for (let k = 1; k <= n; k++) {
      setGaps(
        run<GapsRunT>("gaps", "gap1", {
          phase: "checking",
          started_at: ago(30 + k * 8),
          counts: { proposed: n, checked: k } as never,
          log: [{ t: now(), text: `Novelty check · gap ${k}: searching prior work` }],
        }),
      );
      await W(4200);
    }
    setGaps(run<GapsRunT>("gaps", "gap1", { phase: "ranking", counts: { proposed: n, checked: n } as never, log: [{ t: now(), text: "Scoring novelty, feasibility, impact, testability" }] }));
    await W(4000);
    const gapsDone = run<GapsRunT>("gaps", "gap1", { status: "done", phase: "done", result: { gaps: d.gaps, recommended: d.gaps[0].id, feedback: null }, finished_at: now() });
    setGaps(gapsDone);
    setP({ chosen_gap: { ...d.gaps[0], run_id: gapsDone.id }, stage: "plan" });
    setSpent(d.spend.gaps);
    await W(5000);

    // 04 · Plan
    const planLog: Run["log"] = [];
    setPlan(run<PlanRunT>("plan", "plan1", { phase: "drafting" }));
    reveal("card-plan");
    for (let k = 0; k < d.planLog.length; k++) {
      planLog.push({ t: now(), text: d.planLog[k] });
      setPlan(run<PlanRunT>("plan", "plan1", { phase: k < d.planLog.length - 1 ? "drafting" : "validating", log: [...planLog] }));
      await W(k < 2 ? 7000 : 4500);
    }
    const planDone = run<PlanRunT>("plan", "plan1", {
      status: "done",
      phase: "done",
      log: planLog,
      result: { plan: d.plan, gap_id: d.gaps[0].id, gaps_run_id: gapsDone.id, audit: d.planAudit } as never,
      finished_at: now(),
    });
    setPlan(planDone);
    setP({ plan: { ...d.plan, run_id: planDone.id, approved_at: now() }, stage: "done" });
    setSpent(d.spend.plan);
    await W(5000);

    // 05 · Blueprint
    const bpLog: Run["log"] = [];
    const phases = ["resolving", "resolving", "compiling", "validating"];
    setBp(run<BlueprintRunT>("blueprint", "bp1", { phase: "resolving" }));
    reveal("card-bp");
    for (let k = 0; k < d.bpLog.length; k++) {
      bpLog.push({ t: now(), text: d.bpLog[k] });
      setBp(run<BlueprintRunT>("blueprint", "bp1", { phase: phases[Math.min(k, phases.length - 1)], log: [...bpLog] }));
      await W(6500);
    }
    const bpDone = run<BlueprintRunT>("blueprint", "bp1", {
      status: "done",
      phase: "done",
      log: bpLog,
      result: { master_plan: d.master, warnings: [], capabilities: [], budget: { llm_usd: d.budget, gpu_hours: 0 } } as never,
      finished_at: now(),
    });
    setBp(bpDone);
    setP({ blueprint: { run_id: bpDone.id, approved_at: now() }, stage: "ready" });
    setSpent(d.spend.blueprint);
    await W(5000);

    // 06 · Execution
    setP({ stage: "executing" });
    const plan2 = schedule(d.master, EXEC_MS);
    const execTotal = Object.values(d.taskCost).reduce((a, b) => a + b, 0);
    const tasksAt = (ms: number) =>
      d.master.tasks.map((tk) => {
        const s = plan2[tk.id];
        const st = ms >= s.end ? "done" : ms >= s.start ? "running" : "pending";
        const lines = d.toolScript[tk.id] ?? [];
        const shown = st === "done" ? lines.length : st === "running" ? Math.ceil(((ms - s.start) / (s.end - s.start)) * lines.length) : 0;
        const failed = lines.slice(0, shown).some((e) => e.tool === "error" || e.tool === "verifier");
        const frac = st === "done" ? 1 : st === "running" ? (ms - s.start) / (s.end - s.start) : 0;
        return taskState(tk.id, tk.agent, {
          status: st,
          attempts: st === "pending" ? 0 : failed ? 2 : 1,
          cost: Math.round((d.taskCost[tk.id] ?? 0) * frac * 100) / 100,
          // Shown durations run ~25× the replay clock, as a real task's would.
          started_at: st !== "pending" ? ago(((Math.min(ms, s.end) - s.start) / 1000) * 25) : null,
          finished_at: st === "done" ? now() : null,
          summary: st === "done" ? (lines.at(-1)?.args ?? null) : null,
          checks: st === "done" ? [{ check: "Declared outputs exist", passed: true, reason: "verified by the platform" }] : [],
          events: lines.slice(0, shown).map((e, i) => ({ type: "tool" as const, step: i + 1, tool: e.tool, args: e.args, sub: e.sub, cost: 0.01, t: now() })),
        });
      });
    const execRun = run<Run>("execution", "ex1", { phase: "running" });
    reveal("card-exec");
    const tick = 1500;
    for (let ms = 0; ms <= EXEC_MS; ms += tick) {
      const tasks = tasksAt(ms);
      const cost = tasks.reduce((a, t) => a + t.cost, 0);
      setExec({ run: execRun, project: p, tasks, spent: Math.round(cost * 100) / 100, budget: d.budget, model_policy: "default", paused: null, live: true });
      setSpent(Math.round((d.spend.blueprint + (cost / execTotal) * (d.spend.execution - d.spend.blueprint)) * 100) / 100);
      await W(tick);
    }
    setExec({
      run: run<Run>("execution", "ex1", { status: "done", phase: "done", result: { counts: { done: d.master.tasks.length } } as never, finished_at: now() }),
      project: p,
      tasks: tasksAt(Infinity),
      spent: Math.round(execTotal * 100) / 100,
      budget: d.budget,
      model_policy: "default",
      paused: null,
      live: false,
    });
    setP({ stage: "executed" });
    setSpent(d.spend.execution);
    await W(4000);

    // 07 · Report
    setP({ stage: "reporting" });
    setReport(run<ReportRunT>("report", "rep1", { phase: "consolidating" }));
    reveal("card-report");
    await W(11000);
    setReport(run<ReportRunT>("report", "rep1", { phase: "writing" }));
    await W(16000);
    setReport(run<ReportRunT>("report", "rep1", { phase: "auditing" }));
    await W(8000);
    setReport(run<ReportRunT>("report", "rep1", { status: "done", phase: "done", result: d.report, finished_at: now() }));
    setSpent(d.spend.report);
    await W(6000);

    // 08 · Review
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
    const line = (text: string, kind: "review" | "repair" = "review"): ReviewLogLine => ({ t: now(), text, kind });
    let rlog: ReviewLogLine[] = [];
    setP({ stage: "reviewing", review: { status: "reviewing", iteration: 1 } });
    setReview({ view: reviewStart, log: rlog });
    reveal("card-review");
    for (const l of d.reviewLog.round1) {
      rlog = [...rlog, line(l)];
      setReview({ view: reviewStart, log: rlog });
      await W(4500);
    }
    const it1 = { ...d.iterations[0], issues: d.round1Issues };
    const repairing: ReviewView = {
      ...reviewStart,
      status: "repairing",
      step: "execute",
      iterations: [it1],
      spent_usd: d.iterations[0].cost_usd,
      live: { review: false, repair: false, execute: true, report: false },
    };
    rlog = [...rlog, line(d.reviewLog.repair[0]), line(d.reviewLog.repair[1], "repair")];
    setP({ review: { status: "repairing", iteration: 1 } });
    setReview({ view: repairing, log: rlog });
    await W(12000);
    rlog = [...rlog, line(d.reviewLog.repair[2], "repair")];
    setReview({ view: { ...repairing, step: "report", live: { review: false, repair: false, execute: false, report: true } }, log: rlog });
    await W(7000);
    const it2 = { ...d.iterations[1], issues: [d.round1Issues[2]] };
    const spent2 = d.iterations[0].cost_usd + d.iterations[1].cost_usd;
    rlog = [...rlog, line(d.reviewLog.round2[0])];
    setReview({
      view: { ...repairing, status: "reviewing", step: "review", iteration: 2, iterations: [it1, it2], spent_usd: spent2, live: { review: true, repair: false, execute: false, report: false } },
      log: rlog,
    });
    await W(9000);
    rlog = [...rlog, line(d.reviewLog.round3[0])];
    const total = spent2 + d.iterations[2].cost_usd;
    const last = d.iterations[2].score;
    setP({ stage: "complete", review: { status: "approved", iteration: 3 } });
    setReview({
      view: {
        ...repairing,
        status: "approved",
        step: null,
        iteration: 3,
        iterations: [it1, it2, { ...d.iterations[2], issues: [] }],
        spent_usd: Math.round(total * 100) / 100,
        live: { review: false, repair: false, execute: false, report: false },
        outcome: { status: "approved", reason: `Score ${last} / 10 meets the target. No blocking issues remain.`, unresolved: [], open_concerns: [], needs_human: [] },
      },
      log: rlog,
    });
    setSpent(d.spend.review);
  }

  // ── render ──────────────────────────────────────────────────────────────

  const runningStage = (
    [
      ["literature", lit?.run?.status],
      ["gaps", gaps?.status],
      ["plan", plan?.status],
      ["blueprint", bp?.status],
      ["execution", exec?.live ? "running" : undefined],
      ["report", report?.status],
      ["review", review && review.view.status !== "approved" ? "running" : undefined],
    ] as const
  ).find(([, s]) => s === "running")?.[0];

  const answered: Extract<Message, { kind: "answers" }> | undefined = answers
    ? message(pid, "m3", "user", "answers", { question_message_id: "m2", answers, auto: true })
    : undefined;
  const noop = async () => {};
  const paperPages = data.paper === "heatwave" ? heatwavePages() : documentPages(data.paper);
  const projects: ProjectSummary[] = [
    { id: pid, title: project.title, stage: project.stage, autonomous: true, created_at: project.created_at, updated_at: project.updated_at, review: project.review },
    ...others,
  ];

  return (
    <div className="fixed inset-0 flex overflow-hidden bg-paper">
      <Sidebar
        projects={projects}
        activeId={pid}
        onSelect={(id) => router.push(id === pid ? `/replay/${data.slug}` : `/p/${id}`)}
        onNew={() => router.push("/")}
        onDelete={() => {}}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-rule px-6">
          <StageBar stage={project.stage} />
          <span className="flex shrink-0 items-center gap-3 pl-4 font-mono text-[11px] uppercase tracking-[0.12em] text-faint">
            {runningStage && <span className="border border-ink px-2 py-0.5 text-ink">■ Stop {runningStage}</span>}
            <span title="A pre-made run, replayed">↻ Replay</span>
          </span>
        </header>

        <div ref={thread} className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl px-6 py-10">
            {messages.map((m) => {
              if (m.kind === "questions")
                return (
                  <div id="card-questions" key={m.id} className="film-new scroll-mt-6">
                    <QuestionCards message={m} answered={answered} busy={false} onSubmit={() => {}} />
                  </div>
                );
              if (m.kind === "brief")
                return (
                  <div key={m.id}>
                    <div id="card-brief" className="film-new scroll-mt-6">
                      <BriefCard message={m} project={project} latest busy={false} onConfirm={noop} />
                    </div>
                    {lit && (
                      <div id="card-lit" className="film-new scroll-mt-6">
                        <LiteratureRun project={project} lit={lit} onRetry={noop} onOpenLibrary={() => {}} />
                      </div>
                    )}
                    {gaps && (
                      <div id="card-gaps" className="film-new scroll-mt-6">
                        <GapsRun project={project} run={gaps} papers={lit?.papers ?? []} onSelect={noop} onRegenerate={noop} onOpenPaper={() => {}} />
                      </div>
                    )}
                    {plan && (
                      <div id="card-plan" className="film-new scroll-mt-6">
                        <PlanRun project={project} run={plan} revisions={0} onApprove={noop} onRetry={noop} onSaved={() => {}} />
                      </div>
                    )}
                    {bp && (
                      <div id="card-bp" className="film-new scroll-mt-6">
                        <BlueprintRun project={project} run={bp} onStart={noop} onApprove={noop} />
                      </div>
                    )}
                    {exec && (
                      <div id="card-exec" className="film-new scroll-mt-6">
                        <ExecutionRun
                          project={project}
                          exec={exec}
                          mp={data.master}
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
                      <div id="card-report" className="film-new scroll-mt-6">
                        <ReportRun project={project} run={report} onStart={noop} onOpenFiles={() => {}} paper={<PaperGrid pages={paperPages} />} />
                      </div>
                    )}
                    {review && (
                      <div id="card-review" className="film-new scroll-mt-6">
                        <ReviewRun project={project} review={review.view} enabled run={null} log={review.log} onAction={noop} />
                      </div>
                    )}
                  </div>
                );
              if (m.kind === "text")
                return (
                  <div key={m.id} className="film-new mb-8 flex justify-end">
                    <div className="max-w-[85%] whitespace-pre-wrap bg-ink px-4 py-3 text-[15px] leading-relaxed text-paper">{m.content}</div>
                  </div>
                );
              return null;
            })}
            {status && (
              <div className="mb-8">
                <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">OpenScientist</div>
                <div className="flex items-center gap-3 font-mono text-[12px] text-muted">
                  <span className="relative flex h-2 w-2">
                    <span className="absolute inline-flex h-full w-full animate-ping bg-ink opacity-40" />
                    <span className="relative inline-flex h-2 w-2 bg-ink" />
                  </span>
                  {status}…
                </div>
              </div>
            )}
            <div className="h-[40vh]" />
          </div>
        </div>
        <div className="mx-auto w-full max-w-3xl px-6 pb-6">
          <div className="flex items-end gap-2 border border-ink bg-paper px-4 py-3">
            <div className="min-h-[26px] flex-1 text-[15px] leading-relaxed text-faint">Reply…</div>
            <span className="flex h-8 w-8 shrink-0 items-center justify-center bg-rule font-mono text-faint">↑</span>
          </div>
        </div>
      </main>

      <Notebook
        project={project}
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
  );
}

function baseProject(pid: string): Project {
  const t = now();
  return {
    id: pid,
    title: "New investigation",
    stage: "clarify",
    autonomous: true,
    settings: { depth: "deep", max_papers: 300, citation_hops: 1, budget: { llm_usd: 100, gpu_hours: 0 } },
    brief: null,
    chosen_gap: null,
    plan: null,
    blueprint: null,
    review: null,
    created_at: t,
    updated_at: t,
  };
}
