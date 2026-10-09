"""A small, complete finished study for the review and refinement tests (offline).

Five blueprint tasks (data → experiment → analysis → figures, plus an independent baseline),
a plan, task states, a report run, a workspace with a compiled paper, figures, result files and
code, and two papers in the literature. Every source the judge must never see carries a
SENTINEL string, so independence can be asserted on the request itself.
"""

import struct
import time
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlmodel import Session, select

from app import llm
from app.agents import blueprint as blueprint_agent
from app.agents import plan as plan_agent
from app.agents.plan import ResearchPlan
from app.db import Message, Paper, Project, ProjectPaper, Run, TaskState, Usage, engine
from app.execution import e2b_sandbox, orchestrator, sandbox
from app.sources.common import norm_title

SENTINELS = ("SENTINEL_TASK_SUMMARY", "SENTINEL_VERIFIER", "SENTINEL_SCAFFOLD", "SENTINEL_TEAM_NOTES",
             "SENTINEL_PREVIOUS_MISTAKES", "SENTINEL_REPAIR_PLAN", "SENTINEL_DIRECTIVE", "SENTINEL_AUDIT")

TOOLS = ["run_python", "write_file", "read_file", "list_files", "report_result"]


def png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + \
        chunk(b"IEND", b"")


def exec_task(tid: str, title: str, deps: list[str], inputs: list[tuple[str, str]], outputs: list[str]) -> dict:
    return {
        "id": tid, "title": title, "agent": "A1", "objective": f"{title}.", "steps": [f"Do {title.lower()}"],
        "inputs": [{"path": p, "source": s} for p, s in inputs],
        "outputs": [{"path": p, "format": Path(p).suffix.lstrip(".") or "dir", "description": f"{p} output"}
                    for p in outputs],
        "acceptance_checks": [f"{outputs[0]} exists"], "depends_on": deps, "tools": TOOLS, "resources": [],
        "compute": {"kind": "cpu", "est_minutes": 5, "timeout_minutes": 15}, "max_cost_usd": 0.5, "retries": 1,
        "human_required": False,
    }


def master_plan() -> dict:
    return {
        "title": "Seed robustness study", "summary": "Agents run the study.", "python_packages": [],
        "system_requirements": [],
        "agents": [{"id": "A1", "name": "Scientist", "model_tier": "standard", "tools": TOOLS,
                    "instructions": "Do careful science."}],
        "datasets": [{"id": "D1", "name": "Bench", "url": "https://example.org/bench.csv", "access_method": "download",
                      "format": "csv", "license": "CC-BY", "notes": "", "verified": True}],
        "tasks": [
            exec_task("T1.1", "Download data", [], [("bench.csv", "dataset:D1")], ["data/raw.csv"]),
            exec_task("T2.1", "Run experiment", ["T1.1"], [("data/raw.csv", "task:T1.1")], ["results/runs.csv"]),
            exec_task("T2.2", "Independent baseline", ["T1.1"], [("data/raw.csv", "task:T1.1")],
                      ["results/baseline.csv"]),
            exec_task("T3.1", "Statistical analysis", ["T2.1"], [("results/runs.csv", "task:T2.1")],
                      ["analysis/stats.csv", "src/stats.py"]),
            exec_task("T4.1", "Figures and summary", ["T3.1"], [("analysis/stats.csv", "task:T3.1")],
                      ["figures/main.png", "results/SUMMARY.md", "scripts/plot.py"]),
        ],
        "checkpoints": [{"after_task": "T1.1", "reason": "check the data"}], "llm_usd_estimate": 2.0,
        "compute_hours_estimate": 0.2, "execution_notes": [],
    }


def research_plan() -> dict:
    task = lambda tid, title, kind, deps: {  # noqa: E731
        "id": tid, "title": title, "description": f"{title}.", "kind": kind, "inputs": [], "outputs": [f"{tid}.out"],
        "depends_on": deps, "effort": "S", "tools_hint": ["pandas"]}
    plan = {
        "title": "Seed robustness", "research_question": "Does method M beat baseline B across seeds?",
        "hypothesis": "M improves accuracy over B by at least 2 points.",
        "null_hypothesis": "M and B do not differ.", "objectives": ["Compare M and B"],
        "background": "Prior work [0].", "study_type": "computational",
        "phases": [{"id": "P1", "name": "Data", "goal": "g", "tasks": [task("T1.1", "Download data", "data_acquisition", [])]},
                   {"id": "P2", "name": "Experiments", "goal": "g", "tasks": [
                       task("T2.1", "Run experiment", "experiment", ["T1.1"]),
                       task("T2.2", "Independent baseline", "experiment", ["T1.1"])]},
                   {"id": "P3", "name": "Analysis", "goal": "g", "tasks": [
                       task("T3.1", "Statistical analysis", "analysis", ["T2.1"]),
                       task("T4.1", "Figures and summary", "analysis", ["T3.1"])]}],
        "datasets": [{"name": "Bench", "description": "d", "source": "https://example.org", "access": "public",
                      "role": "main"}],
        "methods": [{"name": "M", "purpose": "candidate"}], "baselines": ["B"],
        "metrics": [{"name": "accuracy", "definition": "share correct", "success_threshold": "+2 points"}],
        "validation_strategy": "5 seeds, paired t-test", "success_criteria": ["M beats B with p<0.05"],
        "compute_estimate": "1 CPU hour", "duration_estimate": "1 h", "risks": [], "deliverables": ["paper"],
        "open_questions": [],
    }
    ResearchPlan.model_validate(plan)
    return plan


TEX = r"""\documentclass[11pt]{article}
\usepackage{graphicx}
\begin{document}
\title{Seed robustness of M}
\maketitle
\section{Introduction}
Prior work studied robust testing \citep{smith2020data}.
\section{Methods}
We ran 5 seeds per condition and used a paired t-test.
\section{Results}
Method M reached an accuracy of 0.912 versus 0.874 for B (p = 0.031).
\begin{figure}[t]
\includegraphics[width=0.8\linewidth]{../figures/main.png}
\caption{Accuracy of M and B across seeds.}
\label{fig:main}
\end{figure}
Figure~\ref{fig:main} shows the effect.
\section{Conclusion}
M is better than B.
\bibliography{references}
\end{document}
"""


class Study:
    """Handles for one study project: ids, workspace root, helpers to edit it."""

    def __init__(self, pid: str, bp_run_id: str, root: Path, exports: Path):
        self.pid, self.bp_run_id, self.root, self.exports = pid, bp_run_id, root, exports

    def project(self) -> Project:
        with Session(engine) as s:
            return s.get(Project, self.pid)

    def states(self) -> dict[str, TaskState]:
        bp = (self.project().blueprint or {}).get("run_id")
        with Session(engine) as s:
            return {st.task_id: st for st in s.exec(select(TaskState).where(TaskState.blueprint_run_id == bp))}

    def runs(self, kind: str | None = None) -> list[Run]:
        with Session(engine) as s:
            q = select(Run).where(Run.project_id == self.pid)
            if kind:
                q = q.where(Run.kind == kind)
            return list(s.exec(q.order_by(Run.started_at)))

    def write_paper(self, tex: str = TEX, pdf: bool = True, when: float | None = None) -> None:
        paper = self.root / "paper"
        paper.mkdir(parents=True, exist_ok=True)
        when = time.time() if when is None else when
        (paper / "paper.tex").write_text(tex, encoding="utf-8")
        import os
        os.utime(paper / "paper.tex", (when, when))
        if pdf:
            (paper / "paper.pdf").write_bytes(b"%PDF-1.5 fake")
            os.utime(paper / "paper.pdf", (when + 1, when + 1))

    def update(self, **fields) -> None:
        with Session(engine) as s:
            p = s.get(Project, self.pid)
            for k, v in fields.items():
                setattr(p, k, v)
            s.add(p)
            s.commit()

    def cleanup(self) -> None:
        with Session(engine) as s:
            for link in s.exec(select(ProjectPaper).where(ProjectPaper.project_id == self.pid)):
                if paper := s.get(Paper, link.paper_id):
                    s.delete(paper)
            for model in (TaskState, Run, ProjectPaper, Message):
                for row in s.exec(select(model).where(model.project_id == self.pid)):
                    s.delete(row)
            for row in s.exec(select(Usage).where(Usage.project_id == self.pid)):
                s.delete(row)
            if p := s.get(Project, self.pid):
                s.delete(p)
            s.commit()


def isolate(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """Workspaces and exports under tmp_path; no sandbox, GPU provider or URL check reaches out."""
    workspaces, exports = tmp_path / "workspaces", tmp_path / "exports"
    monkeypatch.setattr(e2b_sandbox, "WORKSPACES", workspaces)
    monkeypatch.setattr(sandbox, "_sandboxes", {})
    monkeypatch.setattr(plan_agent, "EXPORT_DIR", exports)
    monkeypatch.setattr(blueprint_agent, "EXPORT_DIR", exports)

    async def no_urls(datasets):
        return {d.id: True for d in datasets if d.url}

    monkeypatch.setattr(blueprint_agent, "_verify_urls", no_urls)
    from app.execution import colab_runner
    monkeypatch.setattr(colab_runner, "configured", lambda: False)
    monkeypatch.setattr(llm, "_GRAMMAR_FALLBACK", {})
    monkeypatch.setattr(orchestrator, "_controls", {})
    return workspaces, exports


def make_study(tmp_path: Path, monkeypatch, *, autonomous: bool = True, refinement: dict | None = None,
               user_id: str | None = None) -> Study:
    workspaces, exports = isolate(tmp_path, monkeypatch)
    plan = research_plan()
    mp = master_plan()
    now = datetime.now(timezone.utc)
    settings = {"budget": {"llm_usd": 15.0, "gpu_hours": 5.0},
                "amendments": [{"task": "T2.1", "text": "Use 5 seeds (raised in R1-02).", "at": now.isoformat()}]}
    if refinement is not None:
        settings["refinement"] = refinement
    with Session(engine) as s:
        p = Project(title="_study", stage="complete", autonomous=autonomous, user_id=user_id, settings=settings,
                    brief={"title": "Seed robustness", "core_question": "Is M more accurate than B?",
                           "summary": "Compare M and B.", "scope_in": ["accuracy"], "scope_out": ["latency"],
                           "result_type": "computational", "constraints": [], "assumptions": [],
                           "data_resources": "public", "compute_resources": "CPU"},
                    chosen_gap={"id": "g1", "run_id": "gaps-run", "title": "Seeds", "question": "Is M better?",
                                "hypothesis": "M > B", "why_open": "untested", "approach": "seeds",
                                "novelty_check": {"closest": [{"title": "Prior M study", "overlap": "partial"}]}})
        s.add(p)
        s.commit()
        s.refresh(p)
        pid = p.id
        plan_run = Run(project_id=pid, kind="plan", status="done", result={"plan": plan, "gap_id": "g1",
                                                                            "gaps_run_id": "gaps-run"})
        bp = Run(project_id=pid, kind="blueprint", status="done",
                 result={"master_plan": mp, "warnings": [], "budget": {"llm_usd": 15.0, "gpu_hours": 5.0},
                         "capabilities": ["python"], "plan_run_id": "x"},
                 started_at=now - timedelta(hours=3))
        ex = Run(project_id=pid, kind="execute", status="done", started_at=now - timedelta(hours=2),
                 finished_at=now - timedelta(minutes=30), result={"counts": {"done": 5}})
        rep = Run(project_id=pid, kind="report", status="done", started_at=now - timedelta(minutes=10),
                  finished_at=now - timedelta(minutes=5),
                  result={"integrity": {"hard": [], "soft": []}, "audit": [{"claim": "SENTINEL_AUDIT"}]})
        s.add_all([plan_run, bp, ex, rep])
        s.commit()
        for r in (plan_run, bp):
            s.refresh(r)
        p = s.get(Project, pid)
        p.plan = {**plan, "run_id": plan_run.id, "approved_at": now.isoformat()}
        p.blueprint = {"run_id": bp.id, "approved_at": now.isoformat()}
        s.add(p)
        for t in mp["tasks"]:
            s.add(TaskState(project_id=pid, blueprint_run_id=bp.id, task_id=t["id"], agent="A1", status="done",
                            attempts=1, cost=0.1, summary=f"{t['id']} done. SENTINEL_TASK_SUMMARY",
                            artifacts=[o["path"] for o in t["outputs"]],
                            checks=[{"check": "c", "passed": True, "reason": "SENTINEL_VERIFIER"}],
                            finished_at=now - timedelta(minutes=40)))
        paper = Paper(title="Data methods for robust testing", norm_title=norm_title("Data methods for robust testing"),
                      abstract="We show that robust testing needs at least five seeds.", year=2020,
                      venue="JMLR", authors=["Jane Smith"],
                      notes={"contribution": "Seeds matter.", "key_findings": ["Five seeds suffice."], "methods": [],
                             "datasets": [], "limitations": []})
        s.add(paper)
        s.commit()
        s.refresh(paper)
        s.add(ProjectPaper(project_id=pid, paper_id=paper.id, relevance=3, score=1.0, included=True))
        s.commit()
        bp_id = bp.id
    root = workspaces / pid
    files = {
        "data/raw.csv": "x,y\n1,2\n3,4\n",
        "results/runs.csv": "seed,method,accuracy\n1,M,0.912\n1,B,0.874\n",
        "results/baseline.csv": "seed,accuracy\n1,0.874\n",
        "analysis/stats.csv": "metric,M,B,p\naccuracy,0.912,0.874,0.031\n",
        "src/stats.py": "from scipy import stats\nprint(stats.ttest_rel([1], [2]))\n",
        "scripts/plot.py": "import matplotlib\nplt.savefig('figures/main.png')\n",
        "results/SUMMARY.md": "# Summary\nM 0.912, B 0.874, p=0.031 (5 seeds).\n",
        "paper/scaffold.json": '{"writing_instructions": "SENTINEL_SCAFFOLD"}',
        "team/NOTES.md": "- SENTINEL_TEAM_NOTES\n",
        "context/AMENDMENTS.md": "# amendments\n",
    }
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    old = time.time() - 3600
    import os
    for rel in files:
        os.utime(root / rel, (old, old))
    (root / "figures").mkdir(parents=True, exist_ok=True)
    (root / "figures" / "main.png").write_bytes(png())
    os.utime(root / "figures" / "main.png", (old + 60, old + 60))
    from app.agents.report import _references

    _, bib = _references(pid)
    (root / "paper").mkdir(parents=True, exist_ok=True)
    (root / "paper" / "references.bib").write_text(bib, encoding="utf-8")
    study = Study(pid, bp_id, root, exports)
    study.write_paper(when=time.time() - 400)
    # Earlier review artifacts that must never reach a judge.
    prev = exports / pid / "review" / "iter-0"
    prev.mkdir(parents=True, exist_ok=True)
    (prev / "mistakes.json").write_text('{"summary": "SENTINEL_PREVIOUS_MISTAKES"}', encoding="utf-8")
    (prev / "repair_plan.json").write_text('{"summary": "SENTINEL_REPAIR_PLAN"}', encoding="utf-8")
    return study
