"""Offline regression tests for OpenScientist's core logic (no model calls, no network
except where marked)."""

import asyncio
import copy

import pytest

from app.agents.blueprint import MasterPlan, validate
from app.agents.literature import cite
from app.agents.plan import ResearchPlan, graph_errors, parse_plan
from app.agents.report import _bib_key, _bibtex
from app.db import Paper
from app.execution import orchestrator
from app.execution.sandbox import _CONDA_PKG, _PKG, LocalSandbox
from app.execution.tools import TOOLS, ToolContext, public_url
from app.graph import _norm

CAPS = {"python", "shell", "internet", "files", "cpu", "background", "conda", "apple_gpu"}
BUDGET = {"llm_usd": 15.0, "gpu_hours": 5.0}


# ── Plan task graph ────────────────────────────────────────────────────────


def _plan(tasks: list[dict]) -> dict:
    base = {k: "x" for k in ("title", "research_question", "hypothesis", "null_hypothesis", "background",
                             "validation_strategy", "compute_estimate", "duration_estimate")}
    return {**base, "objectives": [], "study_type": "empirical", "datasets": [], "methods": [], "baselines": [],
            "metrics": [], "success_criteria": [], "risks": [], "deliverables": [], "open_questions": [],
            "phases": [{"id": "P1", "name": "p", "goal": "g", "tasks": tasks}]}


def _ptask(tid: str, deps: list[str]) -> dict:
    return {"id": tid, "title": tid, "description": "d", "kind": "analysis", "inputs": [], "outputs": [f"{tid}.csv"],
            "depends_on": deps, "effort": "S", "tools_hint": []}


def test_plan_graph_valid():
    plan, errors = parse_plan(_plan([_ptask("T1", []), _ptask("T2", ["T1"])]))
    assert plan is not None and errors == []


def test_plan_graph_errors():
    p = ResearchPlan.model_validate(_plan([_ptask("T1", ["T2"]), _ptask("T2", ["T1"]), _ptask("T3", ["T9"]),
                                           _ptask("T3", [])]))
    errors = graph_errors(p)
    assert any("cycle" in e for e in errors)
    assert any("unknown task T9" in e for e in errors)
    assert any("Duplicate" in e for e in errors)


def test_plan_schema_errors_reported():
    bad = _plan([_ptask("T1", [])])
    bad["phases"][0]["tasks"][0]["effort"] = "XL"
    plan, errors = parse_plan(bad)
    assert plan is None and errors


# ── Blueprint validation ───────────────────────────────────────────────────


def _mp() -> dict:
    cpu = {"kind": "cpu", "est_minutes": 5, "timeout_minutes": 15}
    task = lambda tid, deps, inputs, outs, **kw: {  # noqa: E731
        "id": tid, "title": tid, "agent": "A1", "objective": "o", "steps": ["s"], "inputs": inputs,
        "outputs": [{"path": p, "format": "csv", "description": "d"} for p in outs], "acceptance_checks": ["c"],
        "depends_on": deps, "tools": ["run_python"], "resources": [], "compute": cpu, "max_cost_usd": 0.5,
        "retries": 1, "human_required": False, **kw}
    return {
        "title": "t", "summary": "s", "python_packages": ["pandas>=2"], "system_requirements": [],
        "agents": [{"id": "A1", "name": "a", "model_tier": "standard", "tools": ["run_python"], "instructions": "i"}],
        "datasets": [{"id": "D1", "name": "d", "url": "https://example.org", "access_method": "x", "format": "csv",
                      "license": "CC", "notes": ""}],
        "tasks": [task("T1", [], [{"path": "raw", "source": "dataset:D1"}], ["data/a.csv"]),
                  task("T2", ["T1"], [{"path": "data/a.csv", "source": "task:T1"}], ["data/b.csv"])],
        "checkpoints": [], "llm_usd_estimate": 1.0, "compute_hours_estimate": 0.1, "execution_notes": [],
    }


def test_blueprint_valid():
    errors, warnings = validate(MasterPlan.model_validate(_mp()), CAPS, BUDGET)
    assert errors == [] and warnings == []


@pytest.mark.parametrize("mutate,expect", [
    (lambda m: m["agents"][0]["tools"].append("teleport"), "unknown tools"),
    (lambda m: m["python_packages"].append("evil; rm -rf /"), "Invalid package spec"),
    (lambda m: m["tasks"][1].update(agent="A9"), "unknown agent"),
    (lambda m: m["tasks"][1]["inputs"].append({"path": "data/zz.csv", "source": "task:T1"}), "does not produce"),
    (lambda m: m["tasks"][1].update(depends_on=[]), "does not depend on it"),
    (lambda m: m["tasks"][0].update(depends_on=["T2"]), "cycle"),
    (lambda m: m["tasks"][0]["inputs"].append({"path": "x", "source": "dataset:D7"}), "unknown dataset"),
    (lambda m: m["tasks"][1]["tools"].append("run_shell"), "lacks"),
])
def test_blueprint_errors(mutate, expect):
    m = copy.deepcopy(_mp())
    mutate(m)
    errors, _ = validate(MasterPlan.model_validate(m), CAPS, BUDGET)
    assert any(expect in e for e in errors), errors


def test_blueprint_runtime_warnings():
    m = copy.deepcopy(_mp())
    m["tasks"][1]["compute"] = {"kind": "cuda_gpu", "est_minutes": 600, "timeout_minutes": 700}
    m["tasks"][0]["max_cost_usd"] = 20
    errors, warnings = validate(MasterPlan.model_validate(m), CAPS, BUDGET)
    assert errors == []
    assert any("CUDA" in w for w in warnings) and any("above the" in w for w in warnings)


# ── Security guards ────────────────────────────────────────────────────────


@pytest.mark.parametrize("url", ["http://localhost:8000/api", "http://127.0.0.1/", "http://192.168.1.1/",
                                 "http://10.0.0.5/", "file:///etc/passwd", "ftp://example.org/x"])
def test_private_urls_blocked(url):
    with pytest.raises(ValueError):
        public_url(url)


@pytest.mark.parametrize("spec,ok", [("pandas", True), ("pandas>=2.0", True), ("biopython==1.84", True),
                                     ("torch[cuda]", True), ("x; rm -rf /", False), ("--index-url=evil", False),
                                     ("pkg @ https://evil", False)])
def test_pip_spec(spec, ok):
    assert bool(_PKG.match(spec)) is ok


@pytest.mark.parametrize("spec,ok", [("openbabel", True), ("autodock-vina=1.2.5", True),
                                     ("conda-forge::tectonic", True), ("gromacs>=2024", True),
                                     ("x && curl evil", False)])
def test_conda_spec(spec, ok):
    assert bool(_CONDA_PKG.match(spec)) is ok


def test_sandbox_path_guard(tmp_path):
    sb = LocalSandbox("_t")
    sb.root = tmp_path
    assert sb.path("data/x.csv") == tmp_path / "data" / "x.csv"
    for bad in ("../../.env", "../x", "data/../../y"):
        with pytest.raises(ValueError):
            sb.path(bad)


def test_edit_file_requires_unique_match(tmp_path):
    sb = LocalSandbox("_t")
    sb.root = tmp_path
    (tmp_path / "m.py").write_text("a = 1\na = 1\nb = 2\n")
    ctx = ToolContext("_t", sb, None)
    out = asyncio.run(TOOLS["edit_file"].handler(ctx, {"path": "m.py", "old": "a = 1", "new": "a = 3"}))
    assert "matched 2 times" in out
    out = asyncio.run(TOOLS["edit_file"].handler(ctx, {"path": "m.py", "old": "b = 2", "new": "b = 5"}))
    assert out.startswith("Edited") and "b = 5" in (tmp_path / "m.py").read_text()


# ── Text utilities ─────────────────────────────────────────────────────────


def test_cite_formats_and_drops_bad_indices():
    papers = [Paper(title="A b", norm_title="a b", authors=["Simon Chu", "X Y"], year=2024),
              Paper(title="M", norm_title="m", authors=["Kotaro Tsuboyama"], year=2023)]
    assert cite("Data exist [0, 1]. Bad [9].", papers) == "Data exist (Chu et al. 2024; Tsuboyama 2023). Bad."


def test_graph_norm_merges_plurals():
    assert _norm("Protein Language Models") == _norm("protein language model")
    assert _norm("Brass") == "brass"


def test_bib_keys_unique_and_escaped():
    taken: set[str] = set()
    p = Paper(title="Sleep & memory_consolidation", norm_title="s", authors=["Jessica Payne"], year=2012)
    k1, k2 = _bib_key(p, taken), _bib_key(p, taken)
    assert k1 != k2 and k1.startswith("payne2012")
    bib = _bibtex(k1, p)
    assert r"\&" in bib and r"\_" in bib


# ── Execution ──────────────────────────────────────────────────────────────


def test_escalation():
    assert orchestrator.escalated_model("bulk", "minimal", 1) == ("gpt-6-luna", False)
    assert orchestrator.escalated_model("bulk", "minimal", 2) == ("gpt-6-sol", True)
    assert orchestrator.escalated_model("standard", "default", 2) == ("gpt-6-astra", True)
    assert orchestrator.escalated_model("reasoning", "economy", 1)[0] == "gpt-6-sol"


def test_csv_previews_give_exact_facts(tmp_path):
    sb = LocalSandbox("_t")
    sb.root = tmp_path
    (tmp_path / "d.csv").write_text("a,b\n" + "\n".join(f"{i},{i * 2}" for i in range(365)) + "\n")
    text = orchestrator._previews(sb, [{"path": "d.csv"}, {"path": "missing.csv"}])
    assert "365 data rows" in text and "364,728" in text and "MISSING" in text


def test_stage_cancel_marks_run():
    from sqlmodel import Session

    from app import jobs
    from app.db import Project, Run, engine

    async def scenario():
        with Session(engine) as s:
            p = Project(title="_cancel_test")
            s.add(p)
            s.commit()
            s.refresh(p)
            pid = p.id

        async def slow(project_id, h):
            await asyncio.sleep(30)
            return {}

        run = jobs.start(pid, "report", slow)
        await asyncio.sleep(0.2)
        assert jobs.cancel(pid, "report")
        await asyncio.sleep(0.2)
        with Session(engine) as s:
            r = s.get(Run, run.id)
            status, error = r.status, r.error
            s.delete(r)
            s.delete(s.get(Project, pid))
            s.commit()
        return status, error

    assert asyncio.run(scenario()) == ("error", "Cancelled")


def test_confirm_brief_keeps_settings():
    from fastapi.testclient import TestClient
    from sqlmodel import Session

    from app.db import Project, engine
    from app.main import app

    with Session(engine) as s:
        p = Project(title="_settings_test", brief={"title": "x"},
                    settings={"budget": {"llm_usd": 2.0, "gpu_hours": 1}, "model_policy": "economy"})
        s.add(p)
        s.commit()
        s.refresh(p)
        pid = p.id
    import app.routes.projects as routes

    started = []
    original = routes.pipeline.start_literature
    routes.pipeline.start_literature = lambda project_id: started.append(project_id)
    try:
        with TestClient(app) as client:
            r = client.post(f"/api/projects/{pid}/brief/confirm", json={"depth": "quick"})
            assert r.status_code == 200
            cfg = r.json()["settings"]
    finally:
        routes.pipeline.start_literature = original
        with Session(engine) as s:
            s.delete(s.get(Project, pid))
            s.commit()
    assert cfg["budget"]["llm_usd"] == 2.0 and cfg["model_policy"] == "economy" and cfg["depth"] == "quick"
    assert started == [pid]


def test_request_changes_resets_dependents():
    from sqlmodel import Session

    from app.db import Project, Run, TaskState, engine

    mp = _mp()
    mp["tasks"].append({**mp["tasks"][1], "id": "T3", "depends_on": ["T2"],
                        "inputs": [{"path": "data/b.csv", "source": "task:T2"}], "outputs": [
                            {"path": "data/c.csv", "format": "csv", "description": "d"}]})
    with Session(engine) as s:
        p = Project(title="_rc_test")
        s.add(p)
        s.commit()
        s.refresh(p)
        r = Run(project_id=p.id, kind="blueprint", status="done", result={"master_plan": mp})
        s.add(r)
        s.commit()
        s.refresh(r)
        p.blueprint = {"run_id": r.id}
        s.add(p)
        for tid in ("T1", "T2", "T3"):
            s.add(TaskState(project_id=p.id, blueprint_run_id=r.id, task_id=tid, agent="A1", status="done", attempts=1))
        s.commit()
        pid, rid = p.id, r.id
    try:
        assert orchestrator.request_changes(pid, "T2", "use T=10000") == ["T2", "T3"]
        with Session(engine) as s:
            from sqlmodel import select
            st = {x.task_id: x for x in s.exec(select(TaskState).where(TaskState.blueprint_run_id == rid))}
            assert st["T1"].status == "done" and st["T2"].status == "pending" and st["T3"].status == "pending"
            assert st["T2"].feedback == "use T=10000" and st["T3"].feedback is None
    finally:
        with Session(engine) as s:
            from sqlmodel import select
            for x in s.exec(select(TaskState).where(TaskState.blueprint_run_id == rid)):
                s.delete(x)
            s.delete(s.get(Run, rid))
            s.delete(s.get(Project, pid))
            s.commit()


def test_routes_do_not_shadow_each_other():
    """Every declared POST route must be reachable (a generic path param can swallow a sibling)."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        r = client.post("/api/projects/nope/execution/changes/T1", json={"feedback": "x"})
        assert r.status_code == 404 and "Project not found" in r.text
        r = client.post("/api/projects/nope/execution/tasks/T1/skip", json={})
        assert r.status_code == 404 and "Project not found" in r.text
        r = client.post("/api/projects/nope/runs/report/cancel")
        assert r.status_code == 404 and "Project not found" in r.text


def test_budget_is_read_fresh():
    from sqlmodel import Session

    from app.db import Project, engine

    with Session(engine) as s:
        p = Project(title="_budget_test", settings={"budget": {"llm_usd": 1.0}})
        s.add(p)
        s.commit()
        s.refresh(p)
        pid = p.id
    try:
        assert orchestrator.current_budget(pid) == 1.0
        with Session(engine) as s:
            p = s.get(Project, pid)
            p.settings = {"budget": {"llm_usd": 3.5}}
            s.add(p)
            s.commit()
        assert orchestrator.current_budget(pid) == 3.5
    finally:
        with Session(engine) as s:
            s.delete(s.get(Project, pid))
            s.commit()


def test_gpu_budget_refusal(tmp_path, monkeypatch):
    from app.execution import modal_runner as mr

    monkeypatch.setattr(mr, "configured", lambda: True)
    monkeypatch.setattr(mr, "gpu_budget", lambda pid: 1.0)
    monkeypatch.setattr(mr, "gpu_spent", lambda pid: 0.9)
    sb = LocalSandbox("_t")
    sb.root = tmp_path
    ctx = ToolContext("_t", sb, None)
    out = asyncio.run(TOOLS["run_gpu_jobs"].handler(ctx, {
        "jobs": [{"name": "a", "command": "python x.py"}], "gpu": "L4", "timeout_minutes": 60, "pip_packages": ["torch"]}))
    assert out.startswith("Refused") and "$0.10" in out
    out = asyncio.run(TOOLS["run_gpu_jobs"].handler(ctx, {
        "jobs": [{"name": "a b", "command": "x"}], "pip_packages": []}))
    assert "unique names" in out


def test_gpu_tool_granted_for_gpu_tasks():
    sb = LocalSandbox("_t")
    sb.capabilities = set(sb.BASE_CAPABILITIES) | {"cuda_gpu"}
    task = {"tools": ["run_python"], "compute": {"kind": "apple_gpu"}}
    agent = {"tools": ["run_python", "run_shell"]}
    assert "run_gpu_jobs" in orchestrator._task_tools(task, agent, sb)
    task["compute"]["kind"] = "cpu"
    assert "run_gpu_jobs" not in orchestrator._task_tools(task, agent, sb)
