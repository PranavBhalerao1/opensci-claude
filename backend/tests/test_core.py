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
from app.execution.e2b_sandbox import E2BSandbox
from app.execution.sandbox import _CONDA_PKG, _PKG
from app.execution.tools import TOOLS, ToolContext, public_url
from app.graph import _norm

CAPS = {"python", "shell", "internet", "files", "cpu", "background", "conda", "apple_gpu"}
BUDGET = {"llm_usd": 15.0, "gpu_hours": 5.0}


def _approve(*user_ids: str) -> None:
    """Grant private-beta access (uncapped) so route tests reach the product routes."""
    from sqlmodel import Session

    from app.db import BetaUser, engine

    with Session(engine) as s:
        for uid in user_ids:
            s.merge(BetaUser(user_id=uid, approved=True))
        s.commit()


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
    sb = E2BSandbox("_t")
    sb.root = tmp_path
    assert sb.path("data/x.csv") == tmp_path / "data" / "x.csv"
    for bad in ("../../.env", "../x", "data/../../y"):
        with pytest.raises(ValueError):
            sb.path(bad)


def test_edit_file_requires_unique_match(tmp_path):
    sb = E2BSandbox("_t")
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


def test_escalation(monkeypatch):
    # Escalation logic over three distinct tiers (the defaults may all name one model).
    for tier, name in (("reasoning", "gpt-6-astra"), ("standard", "gpt-6-sol"), ("bulk", "gpt-6-luna")):
        monkeypatch.setattr(orchestrator.settings, f"model_{tier}", name)
    assert orchestrator.escalated_model("bulk", "minimal", 1) == ("gpt-6-luna", False)
    assert orchestrator.escalated_model("bulk", "minimal", 2) == ("gpt-6-sol", True)
    assert orchestrator.escalated_model("standard", "default", 2) == ("gpt-6-astra", True)
    assert orchestrator.escalated_model("reasoning", "economy", 1)[0] == "gpt-6-sol"


def test_escalation_with_one_model_for_every_tier():
    # Default config: every tier is the same Bedrock model, so a retry keeps that model
    # and is not flagged as escalated (no stronger model exists to move to).
    model = orchestrator.settings.bedrock_model_id
    assert orchestrator.escalated_model("bulk", "minimal", 2) == (model, False)
    assert orchestrator.escalated_model("standard", "default", 2) == (model, False)


def test_effort_escalation_raises_one_level_per_failed_attempt_capped_at_high():
    # A task starting at LOW can retry at MEDIUM and then HIGH.
    assert [orchestrator.escalated_effort("low", n) for n in (1, 2, 3, 4)] == ["low", "medium", "high", "high"]
    # A task starting at MEDIUM can escalate to HIGH (and stays there).
    assert [orchestrator.escalated_effort("medium", n) for n in (1, 2, 3)] == ["medium", "high", "high"]
    # Already at HIGH: no further escalation is possible.
    assert [orchestrator.escalated_effort("high", n) for n in (1, 2, 3)] == ["high", "high", "high"]


def test_csv_previews_give_exact_facts(tmp_path):
    sb = E2BSandbox("_t")
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

    from app.auth import CurrentUser, get_current_user
    from app.db import Project, engine
    from app.main import app

    with Session(engine) as s:
        p = Project(title="_settings_test", user_id="11111111-1111-1111-1111-111111111111", brief={"title": "x"},
                    settings={"budget": {"llm_usd": 2.0, "gpu_hours": 1}, "model_policy": "economy"})
        s.add(p)
        s.commit()
        s.refresh(p)
        pid = p.id
    import app.routes.projects as routes

    _approve("11111111-1111-1111-1111-111111111111")
    started = []
    original = routes.pipeline.start_literature
    routes.pipeline.start_literature = lambda project_id: started.append(project_id)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="11111111-1111-1111-1111-111111111111", email="u1@example.com"
    )
    try:
        with TestClient(app) as client:
            r = client.post(f"/api/projects/{pid}/brief/confirm", json={"depth": "quick"})
            assert r.status_code == 200
            cfg = r.json()["settings"]
    finally:
        routes.pipeline.start_literature = original
        app.dependency_overrides.pop(get_current_user, None)
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
            assert st["T2"].feedback == "use T=10000" and st["T3"].feedback is None  # kept for the verifier
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

    from app.auth import CurrentUser, get_current_user
    from app.main import app

    uid = "55555555-5555-5555-5555-555555555555"
    _approve(uid)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=uid, email="u1@example.com")
    try:
        with TestClient(app) as client:
            r = client.post("/api/projects/nope/execution/changes/T1", json={"feedback": "x"})
            assert r.status_code == 404 and "Project not found" in r.text
            r = client.post("/api/projects/nope/execution/tasks/T1/skip", json={})
            assert r.status_code == 404 and "Project not found" in r.text
            r = client.post("/api/projects/nope/runs/report/cancel")
            assert r.status_code == 404 and "Project not found" in r.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)


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
    from app.execution import colab_runner as mr

    monkeypatch.setattr(mr, "configured", lambda: True)
    monkeypatch.setattr(mr, "gpu_budget", lambda pid: 1.0)
    monkeypatch.setattr(mr, "gpu_spent", lambda pid: 0.9)
    sb = E2BSandbox("_t")
    sb.root = tmp_path
    ctx = ToolContext("_t", sb, None)
    out = asyncio.run(TOOLS["run_gpu_jobs"].handler(ctx, {
        "jobs": [{"name": "a", "command": "python x.py"}], "gpu": "L4", "timeout_minutes": 60, "pip_packages": ["torch"]}))
    assert out.startswith("Refused") and "$0.10" in out
    out = asyncio.run(TOOLS["run_gpu_jobs"].handler(ctx, {
        "jobs": [{"name": "a b", "command": "x"}], "pip_packages": []}))
    assert "unique names" in out


# ── Auth ─────────────────────────────────────────────────────────────────


def test_missing_or_malformed_bearer_token_rejected():
    import asyncio

    from fastapi import HTTPException

    from app.auth import get_current_user

    for header in (None, "", "Token abc", "Bearer", "Bearer   "):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(get_current_user(header, None))
        assert exc.value.status_code == 401


def test_get_current_user_falls_back_to_query_token(monkeypatch):
    import asyncio

    from app import auth

    monkeypatch.setattr(auth, "verify_token", lambda token: {"sub": f"user-for-{token}", "email": "e@x.com"})
    # No Authorization header: falls back to the query param (used by <a>/<img>/<iframe> links).
    user = asyncio.run(auth.get_current_user(None, "querytoken"))
    assert user.id == "user-for-querytoken"
    # Header present: takes priority over the query param.
    user = asyncio.run(auth.get_current_user("Bearer headertoken", "querytoken"))
    assert user.id == "user-for-headertoken"


def test_verify_token_rejects_garbage(monkeypatch):
    from app import auth
    from app.config import settings

    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co")
    with pytest.raises(Exception):
        auth.verify_token("not-a-jwt")


def test_project_routes_require_auth():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        assert client.get("/api/projects").status_code == 401
        assert client.post("/api/projects", json={}).status_code == 401
        assert client.get("/api/projects/nope").status_code == 401


def test_user_cannot_access_another_users_project():
    from fastapi.testclient import TestClient
    from sqlmodel import Session

    from app.auth import CurrentUser, get_current_user
    from app.db import Project, engine
    from app.main import app

    owner = "22222222-2222-2222-2222-222222222222"
    other = "33333333-3333-3333-3333-333333333333"
    _approve(owner, other)
    with Session(engine) as s:
        p = Project(title="_owner_test", user_id=owner)
        s.add(p)
        s.commit()
        s.refresh(p)
        pid = p.id
    try:
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=other, email="other@example.com")
        with TestClient(app) as client:
            r = client.get(f"/api/projects/{pid}")
            assert r.status_code == 404
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=owner, email="owner@example.com")
        with TestClient(app) as client:
            r = client.get(f"/api/projects/{pid}")
            assert r.status_code == 200
            r = client.get("/api/projects")
            assert all(proj["id"] != pid or proj["id"] == pid for proj in r.json())  # sanity: list succeeds
            assert any(proj["id"] == pid for proj in r.json())
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        with Session(engine) as s:
            s.delete(s.get(Project, pid))
            s.commit()


def test_create_project_ignores_client_supplied_user_id():
    from fastapi.testclient import TestClient
    from sqlmodel import Session

    from app.auth import CurrentUser, get_current_user
    from app.db import Project, engine
    from app.main import app

    real_user = "44444444-4444-4444-4444-444444444444"
    _approve(real_user)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=real_user, email="real@example.com")
    pid = None
    try:
        with TestClient(app) as client:
            r = client.post("/api/projects", json={"title": "spoof test", "user_id": "not-the-real-user"})
            assert r.status_code == 200
            body = r.json()
            pid = body["id"]
        with Session(engine) as s:
            assert s.get(Project, pid).user_id == real_user
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        if pid:
            with Session(engine) as s:
                s.delete(s.get(Project, pid))
                s.commit()


def test_gpu_tool_granted_for_gpu_tasks():
    sb = E2BSandbox("_t")
    sb.capabilities = set(sb.BASE_CAPABILITIES) | {"cuda_gpu"}
    task = {"tools": ["run_python"], "compute": {"kind": "apple_gpu"}}
    agent = {"tools": ["run_python", "run_shell"]}
    assert "run_gpu_jobs" in orchestrator._task_tools(task, agent, sb)
    task["compute"]["kind"] = "cpu"
    assert "run_gpu_jobs" not in orchestrator._task_tools(task, agent, sb)


# ── E2B sandbox (offline parts) ────────────────────────────────────────────


def test_sandbox_for_is_always_e2b_and_fails_clearly_without_it(monkeypatch, tmp_path):
    from app.execution import e2b_sandbox, sandbox as sandbox_mod

    monkeypatch.setattr(sandbox_mod, "_sandboxes", {})
    sb = sandbox_mod.sandbox_for("_e")
    assert isinstance(sb, E2BSandbox)  # constructed without any network call
    sb.root = tmp_path
    monkeypatch.setattr(e2b_sandbox.settings, "e2b_api_key", None)
    with pytest.raises(RuntimeError, match="E2B is not configured"):
        asyncio.run(sb.ensure())
    ctx = ToolContext("_e", sb, None)
    for name, args in [("run_python", {"code": "print(1)"}), ("run_shell", {"command": "echo 1"}),
                       ("install_packages", {"packages": ["numpy"]}), ("start_process", {"name": "p", "command": "x"})]:
        with pytest.raises(RuntimeError, match="E2B is not configured"):  # never a local fallback
            asyncio.run(TOOLS[name].handler(ctx, args))


def test_e2b_paths_and_capabilities(tmp_path, monkeypatch):
    from app.execution import colab_runner
    sb = E2BSandbox("_t")
    sb.root = tmp_path
    assert sb._remote(str(sb.path(".scratch/cell_001.py"))) == "/home/user/workspace/.scratch/cell_001.py"
    assert sb._remote(str(tmp_path)) == "/home/user/workspace"
    assert sb._remote("-q") == "-q" and str(sb.python) == "/home/user/.venv/bin/python"
    monkeypatch.setattr(colab_runner, "configured", lambda: False)
    assert "apple_gpu" not in sb.capabilities and "cuda_gpu" not in sb.capabilities
    assert {"python", "shell", "conda", "background"} <= sb.capabilities
    monkeypatch.setattr(colab_runner, "configured", lambda: True)
    assert "cuda_gpu" in sb.capabilities  # explicit CUDA work → Colab


def test_e2b_sync_skips_environments(tmp_path):
    from app.execution.e2b_sandbox import _parse_listing

    sb = E2BSandbox("_t")
    sb.root = tmp_path
    for rel in (".venv/bin/python", ".conda/x", "pkg/__pycache__/m.pyc", ".tmp/t", ".scratch/cell_001.py",
                ".logs/train.log", "data/x.csv", "context/brief.json"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("x")
    assert sorted(sb._scan_host()) == [".logs/train.log", ".scratch/cell_001.py", "context/brief.json", "data/x.csv"]
    listing = "./data/x.csv\t12\t1700000000.5\n./.venv/lib/a.py\t3\t1.0\n./a\tb.txt\t4\t2.0\nnoise\n"
    assert _parse_listing(listing) == {"data/x.csv": (12, "1700000000.5"), "a\tb.txt": (4, "2.0")}


def test_e2b_pull_and_status_offline(tmp_path):
    sb = E2BSandbox("_t")
    sb.root = tmp_path
    asyncio.run(sb.pull())  # no sandbox yet, no background processes: nothing to do
    ctx = ToolContext("_t", sb, None)
    out = asyncio.run(TOOLS["check_process"].handler(ctx, {"name": "train"}))
    assert out.startswith("No process named train")
    assert asyncio.run(TOOLS["stop_process"].handler(ctx, {"name": "train"})) == "train is not running"
