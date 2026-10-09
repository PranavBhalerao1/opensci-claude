"""Application-owned text files are UTF-8 regardless of the OS default encoding.

On Windows the default is the ANSI code page (e.g. cp1252) unless PYTHONUTF8=1, and
plan approval crashed writing "≥". These tests force a cp1252 default so they fail
the same way on any machine if an explicit encoding is dropped."""

import asyncio
import io
import json
import pathlib
from types import SimpleNamespace as NS

import pytest
from sqlmodel import Session, select

from app import jobs, pipeline
from app.agents import plan as plan_agent
from app.db import Project, Run, engine
from app.execution import orchestrator
from app.execution.e2b_sandbox import E2BSandbox
from app.execution.tools import TOOLS, ToolContext

UNI = "Δ ≥ α — β ≤ ρ –"


@pytest.fixture
def cp1252_default(monkeypatch):
    """Make the platform default text encoding cp1252, as on a stock Windows install
    (also under PYTHONUTF8=1, where io.text_encoding would otherwise resolve to UTF-8)."""
    original = pathlib.Path.open
    monkeypatch.setattr(io, "text_encoding", lambda encoding, stacklevel=2: encoding or "locale")

    def open_(self, mode="r", buffering=-1, encoding=None, errors=None, newline=None):
        if "b" not in mode and encoding in (None, "locale"):
            encoding = "cp1252"
        return original(self, mode, buffering, encoding, errors, newline)

    monkeypatch.setattr(pathlib.Path, "open", open_)


def test_simulated_default_reproduces_the_bug(tmp_path, cp1252_default):
    # Guards the fixture: without an explicit encoding the write fails as it did on Windows.
    with pytest.raises(UnicodeEncodeError):
        (tmp_path / "x.txt").write_text(UNI)


def _project(**kw) -> str:
    with Session(engine) as s:
        p = Project(title="_encoding_test", **kw)
        s.add(p)
        s.commit()
        s.refresh(p)
        return p.id


def _cleanup(pid: str) -> None:
    with Session(engine) as s:
        for r in s.exec(select(Run).where(Run.project_id == pid)):
            s.delete(r)
        s.delete(s.get(Project, pid))
        s.commit()


def test_autonomous_plan_approval_writes_unicode(tmp_path, monkeypatch, cp1252_default):
    """The autonomous chain plan → approve → blueprint, which stalled on "≥"."""
    monkeypatch.setattr(plan_agent, "EXPORT_DIR", tmp_path)
    monkeypatch.setattr(plan_agent, "build_context", lambda pid: {"brief": {"note": UNI}})
    started = []
    monkeypatch.setattr(pipeline, "start_blueprint", lambda pid: started.append(pid))
    pid = _project(autonomous=True)

    async def job(project_id, h):
        return {"plan": {"title": UNI, "success_criteria": [f"accuracy {UNI} 0.8"]}}

    async def scenario():
        run = jobs.start(pid, "plan", job, then=pipeline._after_plan)
        await jobs._tasks[f"{pid}:plan"]
        return run.id

    try:
        run_id = asyncio.run(scenario())
        with Session(engine) as s:
            run, project = s.get(Run, run_id), s.get(Project, pid)
            assert (run.status, run.error) == ("done", None)
            assert project.plan["title"] == UNI and project.stage == "blueprint"
        assert started == [pid]
        for name in ("vague_research_plan.json", "context.json"):
            raw = (tmp_path / pid / name).read_bytes()
            assert UNI.encode("utf-8") in raw  # byte-valid UTF-8, characters kept verbatim
            json.loads(raw.decode("utf-8"))
        assert json.loads((tmp_path / pid / "vague_research_plan.json").read_bytes())["title"] == UNI
    finally:
        _cleanup(pid)


def test_agent_file_tools_round_trip_unicode(tmp_path, cp1252_default):
    sb = E2BSandbox("_t")
    sb.root = tmp_path

    async def no_pull():
        return None

    sb.pull = no_pull
    ctx = ToolContext("_t", sb, None, agent_name="Agent α")

    def call(tool, **a):
        return asyncio.run(TOOLS[tool].handler(ctx, a))

    call("write_file", path="results/summary.md", content=f"Δ = 0.3 {UNI}\n")
    assert UNI in call("read_file", path="results/summary.md")
    assert call("edit_file", path="results/summary.md", old="Δ = 0.3", new="Δ ≥ 0.4").startswith("Edited")
    # Byte-exact: on Windows, writing in the platform's default text mode would have turned
    # these "\n"s into "\r\n", corrupting any file pushed on to the Linux E2B sandbox.
    raw = (tmp_path / "results/summary.md").read_bytes()
    assert b"\r" not in raw
    assert raw.decode("utf-8") == f"Δ ≥ 0.4 {UNI}\n"
    call("post_note", text=f"ρ {UNI}")
    assert "Agent α" in call("read_notes") and f"ρ {UNI}" in call("read_notes")
    notes_raw = (tmp_path / "team/NOTES.md").read_bytes()
    assert b"\r" not in notes_raw
    notes_raw.decode("utf-8")


def test_write_file_always_uses_lf_line_endings(tmp_path):
    sb = E2BSandbox("_t")
    sb.root = tmp_path
    ctx = ToolContext("_t", sb, None, agent_name="Agent")
    content = "#!/bin/bash\necho one\necho two\n"
    asyncio.run(TOOLS["write_file"].handler(ctx, {"path": "run.sh", "content": content}))
    raw = (tmp_path / "run.sh").read_bytes()
    assert b"\r" not in raw
    assert raw.decode("utf-8") == content


def test_edit_file_preserves_the_existing_line_endings_it_does_not_touch(tmp_path):
    """edit_file must not silently rewrite a file's line endings: only the matched snippet
    changes, whatever convention the rest of the file already uses."""
    sb = E2BSandbox("_t")
    sb.root = tmp_path
    (tmp_path / "data.csv").write_bytes(b"a,b\r\n1,2\r\n")
    ctx = ToolContext("_t", sb, None, agent_name="Agent")
    out = asyncio.run(TOOLS["edit_file"].handler(ctx, {"path": "data.csv", "old": "1,2", "new": "1,3"}))
    assert out.startswith("Edited")
    assert (tmp_path / "data.csv").read_bytes() == b"a,b\r\n1,3\r\n"


def test_run_python_writes_an_lf_only_scratch_file(tmp_path):
    sb = E2BSandbox("_t")
    sb.root = tmp_path

    async def fake_run(argv, timeout, owner=None):
        return NS(render=lambda: "ok")

    sb.run = fake_run
    ctx = ToolContext("_t", sb, None, agent_name="Agent")
    code = "print('a')\nprint('b')\n"
    asyncio.run(TOOLS["run_python"].handler(ctx, {"code": code}))
    (cell,) = (tmp_path / ".scratch").glob("cell_*.py")
    raw = cell.read_bytes()
    assert b"\r" not in raw
    assert raw.decode("utf-8") == code


def test_output_previews_read_utf8(tmp_path, cp1252_default):
    sb = E2BSandbox("_t")
    sb.root = tmp_path
    (tmp_path / "r.csv").write_bytes(f"metric,value\n{UNI},1\n".encode("utf-8"))
    (tmp_path / "r.md").write_bytes(f"# {UNI}\n".encode("utf-8"))
    text = orchestrator._previews(sb, [{"path": "r.csv"}, {"path": "r.md"}])
    assert text.count(UNI) == 2


def test_follow_up_failure_is_recorded_on_the_run():
    """A stage that finished but whose next stage crashed must not stall silently."""
    pid = _project()

    async def job(project_id, h):
        return {"ok": True}

    async def then(project_id):
        "≥".encode("cp1252")  # the original crash

    async def scenario():
        run = jobs.start(pid, "plan", job, then=then)
        await jobs._tasks[f"{pid}:plan"]
        return run.id

    try:
        run_id = asyncio.run(scenario())
        with Session(engine) as s:
            run = s.get(Run, run_id)
            assert run.status == "done" and run.result == {"ok": True}  # the plan itself stays usable
            assert run.error.startswith("Next stage failed to start: UnicodeEncodeError")
            assert run.log[-1]["text"] == run.error
    finally:
        _cleanup(pid)
