"""Scientific review routes: ownership, guards, files, defaults (offline)."""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app import jobs, refine
from app.agents import judge
from app.auth import CurrentUser, get_current_user
from app.db import Project, engine
from app.main import app
from study_fixture import make_study
from test_core import _approve

OWNER = "33333333-3333-3333-3333-333333333333"
OTHER = "44444444-4444-4444-4444-444444444444"


@pytest.fixture
def client():
    _approve(OWNER, OTHER)
    who = {"id": OWNER}
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=who["id"], email="u@example.com")
    with TestClient(app) as c:
        c.who = who
        yield c
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def study(tmp_path, monkeypatch):
    s = make_study(tmp_path, monkeypatch, refinement={"enabled": True}, user_id=OWNER)
    yield s
    s.cleanup()


def test_review_state_is_owner_only(client, study):
    r = client.get(f"/api/projects/{study.pid}/review")
    assert r.status_code == 200 and r.json()["enabled"] is True and r.json()["review"]["live"]["review"] is False
    client.who["id"] = OTHER
    assert client.get(f"/api/projects/{study.pid}/review").status_code == 404
    assert client.post(f"/api/projects/{study.pid}/review/start").status_code == 404


def test_start_requires_a_finished_report_and_stop_requires_an_active_review(client, study, monkeypatch):
    assert client.post(f"/api/projects/{study.pid}/review/stop").status_code == 409
    started = []
    monkeypatch.setattr(refine, "start_review", lambda pid: started.append(pid))
    r = client.post(f"/api/projects/{study.pid}/review/start")
    assert r.status_code == 200 and started == [study.pid]
    assert study.project().settings["refinement"]["enabled"] is True
    assert client.post(f"/api/projects/{study.pid}/review/stop").status_code == 200
    assert study.project().review["status"] == "stopped"
    with Session(engine) as s:
        p = Project(title="_no_report", user_id=OWNER)
        s.add(p)
        s.commit()
        pid = p.id
    try:
        r = client.post(f"/api/projects/{pid}/review/start")
        assert r.status_code == 409 and "report first" in r.json()["detail"]
    finally:
        with Session(engine) as s:
            s.delete(s.get(Project, pid))
            s.commit()


def test_planning_changes_are_blocked_during_a_review(client, study):
    study.update(review={"status": "repairing", "step": "execute"})
    r = client.post(f"/api/projects/{study.pid}/plan/revise", json={"instruction": "add an ablation"})
    assert r.status_code == 409 and "scientific review is in progress" in r.json()["detail"]
    assert client.post(f"/api/projects/{study.pid}/blueprint/approve").status_code == 409


def test_execution_and_report_are_blocked_while_the_review_job_works(client, study, monkeypatch):
    monkeypatch.setattr(jobs, "is_running", lambda pid, kind: kind == "repair")
    assert client.post(f"/api/projects/{study.pid}/execution/resume", json={}).status_code == 409
    assert client.post(f"/api/projects/{study.pid}/report/run").status_code == 409
    r = client.post(f"/api/projects/{study.pid}/execution/changes/T3.1", json={"feedback": "x"})
    assert r.status_code == 409


def test_review_files_are_allowlisted(client, study):
    out = judge.review_dir(study.pid, 1)
    out.mkdir(parents=True, exist_ok=True)
    (out / "mistakes.json").write_text("{}", encoding="utf-8")
    (judge.review_dir(study.pid) / "REVIEW.md").write_text("# ok", encoding="utf-8")
    base = f"/api/projects/{study.pid}/review/file"
    assert client.get(base, params={"name": "mistakes.json", "iteration": 1}).status_code == 200
    assert client.get(base, params={"name": "REVIEW.md"}).status_code == 200
    assert client.get(base, params={"name": "../../secrets.txt", "iteration": 1}).status_code == 404
    assert client.get(base, params={"name": "REVIEW.md", "iteration": 1}).status_code == 404
    assert client.get(base, params={"name": "mistakes.json", "iteration": 9}).status_code == 404


def test_new_projects_get_the_review_by_default(client):
    r = client.post("/api/projects", json={"title": "_defaults"})
    pid = r.json()["id"]
    try:
        assert r.json()["settings"]["refinement"] == {"enabled": True}
        r = client.post("/api/projects", json={"title": "_opt_out", "settings": {"refinement": {"enabled": False}}})
        assert r.json()["settings"]["refinement"] == {"enabled": False}
        other = r.json()["id"]
    finally:
        with Session(engine) as s:
            for i in (pid, locals().get("other")):
                if i and (p := s.get(Project, i)):
                    s.delete(p)
            s.commit()
