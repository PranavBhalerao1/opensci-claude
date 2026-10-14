"""The scientific review and refinement loop (app/refine.py), end to end and offline.

Runs the real chain: pipeline hooks → review job (integrity gates, evidence bundle, judge,
verification) → repair job (Planning Agent decision, plan revision, blueprint delta, carry-over,
task re-runs) → the real orchestrator scheduler → report → a fresh review. Model calls are
scripted per schema, the task agent and verifier are faked (the test_attempts pattern), and the
report writer is faked; nothing touches the network or the real workspaces folder.
"""

import asyncio
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import anthropic
import httpx2
import pytest
from sqlmodel import Session, select

from app import jobs, llm, pipeline, refine
from app.agents import blueprint as blueprint_agent
from app.agents import judge
from app.agents import plan as plan_agent
from app.agents import report as report_agent
from app.agents.blueprint import BlueprintDelta, ExecTask
from app.agents.judge import Evidence, IssueCheck, JudgeReport, VerificationReport
from app.agents.plan import Directive, IssueDecision, RepairPlan, ResearchPlan, TaskChange
from app.db import Project, Run, TaskState, Usage, engine
from app.execution import orchestrator
from app.execution.agent import AgentResult
from app.execution.e2b_sandbox import E2BSandbox
from app.execution.sandbox import ExecResult
from study_fixture import TEX, exec_task, make_study, research_plan
from test_judge import RESULTS_LINE, issue, report

REQUEST = httpx2.Request("POST", "https://bedrock-runtime.us-east-1.amazonaws.com/model/m/invoke")
KINDS = ("review", "repair", "execute", "report")


# ── Harness ────────────────────────────────────────────────────────────────


class Unexpected(Exception):
    pass


class ScriptedLLM:
    """Stands in for llm.parse in the judge, planning and blueprint modules: one queue per schema."""

    def __init__(self):
        self.queues: dict[str, list] = defaultdict(list)
        self.calls: list[tuple[str, list]] = []
        self.unexpected: list[str] = []

    def add(self, schema, *items) -> "ScriptedLLM":
        self.queues[schema.__name__].extend(items)
        return self

    async def parse(self, *, model, instructions, messages, schema, reasoning_effort="medium", tools=None,
                    max_tokens=None):
        self.calls.append((schema.__name__, messages))
        queue = self.queues[schema.__name__]
        if not queue:
            self.unexpected.append(schema.__name__)
            raise Unexpected(f"unexpected {schema.__name__} call")
        item = queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        if callable(item):
            item = item(messages)
            if asyncio.iscoroutine(item):
                item = await item
        return item

    def kinds(self) -> list[str]:
        return [k for k, _ in self.calls]

    def text(self, i: int) -> str:
        content = self.calls[i][1][0]["content"]
        return content if isinstance(content, str) else "\n".join(b.get("text", "") for b in content)


class Lab:
    """Fake task agent, verifier and report writer around the real scheduler."""

    def __init__(self, study):
        self.study = study
        self.ran: list[str] = []
        self.prompts: dict[str, list[str]] = defaultdict(list)
        self.fail: set[str] = set()
        self.usage_per_task: dict[str, float] = {}
        self.reports: list[dict] = []
        self.paper = TEX
        self.hang: set[str] = set()
        self.release = asyncio.Event()

    async def agent(self, spec, prompt, ctx, on_event=None):
        tid = ctx.owner
        self.ran.append(tid)
        self.prompts[tid].append(prompt)
        if tid in self.hang:
            await self.release.wait()
        if cost := self.usage_per_task.get(tid):
            with Session(engine) as s:
                s.add(Usage(project_id=ctx.project_id, run_id=llm.current_run.get(), model="m", cost=cost))
                s.commit()
        if tid in self.fail:
            return AgentResult("failed", f"{tid} could not run")
        _, mp, _ = refine._bp(ctx.project_id)
        task = next(t for t in mp["tasks"] if t["id"] == tid)
        stamp = time.time() + len(self.ran)
        for o in task["outputs"]:
            p = ctx.sandbox.path(o["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"{tid} output run {len(self.ran)}\n", encoding="utf-8")
            os.utime(p, (stamp, stamp))
        return AgentResult("success", f"{tid} done", artifacts=[o["path"] for o in task["outputs"]])

    async def verify(self, task, sandbox, policy, report=None, amendments=None, leftovers=None):
        return [{"check": c, "passed": True, "reason": "ok"} for c in task["acceptance_checks"]]

    async def report(self, project_id, h):
        g = report_agent._gather(project_id)
        self.reports.append({"directives": g["directives"], "stage": self.study.project().stage})
        # Each rewrite differs (as a real one would); identical evidence would reuse the last review.
        self.study.write_paper(self.paper.replace("\\section{Conclusion}",
                                                  f"\\section{{Conclusion}}\nRevision {len(self.reports)}."))
        return {"scaffold": {"title": "t", "one_sentence_summary": "s", "hypothesis_verdict": "supported",
                             "verdict_explanation": "", "findings": [], "success_criteria": [], "figures": [],
                             "tables": [], "limitations": [], "deviations": [], "outline": [], "reproducibility": [],
                             "writing_instructions": ""},
                "agent": {"status": "success", "summary": "", "cost": 0.0, "issues": []},
                "files": {"tex": True, "pdf": True, "bib": True},
                "citations": {"used": ["smith2020data"], "unknown": [], "available": 1}, "audit": [],
                "integrity": {"hard": [], "soft": []}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    def build(**kw):
        study = make_study(tmp_path, monkeypatch, refinement=kw.pop("refinement", {"enabled": True}), **kw)
        scripted = ScriptedLLM()
        for mod in (judge, plan_agent, blueprint_agent):
            monkeypatch.setattr(mod, "parse", scripted.parse)
        monkeypatch.setattr(llm, "client", None)  # any direct model call would fail
        monkeypatch.setattr(judge, "RETRY_DELAY", 0)
        monkeypatch.setattr(refine, "WATCH_INTERVAL", 0.01)
        monkeypatch.setattr(refine, "_watchers", {})
        lab = Lab(study)
        monkeypatch.setattr(orchestrator, "run_agent", lab.agent)
        monkeypatch.setattr(orchestrator, "_verify", lab.verify)
        monkeypatch.setattr(report_agent, "run", lab.report)

        async def noop(self, *a, **k):
            return None

        async def install(self, packages):
            return ExecResult(0, "", "")

        monkeypatch.setattr(E2BSandbox, "ensure", noop)
        monkeypatch.setattr(E2BSandbox, "install", install)
        built.append(study)
        return study, scripted, lab

    built: list = []
    yield build
    for s in built:
        s.cleanup()


async def settle(pid: str, timeout: float = 30.0) -> dict:
    """Wait until the loop stops: a final, failed or attention state with no review job running."""
    deadline = time.monotonic() + timeout
    quiet = 0
    while time.monotonic() < deadline:
        st = refine.view(pid)
        busy = any(jobs.is_running(pid, k) for k in KINDS)
        if st.get("status") in (*refine.FINAL, "review_failed", "attention") and not busy:
            quiet += 1
            if quiet >= 5:  # let follow-up callbacks finish
                return st
        else:
            quiet = 0
        await asyncio.sleep(0.02)
    raise AssertionError(f"loop did not settle: {refine.view(pid).get('status')} step {refine.view(pid).get('step')}")


def loop(pid: str, start=None) -> dict:
    async def go():
        await (start() if start else pipeline._after_report(pid))
        return await settle(pid)

    return asyncio.run(go())


def accept() -> JudgeReport:
    return report(verdict="accept")


def blocking(*issues, verdict="major_revision") -> JudgeReport:
    return report(list(issues), verdict=verdict)


def confirm(*refs, severity="MAJOR") -> VerificationReport:
    return VerificationReport(checks=[IssueCheck(ref=r, outcome="confirmed", reason="seen", corrected_severity=severity)
                                      for r in refs])


def fix(issue_id: str, root: str = "execution") -> IssueDecision:
    return IssueDecision(issue_id=issue_id, disposition="fix", root_cause=root, rationale="r")


def repair(decisions, task_changes=(), directives=(), plan_revision="", blueprint_changes="", rerun=(),
           withdraw=()) -> RepairPlan:
    return RepairPlan(summary="s", decisions=list(decisions), plan_revision=plan_revision,
                      blueprint_changes=blueprint_changes, task_changes=list(task_changes),
                      rerun_failed_tasks=list(rerun), report_directives=list(directives),
                      withdraw_directives=list(withdraw))


def stats_issue(ref="I1", severity="MAJOR", **kw):
    return issue(ref, severity, affected=["T3.1", "analysis/stats.csv"], **kw)


def runs(study, kind):
    return study.runs(kind)


# ── Required scenarios ─────────────────────────────────────────────────────


def test_paper_that_passes_its_first_review(env):
    study, llm_, lab = env()
    st = loop(study.pid, lambda: _first(study, llm_.add(JudgeReport, accept())))
    assert st["status"] == "approved" and study.project().stage == "complete"
    assert llm_.kinds() == ["JudgeReport"] and llm_.unexpected == []
    assert lab.ran == [] and lab.reports == [] and runs(study, "repair") == []
    mistakes = judge.review_dir(study.pid, 1) / "mistakes.json"
    assert '"decision": "approved"' in mistakes.read_text(encoding="utf-8")
    assert (judge.review_dir(study.pid) / "REVIEW.md").read_text(encoding="utf-8").startswith("# Scientific review: approved")


async def _first(study, _scripted):
    await pipeline._after_report(study.pid)


def test_localized_analysis_error_reruns_only_the_analysis_and_its_dependents(env):
    study, llm_, lab = env()
    llm_.add(JudgeReport, blocking(stats_issue()), accept())
    llm_.add(VerificationReport, confirm("I1"))
    llm_.add(RepairPlan, repair([fix("R1-01")], task_changes=[TaskChange(
        task_id="T3.1", change="Use a paired t-test across all five seeds (R1-01).", issue_ids=["R1-01"])]))
    st = loop(study.pid)
    assert st["status"] == "approved", st
    assert lab.ran == ["T3.1", "T4.1"]
    assert llm_.kinds() == ["JudgeReport", "VerificationReport", "RepairPlan", "JudgeReport"]
    states = study.states()
    assert all(states[t].attempts == 1 and states[t].status == "done" for t in ("T1.1", "T2.1", "T2.2"))
    assert "Use a paired t-test across all five seeds" in lab.prompts["T3.1"][0]
    assert "R1-01" not in lab.prompts["T3.1"][0]  # review ids never reach the agents
    assert len(runs(study, "plan")) == 1 and len(runs(study, "blueprint")) == 1  # no re-planning
    it = st["iterations"][0]
    assert it["level"] == "execution" and it["rerun_tasks"] == ["T3.1", "T4.1"] and it["execute_run_id"]


def test_fatal_design_flaw_replans_and_runs_only_the_new_control(env):
    study, llm_, lab = env()
    flaw = issue("I1", "FATAL", category="experimental_design", origin="plan", evidence=[],
                 absence_terms=["random-label control"], affected=["T3.1"], invalidates=["analysis/stats.csv"],
                 title="No random-label control")
    llm_.add(JudgeReport, blocking(flaw, verdict="reject"), accept())
    llm_.add(VerificationReport, confirm("I1", severity="FATAL"))
    llm_.add(RepairPlan, repair([fix("R1-01", "plan")], plan_revision="Add a random-label control condition.",
                                blueprint_changes="Add task T2.3 (random-label control) and compare against it in T3.1."))
    revised = research_plan()
    revised["research_question"] = "An easier question?"  # must be restored in code
    revised["validation_strategy"] = "5 seeds, paired t-test, random-label control"
    revised["phases"][1]["tasks"].append({**revised["phases"][1]["tasks"][0], "id": "T2.3", "title": "Control"})
    llm_.add(ResearchPlan, ResearchPlan.model_validate(revised))
    control = exec_task("T2.3", "Random-label control", ["T1.1"], [("data/raw.csv", "task:T1.1")],
                        ["results/control.csv"])
    analysis = exec_task("T3.1", "Statistical analysis", ["T2.1", "T2.3"],
                         [("results/runs.csv", "task:T2.1"), ("results/control.csv", "task:T2.3")],
                         ["analysis/stats.csv", "src/stats.py"])
    llm_.add(BlueprintDelta, BlueprintDelta(add_tasks=[ExecTask.model_validate(control)],
                                            replace_tasks=[ExecTask.model_validate(analysis)], remove_task_ids=[],
                                            add_agents=[], add_datasets=[], add_python_packages=[],
                                            notes=["Control added after review"]))
    old_bp = study.project().blueprint["run_id"]
    st = loop(study.pid)
    assert st["status"] == "approved", st
    assert lab.ran == ["T2.3", "T3.1", "T4.1"]  # data, experiment and baseline are reused
    project = study.project()
    assert project.plan["research_question"] == research_plan()["research_question"]
    assert project.blueprint["run_id"] != old_bp
    it = st["iterations"][0]
    assert it["level"] == "plan" and it["objective_changes"] == ["validation_strategy"]
    assert sorted(it["carried_over"]) == ["T1.1", "T2.1", "T2.2"]
    new_bp = next(r for r in runs(study, "blueprint") if r.id == project.blueprint["run_id"])
    assert new_bp.result["warnings"] == [] and new_bp.result["budget"]["llm_usd"] == 15.0
    assert [d["id"] for d in new_bp.result["master_plan"]["datasets"]] == ["D1"]
    assert new_bp.result["master_plan"]["datasets"][0]["verified"] is True  # untouched entries kept as they were
    carried = study.states()["T2.1"]
    assert carried.summary.startswith("T2.1 done") and carried.attempts == 1 and "carried over" in carried.note
    assert runs(study, "literature") == [] and runs(study, "gaps") == []
    assert (study.exports / study.pid / "master_plan.json").is_file()


def test_inconsistent_figure_reruns_only_the_figure_task(env):
    study, llm_, lab = env()
    now = time.time()
    os.utime(study.root / "scripts" / "plot.py", (now, now))  # code changed after the figure was drawn
    fig = issue("I1", "MAJOR", category="figures_tables", origin="execution", source="figure:figures/main.png",
                quote="", locator="", affected=["T4.1", "figures/main.png"], title="Figure is stale")
    llm_.add(JudgeReport, blocking(fig), accept())
    llm_.add(VerificationReport, confirm("I1"))
    llm_.add(RepairPlan, repair([fix("R1-01")], task_changes=[TaskChange(
        task_id="T4.1", change="Regenerate the figure from analysis/stats.csv.", issue_ids=["R1-01"])]))
    st = loop(study.pid)
    assert st["status"] == "approved" and lab.ran == ["T4.1"]
    assert "older than code that references it" in llm_.text(0)


def test_missing_figure_is_repaired_by_rebuilding_the_paper_without_any_model_call(env):
    study, llm_, lab = env()
    study.write_paper(TEX.replace("\\label{fig:main}", "\\label{fig:main}\n\\includegraphics{../figures/gone.png}"),
                      when=time.time() - 300)
    llm_.add(JudgeReport, accept())
    st = loop(study.pid)
    assert st["status"] == "approved"
    assert llm_.kinds() == ["JudgeReport"]  # the gate failure needed no judge or planner call
    assert st["iterations"][0]["decision"] == "repair_gates" and st["iterations"][0]["level"] == "report"
    assert "Include only figure files that exist" in lab.reports[0]["directives"]


def test_two_iterations_with_different_issues_and_accumulated_directives(env):
    study, llm_, lab = env()
    misread = issue("I1", "MAJOR", category="literature", origin="literature", locator="L7",
                    quote="Prior work studied robust testing", affected=["literature:smith2020data"],
                    title="Citation misread")
    llm_.add(JudgeReport, blocking(stats_issue()), blocking(misread), accept())
    llm_.add(VerificationReport, confirm("I1"), confirm("I1"))
    llm_.add(RepairPlan,
             repair([fix("R1-01")], task_changes=[TaskChange(task_id="T3.1", change="Paired test.", issue_ids=["R1-01"])],
                    directives=[Directive(issue_ids=["R1-01"], text="State the number of seeds per condition.")]),
             repair([fix("R2-01", "report")], directives=[Directive(
                 issue_ids=["R2-01"], text="Describe smith2020data accurately: it shows five seeds suffice.")]))
    st = loop(study.pid)
    assert st["status"] == "approved"
    assert lab.ran == ["T3.1", "T4.1"]  # the second repair touched only the manuscript
    assert len(runs(study, "execute")) == 2  # the study's original run plus one repair run
    assert st["iterations"][1]["level"] == "report"
    second = lab.reports[1]["directives"]
    assert "State the number of seeds per condition." in second  # round-1 directive kept
    assert "What the cited papers actually report" in second and "five seeds" in second
    tracks = st["tracks"]
    assert {t["status"] for t in tracks.values()} == {"resolved"} and len(tracks) == 2


def test_resurfaced_issue_cannot_be_disputed_and_history_reaches_the_planner(env):
    study, llm_, lab = env()
    cite = issue("I1", "MAJOR", category="literature", origin="report", locator="L7",
                 quote="Prior work studied robust testing", affected=["Introduction"], title="Overclaimed prior work")
    llm_.add(JudgeReport, blocking(stats_issue()), blocking(cite), blocking(stats_issue()), accept())
    llm_.add(VerificationReport, confirm("I1"), confirm("I1"), confirm("I1"))
    change = [TaskChange(task_id="T3.1", change="Paired test.", issue_ids=["R1-01"])]
    llm_.add(RepairPlan,
             repair([fix("R1-01")], task_changes=change),
             repair([fix("R2-01", "report")], directives=[Directive(issue_ids=["R2-01"], text="Tone it down.")]),
             repair([IssueDecision(issue_id="R3-01", disposition="dispute", root_cause="execution",
                                   rationale="The test is fine.")]),
             repair([fix("R3-01")], task_changes=[TaskChange(task_id="T3.1", change="Use a permutation test.",
                                                             issue_ids=["R3-01"])]))
    st = loop(study.pid)
    assert st["status"] == "approved"
    review3 = st["iterations"][2]["issues"][0]
    assert review3["tracking"]["status"] == "resurfaced" and review3["track_id"] == st["iterations"][0]["issues"][0]["track_id"]
    planner = [i for i, k in enumerate(llm_.kinds()) if k == "RepairPlan"]
    third = llm_.text(planner[2])
    assert "resurfaced" in third and "ISSUE HISTORY" in third and "re-run T3.1" in third
    assert "raised again after an earlier dispute or fix" in llm_.text(planner[3])  # the dispute was rejected


def test_persistent_fatal_issue_stops_honestly(env):
    study, llm_, lab = env()
    fatal = stats_issue(severity="FATAL")
    llm_.add(JudgeReport, *[blocking(fatal, verdict="reject") for _ in range(3)])
    llm_.add(VerificationReport, *[confirm("I1", severity="FATAL") for _ in range(3)])
    llm_.add(RepairPlan, *[repair([fix(f"R{n}-01")], task_changes=[TaskChange(
        task_id="T3.1", change=f"Attempt {n}.", issue_ids=[f"R{n}-01"])]) for n in (1, 2)])
    st = loop(study.pid)
    assert st["status"] == "unresolved" and "persisted" in st["outcome"]["reason"]
    assert st["outcome"]["unresolved"][0]["severity"] == "FATAL"
    assert study.project().stage == "complete" and llm_.unexpected == []


def test_malformed_judge_output_fails_the_review_and_resume_recovers(env):
    study, llm_, lab = env()
    bad = RuntimeError("Model returned invalid structured output: 1 validation error")
    llm_.add(JudgeReport, bad, bad)
    st = loop(study.pid)
    assert st["status"] == "review_failed" and study.project().stage == "reviewing"
    assert "did not return a valid review" in st["attention"]
    llm_.add(JudgeReport, accept())

    async def again():
        refine.resume(study.pid)

    st = loop(study.pid, again)
    assert st["status"] == "approved"


@pytest.mark.parametrize("failures,status", [(1, "approved"), (2, "review_failed")])
def test_bedrock_failures(env, failures, status):
    study, llm_, lab = env()
    llm_.add(JudgeReport, *[anthropic.APIConnectionError(request=REQUEST) for _ in range(failures)], accept())
    st = loop(study.pid)
    assert st["status"] == status
    if status == "review_failed":
        assert "temporarily unavailable" in st["attention"]


def test_permanent_provider_error_fails_the_review_instead_of_sticking_at_reviewing(env):
    """A non-transient model-service error (e.g. a 4xx) from the judge call must end the review with
    an explicit, resumable status rather than leaving Project.review.status stuck at
    "reviewing" forever with its background job silently dead."""
    study, llm_, lab = env()
    bad_request = anthropic.BadRequestError(
        "bad request", response=httpx2.Response(400, request=REQUEST), body={"message": "bad request"})
    llm_.add(JudgeReport, bad_request)
    st = loop(study.pid)
    assert st["status"] == "review_failed"
    # The user is told the review failed; the provider's own wording and the exception class are
    # logged, not shown (safe_error).
    assert "The review could not be completed." in st["attention"]
    assert not {"BadRequestError", "bad request"} & set(st["attention"].split())
    assert not jobs.is_running(study.pid, "review")


def test_failed_repair_task_needs_attention_then_resumes(env):
    study, llm_, lab = env()
    llm_.add(JudgeReport, blocking(stats_issue()), accept())
    llm_.add(VerificationReport, confirm("I1"))
    llm_.add(RepairPlan, repair([fix("R1-01")], task_changes=[TaskChange(task_id="T3.1", change="Paired test.",
                                                                       issue_ids=["R1-01"])]))
    lab.fail = {"T3.1"}
    st = loop(study.pid)
    assert st["status"] == "attention" and "T3.1 [failed]" in st["attention"]
    lab.fail = set()

    async def again():
        refine.resume(study.pid)

    st = loop(study.pid, again)
    assert st["status"] == "approved" and lab.ran[-2:] == ["T3.1", "T4.1"]


def test_interrupted_repair_resumes_without_paying_twice_or_duplicating_work(env):
    study, llm_, lab = env()
    flaw = issue("I1", "FATAL", category="controls_confounds", origin="blueprint", affected=["T3.1"],
                 title="Missing control task")
    llm_.add(JudgeReport, blocking(flaw, verdict="reject"), accept())
    llm_.add(VerificationReport, confirm("I1", severity="FATAL"))
    llm_.add(RepairPlan, repair([fix("R1-01", "blueprint")], blueprint_changes="Add a control task T2.3."))
    hang = asyncio.Event()

    async def stuck(messages):
        await hang.wait()

    control = exec_task("T2.3", "Control", ["T1.1"], [("data/raw.csv", "task:T1.1")], ["results/control.csv"])
    delta = BlueprintDelta(add_tasks=[ExecTask.model_validate(control)], replace_tasks=[], remove_task_ids=[],
                           add_agents=[], add_datasets=[], add_python_packages=[], notes=[])
    llm_.add(BlueprintDelta, stuck, delta)

    async def interrupt():
        await pipeline._after_report(study.pid)
        for _ in range(500):
            if llm_.kinds().count("BlueprintDelta") == 1:
                break
            await asyncio.sleep(0.02)
        assert jobs.cancel(study.pid, "repair")  # e.g. a restart in the middle of the repair job
        await asyncio.sleep(0.1)

    async def go():
        await interrupt()
        st = refine.view(study.pid)
        assert st["status"] == "attention" and st["step"] == "repair"
        refine.resume(study.pid)
        return await settle(study.pid)

    st = asyncio.run(go())
    assert st["status"] == "approved"
    assert llm_.kinds().count("RepairPlan") == 1  # the saved repair plan was reused
    assert lab.ran == ["T2.3"]
    with Session(engine) as s:
        rows = s.exec(select(TaskState).where(TaskState.blueprint_run_id == study.project().blueprint["run_id"])).all()
    assert sorted(r.task_id for r in rows) == ["T1.1", "T2.1", "T2.2", "T2.3", "T3.1", "T4.1"]


def test_round_limit_ends_unresolved(env):
    study, llm_, lab = env(refinement={"enabled": True, "max_rounds": 1})
    llm_.add(JudgeReport, blocking(stats_issue()), blocking(stats_issue()))
    llm_.add(VerificationReport, confirm("I1"), confirm("I1"))
    llm_.add(RepairPlan, repair([fix("R1-01")], task_changes=[TaskChange(task_id="T3.1", change="Paired test.",
                                                                       issue_ids=["R1-01"])]))
    st = loop(study.pid)
    assert st["status"] == "unresolved" and "after 1 repair rounds" in st["outcome"]["reason"]
    assert st["outcome"]["unresolved"] and study.project().stage == "complete"


def test_budget_spent_by_the_review_ends_before_any_repair(env):
    study, llm_, lab = env(refinement={"enabled": True, "max_usd": 1.0})

    def expensive(messages):
        with Session(engine) as s:
            s.add(Usage(project_id=study.pid, model="m", cost=5.0))
            s.commit()
        return blocking(stats_issue())

    llm_.add(JudgeReport, expensive)
    llm_.add(VerificationReport, confirm("I1"))
    st = loop(study.pid)
    assert st["status"] == "budget_exhausted" and runs(study, "repair") == []


def test_budget_reached_during_repair_execution_stops_and_restores_the_budget(env):
    study, llm_, lab = env(refinement={"enabled": True, "max_usd": 2.0})
    llm_.add(JudgeReport, blocking(stats_issue()))
    llm_.add(VerificationReport, confirm("I1"))
    llm_.add(RepairPlan, repair([fix("R1-01")], task_changes=[TaskChange(task_id="T3.1", change="Paired test.",
                                                                       issue_ids=["R1-01"])]))
    lab.usage_per_task = {"T3.1": 50.0}
    st = loop(study.pid)
    assert st["status"] == "budget_exhausted" and "repair execution" in st["outcome"]["reason"]
    assert lab.ran == ["T3.1"]  # T4.1 never started
    project = study.project()
    assert project.stage == "complete" and project.settings["budget"]["llm_usd"] == 15.0
    assert "gpu_budget_usd" not in project.settings  # the GPU cap is restored too


def test_escalated_issue_is_disclosed_and_flagged_for_a_human(env):
    study, llm_, lab = env()
    ill = issue("I1", "FATAL", category="research_question", origin="plan", title="Question is ill-posed")
    llm_.add(JudgeReport, blocking(ill, verdict="reject"), accept())
    llm_.add(VerificationReport, confirm("I1", severity="FATAL"))
    llm_.add(RepairPlan, repair([IssueDecision(issue_id="R1-01", disposition="escalate", root_cause="plan",
                                               rationale="Needs the user")],
                                directives=[Directive(issue_ids=["R1-01"], text="State that the question as posed "
                                                                                 "cannot be answered by this design.")]))
    st = loop(study.pid)
    assert st["status"] == "approved" and lab.ran == []
    assert st["outcome"]["needs_human"] and "cannot be answered" in lab.reports[0]["directives"]


def test_dispute_only_plan_ends_unresolved(env):
    study, llm_, lab = env()
    llm_.add(JudgeReport, blocking(stats_issue()))
    llm_.add(VerificationReport, confirm("I1"))
    llm_.add(RepairPlan, repair([IssueDecision(issue_id="R1-01", disposition="dispute", root_cause="execution",
                                               rationale="The reviewer misread the table.")]))
    st = loop(study.pid)
    assert st["status"] == "unresolved" and "disputes every" in st["outcome"]["reason"]


def test_refinement_disabled_keeps_the_plain_pipeline(env):
    study, llm_, lab = env(refinement=None)
    asyncio.run(pipeline._after_report(study.pid))
    assert study.project().stage == "complete" and study.project().review is None
    assert llm_.calls == [] and runs(study, "review") == []


def test_report_after_a_finished_review_is_marked_stale_not_rereviewed(env):
    study, llm_, lab = env()
    llm_.add(JudgeReport, accept())
    loop(study.pid)

    async def manual_report():
        pipeline.start_report(study.pid)
        for _ in range(200):
            if not jobs.is_running(study.pid, "report"):
                break
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.1)

    asyncio.run(manual_report())
    st = refine.state(study.pid)
    assert st["status"] == "approved" and st["stale"] is True and len(llm_.calls) == 1
    assert study.project().stage == "complete"


def test_guided_project_repairs_without_stopping_at_checkpoints(env):
    study, llm_, lab = env(autonomous=False)
    with Session(engine) as s:  # a human checkpoint right after the analysis task
        bp = s.get(Run, study.bp_run_id)
        bp.result = {**bp.result, "master_plan": {**bp.result["master_plan"],
                                                  "checkpoints": [{"after_task": "T3.1", "reason": "check"}]}}
        s.add(bp)
        s.commit()
    llm_.add(JudgeReport, blocking(stats_issue()), accept())
    llm_.add(VerificationReport, confirm("I1"))
    llm_.add(RepairPlan, repair([fix("R1-01")], task_changes=[TaskChange(task_id="T3.1", change="Paired test.",
                                                                       issue_ids=["R1-01"])]))
    st = loop(study.pid)
    assert st["status"] == "approved" and lab.ran == ["T3.1", "T4.1"]


def test_unfinished_tasks_not_selected_are_skipped_not_silently_rerun(env):
    study, llm_, lab = env()
    with Session(engine) as s:
        for st in s.exec(select(TaskState).where(TaskState.blueprint_run_id == study.bp_run_id)):
            if st.task_id == "T2.2":
                st.status, st.note = "failed", "download refused"
                s.add(st)
        s.commit()
    llm_.add(JudgeReport, blocking(stats_issue()), accept())
    llm_.add(VerificationReport, confirm("I1"))
    llm_.add(RepairPlan, repair([fix("R1-01")], task_changes=[TaskChange(task_id="T3.1", change="Paired test.",
                                                                       issue_ids=["R1-01"])]))
    st = loop(study.pid)
    assert st["status"] == "approved" and "T2.2" not in lab.ran
    t22 = study.states()["T2.2"]
    assert t22.status == "skipped" and "download refused" in t22.note


def test_resume_after_a_cancelled_repair_execution_reruns_the_task(env):
    study, llm_, lab = env()
    fig = issue("I1", "MAJOR", category="figures_tables", origin="execution", affected=["T4.1"], title="Bad figure")
    llm_.add(JudgeReport, blocking(fig), accept())
    llm_.add(VerificationReport, confirm("I1"))
    llm_.add(RepairPlan, repair([fix("R1-01")], task_changes=[TaskChange(task_id="T4.1", change="Redraw it.",
                                                                       issue_ids=["R1-01"])]))
    lab.hang = {"T4.1"}

    async def cancel_midway():
        await pipeline._after_report(study.pid)
        for _ in range(500):
            if "T4.1" in lab.ran:
                break
            await asyncio.sleep(0.02)
        ctl = orchestrator.control(study.pid)
        ctl.cancelled = True  # the user cancels the repair execution
        ctl.resume()
        return await settle(study.pid)

    st = asyncio.run(cancel_midway())
    assert st["status"] == "attention" and study.states()["T4.1"].status == "cancelled"
    lab.hang = set()

    async def again():
        refine.resume(study.pid)

    st = loop(study.pid, again)
    assert st["status"] == "approved" and lab.ran.count("T4.1") == 2  # re-run, not straight to the report


def test_planner_can_revive_a_skipped_task(env):
    study, llm_, lab = env()
    with Session(engine) as s:
        for st in s.exec(select(TaskState).where(TaskState.blueprint_run_id == study.bp_run_id,
                                                 TaskState.task_id == "T2.2")):
            st.status, st.note = "skipped", "skipped by the user"
            s.add(st)
        s.commit()
    llm_.add(JudgeReport, blocking(stats_issue()), accept())
    llm_.add(VerificationReport, confirm("I1"))
    llm_.add(RepairPlan, repair([fix("R1-01")], rerun=["T2.2"], task_changes=[TaskChange(
        task_id="T3.1", change="Compare against the baseline.", issue_ids=["R1-01"])]))
    st = loop(study.pid)
    assert st["status"] == "approved" and "T2.2" in lab.ran and study.states()["T2.2"].status == "done"


def test_report_only_gate_repair_leaves_unfinished_tasks_alone(env):
    study, llm_, lab = env()
    with Session(engine) as s:
        for st in s.exec(select(TaskState).where(TaskState.blueprint_run_id == study.bp_run_id,
                                                 TaskState.task_id == "T2.2")):
            st.status, st.note = "human", "Needs credential NCBI_API_KEY"
            s.add(st)
        s.commit()
    (study.root / "paper" / "paper.pdf").unlink()  # H1: not compiled
    llm_.add(JudgeReport, accept())
    st = loop(study.pid)
    assert st["status"] == "approved" and study.states()["T2.2"].status == "human"


def test_research_files_changed_by_the_report_that_no_task_regenerates_stop_the_loop(env):
    study, llm_, lab = env()
    with Session(engine) as s:
        rep = s.exec(select(Run).where(Run.project_id == study.pid, Run.kind == "report")).first()
        rep.result = {**rep.result, "integrity": {"hard": ["notes/hand_edited.txt"], "soft": []}}
        s.add(rep)
        s.commit()
    st = loop(study.pid)
    assert st["status"] == "unresolved" and "no task regenerates" in st["outcome"]["reason"]
    assert llm_.calls == []


def test_a_new_session_restores_budgets_capped_by_an_earlier_one(env):
    study, llm_, lab = env()
    study.update(settings={**study.project().settings, "budget": {"llm_usd": 3.0}, "gpu_budget_usd": 1.0},
                 review={"status": "attention", "budget_override": {"llm": {"original": 15.0, "set": 3.0},
                                                                     "gpu": {"original": None, "set": 1.0}}})
    refine.begin_session(study.pid)
    cfg = study.project().settings
    assert cfg["budget"]["llm_usd"] == 15.0 and "gpu_budget_usd" not in cfg


# ── Units ──────────────────────────────────────────────────────────────────


def _st(**kw) -> dict:
    return {"max_rounds": 3, "max_usd": 12.0, "session_first_iteration": 1, "iterations": [], "tracks": {}, **kw}


def _m(*issues, verdict="major_revision", valid=True, judged=True) -> dict:
    return {"valid": valid, "judged": judged, "verdict": verdict, "issues": list(issues)}


B = {"id": "R1-01", "severity": "MAJOR", "blocking": True}
F = {"id": "R1-02", "severity": "FATAL", "blocking": True}


@pytest.mark.parametrize("st,mistakes,spent,decision", [
    (_st(), _m(verdict="accept"), 0, "approved"),
    (_st(), _m(verdict="minor_revision"), 0, "approved"),
    (_st(), _m(verdict="reject"), 0, "unresolved"),
    (_st(), _m(B), 0, "repair"),
    (_st(), _m(B), 20.0, "budget_exhausted"),
    (_st(), {"valid": False, "error": "x"}, 0, "review_failed"),
    (_st(), {"valid": False, "budget_limit": True}, 0, "budget_exhausted"),
    (_st(), _m({"gate": "H1", "blocking": True}, judged=False), 0, "repair_gates"),
    (_st(iterations=[{"n": 1, "decision": "repair", "judged": True, "blocking": {"MAJOR": 1}}] * 3), _m(B), 0,
     "unresolved"),
    (_st(iterations=[{"n": 1, "decision": "repair", "judged": True, "blocking": {"MAJOR": 1}},
                     {"n": 2, "decision": "repair", "judged": True, "blocking": {"MAJOR": 1}}]), _m(B), 0, "unresolved"),
    (_st(iterations=[{"n": 1, "decision": "repair", "judged": True, "blocking": {"FATAL": 1}},
                     {"n": 2, "decision": "repair", "judged": True, "blocking": {"MAJOR": 2}}]), _m(B), 0, "repair"),
    (_st(tracks={"T-001": {"severity": "FATAL", "status": "open", "open_streak": 3, "title": "x"}}), _m(F), 0,
     "unresolved"),
    (_st(session_first_iteration=4, iterations=[{"n": 1, "decision": "repair"}] * 3), _m(B), 0, "repair"),
    # A failed verification never approves, even if nothing ended up blocking.
    (_st(), {**_m({"id": "R1-01", "severity": "MAJOR", "blocking": False, "open_concern": True},
                  verdict="minor_revision"), "verification": "failed"}, 0, "review_failed"),
    (_st(), {**_m(verdict="accept"), "verdict_consistent": False}, 0, "unresolved"),
])
def test_decide_table(st, mistakes, spent, decision):
    assert refine.decide(st, mistakes, spent)[0] == decision


def test_repair_context_shows_the_round_about_to_run_not_one_ahead(tmp_path, monkeypatch):
    """By the time repair_context runs, this review's own "repair" decision is already
    appended to st["iterations"] (_review_job records it before dispatching to repair), so
    `rounds` already counts the round about to happen — the message must not add another 1."""
    study = make_study(tmp_path, monkeypatch)
    st = _st(max_rounds=3, session_first_iteration=1, started_at=datetime.now(timezone.utc).isoformat(),
             iterations=[{"n": 1, "decision": "repair"}], preregistration={}, directives={})
    mistakes = {"iteration": 1, "verdict": "major_revision", "summary": "s", "issues": []}
    context = refine.repair_context(study.pid, st, mistakes)
    assert "repair round 1 of 3" in context
    study.cleanup()


def test_issue_tracking_matches_resolves_and_labels():
    a = {"id": "R1-01", "severity": "MAJOR", "category": "statistics", "title": "Paired t-test on one seed pair",
         "affected": ["T3.1"], "invalidates": [], "blocking": True}
    tracks = refine.track_issues({}, [a], 1, set())
    assert a["track_id"] == "T-001" and a["tracking"]["status"] == "new"
    tracks = refine.track_issues(tracks, [], 2, set())
    assert tracks["T-001"]["status"] == "resolved"
    b = {**a, "id": "R3-01", "title": "Wrong test for paired seeds", "affected": ["t3.1"]}
    tracks = refine.track_issues(tracks, [b], 3, set())
    assert b["track_id"] == "T-001" and b["tracking"]["status"] == "resurfaced"
    c = {**a, "id": "R4-01", "category": "figures_tables", "title": "Figure axis", "affected": ["figures/main.png"]}
    tracks = refine.track_issues(tracks, [b | {"id": "R4-02"}, c], 4, {"figures/main.png"})
    assert c["tracking"]["status"] == "regression" and tracks["T-001"]["open_streak"] == 2


def test_root_cause_cannot_be_later_than_the_origin():
    mistakes = {"issues": [{"id": "R1-01", "origin": "analysis", "blocking": True, "track_id": None}]}
    mp = {"tasks": [{"id": "T3.1"}]}
    rp = repair([fix("R1-01", "report")], directives=[Directive(issue_ids=["R1-01"], text="reword")])
    errors = refine.validate_repair(rp, mistakes, {"tracks": {}}, mp, {})
    assert any("cannot be fixed at the later report stage" in e for e in errors)
    ok = repair([fix("R1-01")], task_changes=[TaskChange(task_id="T3.1", change="c", issue_ids=["R1-01"])])
    assert refine.validate_repair(ok, mistakes, {"tracks": {}}, mp, {}) == []
    missing = repair([fix("R1-01")], task_changes=[TaskChange(task_id="T9", change="c", issue_ids=["R1-01"])])
    assert any("unknown task T9" in e for e in refine.validate_repair(missing, mistakes, {"tracks": {}}, mp, {}))


def test_task_hash_ignores_estimates_and_url_checks():
    from study_fixture import master_plan

    mp = master_plan()
    t = mp["tasks"][1]
    base = refine.task_hash(t, mp)
    mp2 = {**mp, "datasets": [{**mp["datasets"][0], "verified": False}]}
    t2 = {**t, "max_cost_usd": 9.0, "retries": 3, "compute": {**t["compute"], "est_minutes": 99}}
    assert refine.task_hash(t2, mp2) == base
    assert refine.task_hash({**t, "steps": ["different"]}, mp) != base
    new = {**mp, "tasks": [*mp["tasks"][:3], {**mp["tasks"][3], "steps": ["new"]}, mp["tasks"][4]]}
    assert refine.invalidated_tasks(mp, new) == {"T3.1", "T4.1"}


def test_after_execution_does_not_report_unfinished_guided_runs(env):
    study, llm_, lab = env(autonomous=False, refinement=None)
    started = []
    original = pipeline.start_report

    def fake_start_report(pid):
        started.append(pid)
        return Run(id="fake-report", project_id=pid, kind="report")

    pipeline.start_report = fake_start_report
    try:
        study.update(stage="executed")
        asyncio.run(pipeline._after_execution(study.pid))
        assert started == []  # guided and not repairing: the user decides
        study.update(review={"status": "repairing", "step": "execute", "iterations": [], "iteration": 1})
        asyncio.run(pipeline._after_execution(study.pid))
        assert started == [study.pid]
    finally:
        pipeline.start_report = original


def _cut_off(thinking_only: bool = False) -> llm.OutputLimitReached:
    return llm.OutputLimitReached("Model returned no structured output (stop reason: max_tokens): the answer was "
                                  "cut off by the output limit (64,000 output tokens)", thinking_only=thinking_only)


def test_judge_output_limit_is_recovered_by_one_fresh_attempt(env):
    study, llm_, lab = env()
    llm_.add(JudgeReport, _cut_off(thinking_only=True), accept())
    st = loop(study.pid)
    assert st["status"] == "approved" and llm_.kinds().count("JudgeReport") == 2


def test_exhausted_judge_output_fails_the_review_explicitly_and_resume_recovers(env):
    study, llm_, lab = env()
    llm_.add(JudgeReport, _cut_off(thinking_only=True), _cut_off())
    st = loop(study.pid)
    assert st["status"] == "review_failed" and study.project().stage == "reviewing"
    assert "did not return a valid review" in st["attention"] and "max_tokens" in st["attention"]
    assert not jobs.is_running(study.pid, "review")
    llm_.add(JudgeReport, accept())

    async def again():
        refine.resume(study.pid)

    st = loop(study.pid, again)
    assert st["status"] == "approved"


def test_a_judge_stream_interrupted_twice_fails_the_review_as_model_unavailable(env):
    study, llm_, lab = env()
    broken = llm.StreamInterrupted(httpx2.ReadError("connection reset", request=REQUEST))
    llm_.add(JudgeReport, broken, broken)
    st = loop(study.pid)
    assert st["status"] == "review_failed" and "temporarily unavailable" in st["attention"]
    assert "StreamInterrupted" not in st["attention"]
