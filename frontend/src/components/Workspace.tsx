"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  api,
  blueprintApi,
  executionApi,
  gapsApi,
  literatureApi,
  planApi,
  sendTurn,
  type Answer,
  type BlueprintRun as BlueprintRunT,
  type Depth,
  type Execution,
  type ModelPolicy,
  type GapsRun as GapsRunT,
  type Literature,
  type Message,
  type PlanRun as PlanRunT,
  type Project,
  type Turn,
} from "@/lib/api";
import BlueprintRun from "./BlueprintRun";
import BriefCard from "./BriefCard";
import ExecutionRun from "./ExecutionRun";
import GapsRun from "./GapsRun";
import Library from "./Library";
import LiteratureRun from "./LiteratureRun";
import PlanRun from "./PlanRun";
import Notebook from "./Notebook";
import QuestionCards from "./QuestionCards";
import Sidebar from "./Sidebar";
import WorkspaceFiles from "./WorkspaceFiles";
import StageBar from "./StageBar";

const EXAMPLES = [
  "Can small language models predict protein stability changes from mutations?",
  "Does sleep timing affect how well people remember what they learned that day?",
  "Which material properties best predict battery electrode degradation?",
];

type AnswersMessage = Extract<Message, { kind: "answers" }>;

export default function Workspace({ projectId: initialId }: { projectId?: string }) {
  const [projectId, setProjectId] = useState<string | null>(initialId ?? null);
  const [project, setProject] = useState<Project | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [streaming, setStreaming] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [autonomous, setAutonomous] = useState(false);
  const [lit, setLit] = useState<Literature | null>(null);
  const [gapsRun, setGapsRun] = useState<GapsRunT | null>(null);
  const [planRun, setPlanRun] = useState<{ run: PlanRunT | null; revisions: number } | null>(null);
  const [bpRun, setBpRun] = useState<BlueprintRunT | null>(null);
  const [exec, setExec] = useState<Execution | null>(null);
  const [execKick, setExecKick] = useState(0);
  const [files, setFiles] = useState<{ focus?: string } | null>(null);
  const [library, setLibrary] = useState<{ focus?: string } | null>(null);
  // A project created in this tab already has its state locally; skip the reload.
  const justCreated = useRef<string | null>(null);

  const refreshProjects = useCallback(() => {
    void api.listProjects().then(setProjects).catch((e) => setError(String(e)));
  }, []);

  useEffect(refreshProjects, [refreshProjects]);

  useEffect(() => {
    if (!projectId || justCreated.current === projectId) return;
    api
      .getProject(projectId)
      .then(({ project, messages }) => {
        setProject(project);
        setMessages(messages);
      })
      .catch((e) => setError(String(e)));
  }, [projectId]);

  // Poll the literature run while it is in progress (or about to start).
  const litStage = project && project.stage !== "clarify" ? project.id : null;
  const litStatus = lit?.run?.status;
  useEffect(() => {
    if (!litStage) return;
    let cancelled = false;
    const load = () =>
      literatureApi
        .get(litStage)
        .then((d) => !cancelled && setLit(d))
        .catch((e) => !cancelled && setError(String(e)));
    void load();
    if (litStatus === "done" || litStatus === "error") return () => void (cancelled = true);
    const timer = setInterval(load, 2000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [litStage, litStatus]);

  // Gap analysis starts automatically once the literature review completes.
  const gapsFor =
    project && (litStatus === "done" || ["gaps", "plan", "done"].includes(project.stage)) ? project.id : null;
  const gapsStatus = gapsRun?.status;
  // Autonomous mode picks a gap just after the run finishes; keep polling until it lands.
  const awaitingAutoChoice = Boolean(project?.autonomous && gapsStatus === "done" && !project?.chosen_gap);
  useEffect(() => {
    if (!gapsFor) return;
    let cancelled = false;
    const load = () =>
      gapsApi
        .get(gapsFor)
        .then((d) => {
          if (cancelled) return;
          setGapsRun(d.run);
          setProject(d.project);
        })
        .catch((e) => !cancelled && setError(String(e)));
    void load();
    if ((gapsStatus === "done" && !awaitingAutoChoice) || gapsStatus === "error") return () => void (cancelled = true);
    const timer = setInterval(load, 2500);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [gapsFor, gapsStatus, awaitingAutoChoice]);

  // The plan is drafted as soon as a gap is chosen.
  const planFor = project?.chosen_gap ? project.id : null;
  const planStatus = planRun?.run?.status;
  const planRunId = planRun?.run?.id;
  const awaitingAutoApproval = Boolean(project?.autonomous && planStatus === "done" && !project?.plan);
  useEffect(() => {
    if (!planFor) return;
    let cancelled = false;
    const load = () =>
      planApi
        .get(planFor)
        .then((d) => {
          if (cancelled) return;
          setPlanRun({ run: d.run, revisions: d.revisions });
          setProject(d.project);
        })
        .catch((e) => !cancelled && setError(String(e)));
    void load();
    if ((planStatus === "done" && !awaitingAutoApproval) || planStatus === "error") return () => void (cancelled = true);
    const timer = setInterval(load, 2500);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [planFor, planStatus, planRunId, awaitingAutoApproval]);

  // The blueprint compiles once the plan is approved.
  const bpFor = project?.plan ? project.id : null;
  const bpStatus = bpRun?.status;
  const bpRunId = bpRun?.id;
  const awaitingBpApproval = Boolean(project?.autonomous && bpStatus === "done" && !project?.blueprint);
  useEffect(() => {
    if (!bpFor) return;
    let cancelled = false;
    const load = () =>
      blueprintApi
        .get(bpFor)
        .then((d) => {
          if (cancelled) return;
          setBpRun(d.run);
          setProject(d.project);
        })
        .catch((e) => !cancelled && setError(String(e)));
    void load();
    const settled = !bpStatus ? project?.stage === "done" : bpStatus !== "running" && !awaitingBpApproval;
    if (settled) return () => void (cancelled = true);
    const timer = setInterval(load, 3000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- stage only matters for the no-run case
  }, [bpFor, bpStatus, bpRunId, awaitingBpApproval]);

  const startBlueprint = async () => {
    if (!projectId) return;
    try {
      setBpRun(await blueprintApi.run(projectId));
    } catch (e) {
      setError(String(e));
    }
  };

  const approveBlueprint = async () => {
    if (!projectId) return;
    try {
      setProject(await blueprintApi.approve(projectId));
      refreshProjects();
    } catch (e) {
      setError(String(e));
    }
  };

  // Execution: poll while the run is live (and once whenever an action kicks it).
  const execFor = project?.blueprint ? project.id : null;
  const execLive = Boolean(exec?.live);
  useEffect(() => {
    if (!execFor) return;
    let cancelled = false;
    const load = () =>
      executionApi
        .get(execFor)
        .then((d) => {
          if (cancelled) return;
          setExec(d);
          setProject(d.project);
        })
        .catch((e) => !cancelled && setError(String(e)));
    void load();
    if (!execLive && execKick === 0) return () => void (cancelled = true);
    const timer = setInterval(load, 2000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [execFor, execLive, execKick]);

  const execAction = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      setExecKick((k) => k + 1);
    } catch (e) {
      setError(String(e));
    }
  };

  const startedPlan = (run: PlanRunT) => setPlanRun((p) => ({ run, revisions: p?.revisions ?? 0 }));

  const approvePlan = async () => {
    if (!projectId) return;
    try {
      setProject(await planApi.approve(projectId));
      refreshProjects();
    } catch (e) {
      setError(String(e));
    }
  };

  const retryPlan = async () => {
    if (!projectId) return;
    try {
      startedPlan(await planApi.rerun(projectId));
    } catch (e) {
      setError(String(e));
    }
  };

  const selectGap = async (gapId: string) => {
    if (!projectId) return;
    try {
      setProject(await gapsApi.select(projectId, gapId));
      setPlanRun(null);
      refreshProjects();
    } catch (e) {
      setError(String(e));
    }
  };

  const regenerateGaps = async (feedback: string) => {
    if (!projectId) return;
    try {
      setGapsRun(await gapsApi.rerun(projectId, feedback));
      setProject((p) => (p ? { ...p, chosen_gap: null, stage: "gaps" } : p));
    } catch (e) {
      setError(String(e));
    }
  };

  const retryLiterature = async () => {
    if (!projectId) return;
    try {
      await literatureApi.rerun(projectId);
      setLit((l) => (l ? { ...l, run: l.run && { ...l.run, status: "running", phase: "starting", error: null } } : l));
    } catch (e) {
      setError(String(e));
    }
  };

  // Switch investigations without remounting the page.
  const openProject = (id: string | null) => {
    if (busy) return;
    window.history.pushState(null, "", id ? `/p/${id}` : "/");
    setError(null);
    if (!id) {
      setProject(null);
      setMessages([]);
    }
    setLit(null);
    setGapsRun(null);
    setPlanRun(null);
    setBpRun(null);
    setExec(null);
    setExecKick(0);
    setFiles(null);
    setLibrary(null);
    setProjectId(id);
  };

  const runTurn = async (turn: Turn) => {
    if (busy) return;
    // While reviewing a plan, a reply is a revision request.
    // While reviewing a blueprint, a reply revises it.
    if (turn.kind === "text" && projectId && (project?.stage === "blueprint" || project?.stage === "ready") && bpRun?.status === "done") {
      setError(null);
      try {
        const { message, run } = await blueprintApi.revise(projectId, turn.content);
        setMessages((m) => [...m, message]);
        setBpRun(run);
        setProject((p) => (p ? { ...p, blueprint: null, stage: "blueprint" } : p));
      } catch (e) {
        setError(String(e));
      }
      return;
    }
    const reviewingPlan = project?.stage === "plan" || project?.stage === "done";
    if (turn.kind === "text" && projectId && reviewingPlan && planRun?.run?.status === "done") {
      setError(null);
      try {
        const { message, run } = await planApi.revise(projectId, turn.content);
        setMessages((m) => [...m, message]);
        startedPlan(run);
        setProject((p) => (p ? { ...p, plan: null } : p));
      } catch (e) {
        setError(String(e));
      }
      return;
    }
    setError(null);
    setBusy(true);
    setStatus(null);

    let id = projectId;
    try {
      if (!id) {
        const created = await api.createProject({ autonomous });
        id = created.id;
        justCreated.current = id;
        setProject(created);
        window.history.pushState(null, "", `/p/${id}`);
        setProjectId(id);
      }
      for await (const ev of sendTurn(id, turn)) {
        switch (ev.event) {
          case "message":
            setStreaming(null);
            setStatus(null);
            setMessages((m) => [...m, ev.data]);
            break;
          case "status":
            setStatus(ev.data.text);
            break;
          case "delta":
            setStatus(null);
            setStreaming((s) => (s ?? "") + ev.data.text);
            break;
          case "project":
            setProject(ev.data);
            break;
          case "error":
            setError(ev.data.message);
            break;
        }
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
      setStatus(null);
      setStreaming(null);
      refreshProjects();
    }
  };

  const confirmBrief = async (depth: Depth, maxPapers: number) => {
    if (!projectId) return;
    try {
      setProject(await api.confirmBrief(projectId, { depth, max_papers: maxPapers }));
      refreshProjects();
    } catch (e) {
      setError(String(e));
    }
  };

  const remove = async (id: string) => {
    if (!confirm("Delete this investigation? This cannot be undone.")) return;
    await api.deleteProject(id);
    if (id === projectId) openProject(null);
    refreshProjects();
  };

  const empty = !projectId && messages.length === 0;

  return (
    <div className="flex h-full">
      <Sidebar
        projects={projects}
        activeId={projectId}
        onSelect={openProject}
        onNew={() => openProject(null)}
        onDelete={remove}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-rule px-6">
          <StageBar stage={project?.stage ?? "clarify"} />
          <span className="shrink-0 pl-4 font-mono text-[11px] uppercase tracking-[0.12em] text-faint">
            {project ? (project.autonomous ? "Autonomous" : "Guided") : ""}
          </span>
        </header>

        {empty ? (
          <EmptyState
            autonomous={autonomous}
            setAutonomous={setAutonomous}
            onSubmit={(content) => runTurn({ kind: "text", content })}
            busy={busy}
          />
        ) : (
          <>
            <Thread
              project={project}
              messages={messages}
              busy={busy}
              status={status}
              streaming={streaming}
              error={error}
              onAnswer={(question_message_id, answers) => runTurn({ kind: "answers", question_message_id, answers })}
              onConfirm={confirmBrief}
              literature={
                project && project.stage !== "clarify" ? (
                  <>
                    {(lit?.run || project.stage === "literature") && (
                      <LiteratureRun
                        project={project}
                        lit={lit}
                        onRetry={retryLiterature}
                        onOpenLibrary={(focus) => setLibrary({ focus })}
                      />
                    )}
                    {gapsFor && (
                      <GapsRun
                        project={project}
                        run={gapsRun}
                        papers={lit?.papers ?? []}
                        onSelect={selectGap}
                        onRegenerate={regenerateGaps}
                        onOpenPaper={(focus) => setLibrary({ focus })}
                      />
                    )}
                    {planFor && (
                      <PlanRun
                        project={project}
                        run={planRun?.run ?? null}
                        revisions={planRun?.revisions ?? 0}
                        onApprove={approvePlan}
                        onRetry={retryPlan}
                        onSaved={(run) => {
                          setPlanRun((p) => ({ run, revisions: (p?.revisions ?? 0) + 1 }));
                          setProject((p) => (p ? { ...p, plan: null, stage: "plan" } : p));
                        }}
                      />
                    )}
                    {bpFor && (
                      <BlueprintRun project={project} run={bpRun} onStart={startBlueprint} onApprove={approveBlueprint} />
                    )}
                    {execFor && bpRun?.result && (
                      <ExecutionRun
                        project={project}
                        exec={exec}
                        mp={bpRun.result.master_plan}
                        onStart={(budget: number, policy: ModelPolicy) =>
                          execAction(() => executionApi.start(project.id, { budget_usd: budget, model_policy: policy }))
                        }
                        onPause={() => execAction(() => executionApi.pause(project.id))}
                        onResume={(budget?: number) =>
                          execAction(() => executionApi.resume(project.id, budget ? { budget_usd: budget } : {}))
                        }
                        onCancel={() => execAction(() => executionApi.cancel(project.id))}
                        onTask={(taskId, action, note) => execAction(() => executionApi.task(project.id, taskId, action, note))}
                        onOpenFiles={(focus) => setFiles({ focus })}
                      />
                    )}
                  </>
                ) : null
              }
            />
            <div className="mx-auto w-full max-w-3xl px-6 pb-6">
              <Composer
                onSubmit={(content) => runTurn({ kind: "text", content })}
                busy={busy}
                placeholder={composerHint(project, messages)}
              />
            </div>
          </>
        )}
      </main>

      <Notebook
        project={project}
        lit={lit}
        gapsRun={gapsRun}
        planRun={planRun?.run ?? null}
        bpRun={bpRun}
        exec={exec}
        onOpenFiles={() => setFiles({})}
        onOpenLibrary={() => setLibrary({})}
      />
      {files && projectId && (
        <WorkspaceFiles projectId={projectId} focus={files.focus} onClose={() => setFiles(null)} />
      )}
      {library && projectId && lit && (
        <Library projectId={projectId} papers={lit.papers} focus={library.focus} onClose={() => setLibrary(null)} />
      )}
    </div>
  );
}

function composerHint(project: Project | null, messages: Message[]) {
  const last = messages.at(-1);
  if (last?.kind === "questions") return "Answer above, or type anything to add context…";
  if (project?.stage === "clarify" && last?.kind === "brief") return "Suggest a change to the brief…";
  if (project?.stage === "blueprint" || project?.stage === "ready")
    return "Ask for changes to the blueprint, e.g. “merge the two data agents”…";
  if (project?.stage === "plan" || project?.stage === "done") return "Ask for changes to the plan, e.g. “add an ablation study”…";
  return "Reply…";
}

function EmptyState({
  autonomous,
  setAutonomous,
  onSubmit,
  busy,
}: {
  autonomous: boolean;
  setAutonomous: (v: boolean) => void;
  onSubmit: (text: string) => void;
  busy: boolean;
}) {
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
          <Composer onSubmit={onSubmit} busy={busy} placeholder="e.g. I wonder whether…" autoFocus />
        </div>

        <div className="mt-3 flex items-center justify-between">
          <ModeToggle autonomous={autonomous} setAutonomous={setAutonomous} />
          <span className="font-mono text-[11px] text-faint">↵ to begin · ⇧↵ new line</span>
        </div>

        <div className="mt-10 border-t border-rule">
          {EXAMPLES.map((ex, i) => (
            <button
              key={ex}
              onClick={() => onSubmit(ex)}
              disabled={busy}
              className="group flex w-full items-baseline gap-4 border-b border-rule py-3 text-left text-[14px] text-muted transition-colors hover:text-ink"
            >
              <span className="font-mono text-[11px] text-faint">{String(i + 1).padStart(2, "0")}</span>
              <span className="flex-1">{ex}</span>
              <span className="font-mono text-faint opacity-0 transition-opacity group-hover:opacity-100">→</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function ModeToggle({ autonomous, setAutonomous }: { autonomous: boolean; setAutonomous: (v: boolean) => void }) {
  return (
    <div className="flex border border-rule font-mono text-[11px] uppercase tracking-[0.1em]" role="radiogroup">
      {[
        { v: false, label: "Guided", title: "You choose the research gap and approve the plan" },
        { v: true, label: "Autonomous", title: "OpenScientist makes every choice and runs end to end" },
      ].map((o) => (
        <button
          key={o.label}
          role="radio"
          aria-checked={autonomous === o.v}
          title={o.title}
          onClick={() => setAutonomous(o.v)}
          className={`px-3 py-1.5 transition-colors ${autonomous === o.v ? "bg-ink text-paper" : "text-muted hover:text-ink"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function Thread({
  project,
  messages,
  busy,
  status,
  streaming,
  error,
  onAnswer,
  onConfirm,
  literature,
}: {
  literature: React.ReactNode;
  project: Project | null;
  messages: Message[];
  busy: boolean;
  status: string | null;
  streaming: string | null;
  error: string | null;
  onAnswer: (questionMessageId: string, answers: Answer[]) => void;
  onConfirm: (depth: Depth, maxPapers: number) => Promise<void>;
}) {
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [messages.length, streaming, status]);

  const answersFor = new Map<string, AnswersMessage>();
  for (const m of messages) if (m.kind === "answers") answersFor.set(m.payload.question_message_id, m);
  const latestBrief = messages.findLast((m) => m.kind === "brief")?.id;

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl px-6 py-10">
        {messages.map((m) => {
          switch (m.kind) {
            case "questions":
              return (
                <QuestionCards
                  key={m.id}
                  message={m}
                  answered={answersFor.get(m.id)}
                  busy={busy}
                  onSubmit={(answers) => onAnswer(m.id, answers)}
                />
              );
            case "answers":
              return null; // rendered inside its QuestionCards
            case "brief":
              return project ? (
                <Fragment key={m.id}>
                  <BriefCard
                    message={m}
                    project={project}
                    latest={m.id === latestBrief}
                    busy={busy}
                    onConfirm={onConfirm}
                  />
                  {m.id === latestBrief && literature}
                </Fragment>
              ) : null;
            default:
              return <Bubble key={m.id} role={m.role} content={m.content} />;
          }
        })}
        {!latestBrief && literature}
        {streaming !== null && <Bubble role="assistant" content={streaming} live />}
        {busy && streaming === null && <StatusLine text={status ?? "Thinking"} />}
        {error && (
          <div className="mt-4 border border-ink px-4 py-3 font-mono text-[12px]">
            <span className="uppercase tracking-wider">Error</span> — {error}
          </div>
        )}
        <div ref={bottom} />
      </div>
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

function Bubble({ role, content, live }: { role: Message["role"]; content: string; live?: boolean }) {
  if (role === "user") {
    return (
      <div className="mb-8 flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap bg-ink px-4 py-3 text-[15px] leading-relaxed text-paper">
          {content}
        </div>
      </div>
    );
  }
  return (
    <div className="mb-8">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.14em] text-faint">OpenScientist</div>
      {content ? (
        <div className={`prose-os ${live ? "caret" : ""}`}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        </div>
      ) : (
        <div className="font-mono text-[12px] text-muted">
          Thinking<span className="caret" />
        </div>
      )}
    </div>
  );
}

function Composer({
  onSubmit,
  busy,
  placeholder,
  autoFocus,
}: {
  onSubmit: (text: string) => void;
  busy: boolean;
  placeholder: string;
  autoFocus?: boolean;
}) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
  }, [text]);

  const send = () => {
    if (!text.trim() || busy) return;
    onSubmit(text);
    setText("");
  };

  return (
    <div className="flex items-end gap-2 border border-ink bg-paper px-4 py-3 focus-within:shadow-[4px_4px_0_0_#0a0a0a] transition-shadow">
      <textarea
        ref={ref}
        rows={1}
        value={text}
        autoFocus={autoFocus}
        placeholder={placeholder}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            send();
          }
        }}
        className="max-h-60 flex-1 resize-none bg-transparent text-[15px] leading-relaxed outline-none placeholder:text-faint"
      />
      <button
        onClick={send}
        disabled={busy || !text.trim()}
        aria-label="Send"
        className="flex h-8 w-8 shrink-0 items-center justify-center bg-ink font-mono text-paper disabled:bg-rule disabled:text-faint"
      >
        {busy ? "…" : "↑"}
      </button>
    </div>
  );
}
