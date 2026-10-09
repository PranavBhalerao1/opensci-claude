"""Offline tests for the Colab GPU runner (no network, no compute units).

The `colab` CLI is replaced by FakeColab, which keeps per-session file stores and plays
scripted jobs, so the host side runs for real: result protocol, retries, part transfers
with sha checks, staged extraction, the session pool, the ledger and GpuUsage metering.
test_remote_steps_locally runs the actual VM-side scripts on this machine (Linux/macOS).
"""

import asyncio
import base64
import hashlib
import io
import json
import os
import re
import secrets
import subprocess
import sys
import tarfile
import threading
import time
from dataclasses import dataclass, field

import pytest
from sqlmodel import Session, select

from app.db import GpuUsage, Project, engine
from app.execution import colab_runner as cr
from app.llm import current_run

MODAL_SUCCESS_KEYS = {"name", "exit_code", "seconds", "log", "timed_out", "log_tail", "wall_seconds", "cost"}
MODAL_ERROR_KEYS = {"name", "exit_code", "error", "seconds", "log", "log_tail", "wall_seconds", "cost"}


@dataclass
class Job:
    rc: int | None = 0
    files: dict = field(default_factory=dict)
    seconds: int = 7
    log: str = "training…\nloss 0.01\n"
    waits: int = 0  # WAIT cells that still see it running
    never_done: bool = False
    transport_failures: int = 0  # WAIT cells whose connection drops
    gone: bool = False  # the VM disappears during WAIT


class FakeColab:
    """Stands in for `colab` (the CLI): same commands, same output conventions as 0.7.4."""

    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}
        self.jobs: dict[str, Job] = {}
        self.calls: list[list[str]] = []
        self.gpu_name = "NVIDIA L4"
        self.balance = 200.0
        self.usage_out: tuple | None = None
        self.new_failures: list[tuple] = []
        self.pip_rc = 0
        self.corrupt_downloads = 0
        self.killed: list[str] = []
        self.max_live = 0
        self.lock = threading.Lock()

    def __call__(self, args, timeout, session=None):
        with self.lock:
            self.calls.append(list(args))
        cmd = args[0]
        name = args[args.index("-s") + 1] if "-s" in args else None
        if cmd == "usage":
            return self.usage_out or (0, f"Current balance: {self.balance:.2f} compute units\nUsage rate: 0.00/hr\n"
                                         f"Active assignments: {len(self.sessions)}\n", "")
        if cmd == "new":
            if self.new_failures:
                return self.new_failures.pop(0)
            with self.lock:
                self.sessions[name] = {"files": {}}
                self.max_live = max(self.max_live, len(self.sessions))
            return 0, f"[colab] Creating session '{name}'...\n[colab] Session READY.\n", ""
        if name not in self.sessions:
            return (1 if cmd == "exec" else 0), f"[colab] Session '{name}' not found.\n", ""
        files = self.sessions[name]["files"]
        if cmd == "stop":
            with self.lock:
                del self.sessions[name]
            return 0, f"[colab] Stopping session '{name}'...\n[colab] Session terminated.\n", ""
        if cmd == "status":
            return 0, f"[colab] Session '{name}' is active.\n", ""
        if cmd == "upload":
            local, remote = args[3], args[4]
            files[remote] = open(local, "rb").read()
            return 0, f"[colab] Uploaded '{local}' to '{remote}'\n", ""
        if cmd == "download":
            remote, local = args[3], args[4]
            if remote not in files:
                return 1, f"[colab] Download failed: File or directory not found: {remote}\n", ""
            data = files[remote]
            if self.corrupt_downloads and "/out/" in remote:
                self.corrupt_downloads -= 1
                data = b"X" + data[1:]
            open(local, "wb").write(data)
            return 0, f"[colab] Downloaded '{remote}' to '{local}'\n", ""
        if cmd == "exec":
            code = open(args[args.index("-f") + 1]).read()
            p = json.loads(base64.b64decode(re.search(r"b64decode\('([^']+)'\)", code)[1]))
            out = self._exec(name, files, code, p)
            if isinstance(out, tuple):
                return out
            return 0, f"{cr.SENTINEL}{json.dumps(out)}\n", ""
        raise AssertionError(f"unexpected command {args}")

    def _exec(self, name, files, code, p):
        if cr._GPUCHECK in code:
            return {"gpu": self.gpu_name}
        if cr._SETUP in code:
            data = b"".join(files.get(f"{cr.CONTENTS}/in/part_{i:03d}", b"") for i in range(p["parts"]))
            self.sessions[name]["workspace"] = data
            files[f"{cr.CONTENTS}/environment.txt"] = b"Python 3.13.15\ntorch==2.11.0+cu130\n"
            out = {"sha_ok": hashlib.sha256(data).hexdigest() == p["sha"]}
            if p["packages"]:
                out.update(pip_rc=self.pip_rc, pip_tail="ERROR: No matching distribution" if self.pip_rc else "ok")
            return out
        if cr._LAUNCH in code:
            self.sessions[name].setdefault("launched", []).append(p["name"])
            return {"pid": 4242, "resumed": False}
        if cr._WAIT in code:
            job = self.jobs[p["name"]]
            if job.gone:
                with self.lock:
                    del self.sessions[name]
                return 1, f"[colab] Session '{name}' not found.\n", ""
            if job.transport_failures:
                job.transport_failures -= 1
                return "TIMEOUT", "", "RuntimeError: Connection was lost.\n"
            if job.never_done or job.waits:
                job.waits = max(0, job.waits - 1)
                time.sleep(0.01)
                return {"rc": None}
            return {"rc": job.rc}
        if cr._KILL in code:
            self.killed.append(p["name"])
            return {"killed": True}
        if cr._COLLECT in code:
            job, n = self.jobs[p["name"]], p["name"]
            out_files = {**job.files, f"logs/gpu/{n}.log": (job.log + self.gpu_name + "\n").encode(),
                         f"logs/gpu/{n}.log.time": f"__OS_START__ 1000\n__OS_END__ {1000 + job.seconds}\n".encode()}
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                for rel, data in out_files.items():
                    info = tarfile.TarInfo(rel)
                    info.size = len(data)
                    tar.addfile(info, io.BytesIO(data))
            blob = buf.getvalue()
            parts = [blob[i:i + p["part"]] for i in range(0, len(blob), p["part"])]
            for i, part in enumerate(parts):
                files[f"{cr.CONTENTS}/out/{n}/part_{i:03d}"] = part
            return {"files": len(out_files), "parts": len(parts), "sha": hashlib.sha256(blob).hexdigest()}
        raise AssertionError("unknown remote step")

    def count(self, cmd: str) -> int:
        return sum(1 for c in self.calls if c[0] == cmd)


@pytest.fixture
def fake(monkeypatch, tmp_path):
    f = FakeColab()
    monkeypatch.setattr(cr, "_cli", f)
    monkeypatch.setattr(cr, "COLAB_HOME", tmp_path / "colab")
    monkeypatch.setattr(cr, "RETRY_S", 0)
    monkeypatch.setattr(cr, "BACKOFF_S", (0, 0, 0))
    monkeypatch.setattr(cr, "DEADLINE_GRACE_S", 0)
    monkeypatch.setattr(cr.settings, "colab_max_sessions", 1)
    return f


@pytest.fixture
def project():
    with Session(engine) as s:
        p = Project(title="_colab", settings={"gpu_budget_usd": 10.0})
        s.add(p)
        s.commit()
        pid = p.id
    yield pid
    with Session(engine) as s:
        for row in s.exec(select(GpuUsage).where(GpuUsage.project_id == pid)):
            s.delete(row)
        s.delete(s.get(Project, pid))
        s.commit()


@pytest.fixture
def ws(tmp_path):
    root = tmp_path / "ws"
    (root / "data").mkdir(parents=True)
    (root / "data" / "input.txt").write_bytes(b"3\n4\n")
    (root / "train.py").write_bytes(b"print('hi')\n")
    (root / ".venv").mkdir()
    (root / ".venv" / "big.bin").write_bytes(b"x" * 100)
    return root


def _usage(pid):
    with Session(engine) as s:
        return list(s.exec(select(GpuUsage).where(GpuUsage.project_id == pid)))


def _jobs(*names):
    return [{"name": n, "command": f"python train.py {n}"} for n in names]


# ── Contract ───────────────────────────────────────────────────────────────


def test_success_matches_modal_contract(fake, project, ws, monkeypatch):
    monkeypatch.setattr(cr, "PART_BYTES", 64 * 1024)  # forces multi-part transfers
    big = os.urandom(200 * 1024)
    fake.jobs["a"] = Job(files={"results/metrics.json": b'{"acc": 0.9}', "ckpt/model.pt": big}, seconds=7)
    fake.jobs["b"] = Job(rc=3, files={"results/b.csv": b"x,y\n1,2\n"}, seconds=4)
    token = current_run.set("run-123")
    try:
        out = cr.run_jobs(project, ws, _jobs("a", "b"), "L4", 600, [])
    finally:
        current_run.reset(token)

    assert set(out) == {"jobs", "files_synced_back", "changed_files"}
    a, b = out["jobs"]
    assert set(a) == MODAL_SUCCESS_KEYS and set(b) == MODAL_SUCCESS_KEYS
    assert (a["name"], a["exit_code"], a["timed_out"], a["seconds"]) == ("a", 0, False, 7.0)
    assert (b["exit_code"], b["seconds"]) == (3, 4.0)
    assert a["cost"] == pytest.approx(7 * cr.rate("L4"), abs=1e-4)
    assert a["log"] == "logs/gpu/a.log" and "NVIDIA L4" in a["log_tail"] and "loss 0.01" in a["log_tail"]
    assert (ws / "ckpt" / "model.pt").read_bytes() == big and (ws / "results" / "b.csv").exists()
    assert (ws / "logs" / "gpu" / "a.log.time").read_text().startswith("__OS_START__")
    assert (ws / "logs" / "gpu" / "_environment.txt").read_text().startswith("Python 3.13")
    assert "results/metrics.json" in out["changed_files"] and out["files_synced_back"] == len(out["changed_files"])
    assert not (ws / ".tmp").exists() or not any((ws / ".tmp").iterdir())  # staging cleaned up

    with tarfile.open(fileobj=io.BytesIO(_seen_ws["data"])) as tar:  # Modal's upload filter: no hidden dirs
        assert sorted(tar.getnames()) == ["data/input.txt", "train.py"]
    rows = _usage(project)
    assert sorted(r.job for r in rows) == ["(session overhead)", "a", "b"]
    assert all(r.run_id == "run-123" and r.gpu == "L4" for r in rows)
    assert not fake.sessions  # stopped
    assert not list((cr.COLAB_HOME / "sessions").iterdir())  # ledger and CLI state forgotten


_seen_ws: dict = {}


@pytest.fixture(autouse=True)
def _capture_workspace(monkeypatch):
    """Keep the bytes the runner uploads (its part files are deleted right after upload)."""
    orig = FakeColab._exec

    def spy(self, name, files, code, p):
        out = orig(self, name, files, code, p)
        if cr._SETUP in code:
            _seen_ws["data"] = self.sessions[name]["workspace"]
        return out

    monkeypatch.setattr(FakeColab, "_exec", spy)


def test_timeout_rule(fake, project, ws):
    fake.jobs["slow"] = Job(rc=124, seconds=60)  # coreutils timeout fired at the limit
    fake.jobs["oom"] = Job(rc=137, seconds=5)  # SIGKILL early: not a timeout
    slow, oom = cr.run_jobs(project, ws, _jobs("slow", "oom"), "L4", 60, [])["jobs"]
    assert slow["timed_out"] is True and slow["exit_code"] == 124
    assert oom["timed_out"] is False and oom["exit_code"] == 137


def test_host_deadline_kills_and_still_collects(fake, project, ws):
    fake.jobs["hang"] = Job(never_done=True, files={"partial.txt": b"half"})
    r = cr.run_jobs(project, ws, _jobs("hang"), "L4", 1, [])["jobs"][0]
    assert r["timed_out"] is True and r["exit_code"] is None
    assert fake.killed == ["hang"] and (ws / "partial.txt").read_bytes() == b"half"


# ── Failures are never reported as success ─────────────────────────────────


def test_lost_runtime_and_stale_logs(fake, project, ws):
    (ws / "logs" / "gpu").mkdir(parents=True)
    (ws / "logs" / "gpu" / "a.log").write_text("STALE: accuracy 0.99 from an earlier attempt\n")
    fake.jobs["a"] = Job(gone=True)
    fake.jobs["b"] = Job()
    a, b = cr.run_jobs(project, ws, _jobs("a", "b"), "L4", 600, [])["jobs"]
    assert set(a) == MODAL_ERROR_KEYS and a["exit_code"] is None and "runtime lost" in a["error"]
    assert a["log_tail"] == ""  # never the stale log
    assert set(b) == MODAL_ERROR_KEYS and b["error"] == "not run: the Colab runtime was lost" and b["cost"] == 0


def test_dropped_connections_are_retried(fake, project, ws):
    fake.jobs["a"] = Job(transport_failures=2, waits=1)
    r = cr.run_jobs(project, ws, _jobs("a"), "L4", 600, [])["jobs"][0]
    assert r["exit_code"] == 0 and "error" not in r


def test_corrupt_download_is_retried_then_reported(fake, project, ws):
    fake.jobs["a"] = Job(files={"r.txt": b"ok"})
    fake.corrupt_downloads = 1
    assert cr.run_jobs(project, ws, _jobs("a"), "L4", 600, [])["jobs"][0]["exit_code"] == 0
    (ws / "r.txt").unlink()
    fake.corrupt_downloads = 99
    r = cr.run_jobs(project, ws, _jobs("a"), "L4", 600, [])["jobs"][0]
    assert r["exit_code"] == 0 and "downloaded intact" in r["error"] and not (ws / "r.txt").exists()


def test_gpu_unavailable_backs_off_then_reports(fake, project, ws):
    busy = (1, "[colab] Creating session...\n", "ColabRequestError: Failed to issue request POST "
                                                "https://colab.research.google.com/tun/m/assign: Service Unavailable\n")
    fake.new_failures = [busy] * 4
    out = cr.run_jobs(project, ws, _jobs("a", "b"), "L4", 600, [])
    assert fake.count("new") == 4  # first try + 3 backoffs
    assert all(j["error"].startswith("not run: Colab could not start a L4 GPU") for j in out["jobs"])
    assert "Service Unavailable" in out["jobs"][0]["error"] and not fake.sessions


def test_entitlement_error_is_not_retried(fake, project, ws):
    fake.new_failures = [(1, "", "ColabRequestError: ... accelerator=L4: Bad Request\n")]
    cr.run_jobs(project, ws, _jobs("a"), "L4", 600, [])
    assert fake.count("new") == 1


def test_wrong_gpu_is_never_used(fake, project, ws):
    fake.gpu_name = "NVIDIA A100-SXM4-40GB"  # the CLI's silent fallback for unknown types
    r = cr.run_jobs(project, ws, _jobs("a"), "L4", 600, [])["jobs"][0]
    assert "instead of L4" in r["error"] and fake.count("upload") == 0 and not fake.sessions


def test_pip_failure_is_fatal_for_the_call(fake, project, ws, monkeypatch):
    monkeypatch.setattr(cr.settings, "colab_max_sessions", 2)
    fake.pip_rc = 1
    out = cr.run_jobs(project, ws, _jobs("a", "b", "c", "d"), "L4", 600, ["nonexistent-pkg"])
    assert all("pip install failed" in j["error"] for j in out["jobs"])
    assert fake.count("new") <= 2 and not fake.sessions  # no new VM per remaining job


# ── Preflight ──────────────────────────────────────────────────────────────


def test_cli_detects_auth_failure_and_passes_no_secrets(tmp_path, monkeypatch):
    """The real _cli: no stdin (a re-login prompt fails instead of hanging), no backend secrets in the
    environment, ADC credentials, its own process group; expired credentials become ColabAuthError."""
    seen = {}

    def run(argv, **kw):
        seen.update(argv=argv, **kw)
        return subprocess.CompletedProcess(argv, seen.get("rc", 1), "", seen.get("err", ""))

    monkeypatch.setattr(cr, "_bin", lambda: "/opt/colab")
    monkeypatch.setattr(cr.subprocess, "run", run)
    monkeypatch.setattr(cr.settings, "colab_credentials_file", str(tmp_path / "credentials.json"))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-must-not-leak")
    seen["err"] = "google.auth.exceptions.RefreshError: ('invalid_grant: Token has been expired or revoked.')"
    with pytest.raises(cr.ColabAuthError, match="credentials were rejected"):
        cr._cli(["usage"], 60)
    assert seen["argv"][:2] == ["/opt/colab", "--auth=adc"]
    assert set(seen["env"]) == {"PATH", "LANG", "HOME", "GOOGLE_APPLICATION_CREDENTIALS"}
    assert seen["stdin"] is subprocess.DEVNULL and seen["start_new_session"] is True and seen["umask"] == 0o077
    seen.update(rc=0, err="EOFError in the remote traceback")  # remote code's errors are not auth failures
    assert cr._cli(["exec"], 60)[0] == 0


def test_auth_failure_stops_the_call(fake, project, ws, monkeypatch):
    def expired(args, timeout, session=None):
        raise cr.ColabAuthError()

    monkeypatch.setattr(cr, "_cli", expired)
    with pytest.raises(cr.ColabAuthError):
        cr.run_jobs(project, ws, _jobs("a"), "L4", 600, [])
    assert fake.count("new") == 0


def test_refusals_before_any_session(fake, project, ws):
    fake.balance = 10.5
    with pytest.raises(cr.ColabError, match="compute units"):
        cr.run_jobs(project, ws, _jobs("a"), "L4", 3600, [])
    fake.balance = 200
    with pytest.raises(cr.ColabError, match="GPU budget"):
        cr.run_jobs(project, ws, _jobs(*[f"j{i}" for i in range(40)]), "L4", 3 * 3600, [])  # ~$18 > $10
    fake.usage_out = (0, "something unexpected\n", "")
    with pytest.raises(cr.ColabError, match="Could not read"):
        cr.run_jobs(project, ws, _jobs("a"), "L4", 600, [])
    assert fake.count("new") == 0


def test_large_files_are_skipped_and_reported(fake, project, ws, monkeypatch):
    monkeypatch.setattr(cr, "MAX_SYNC_FILE_BYTES", 5)
    fake.jobs["a"] = Job()
    out = cr.run_jobs(project, ws, _jobs("a"), "L4", 600, [])
    assert out["skipped_uploads"] == ["train.py"]  # 12 bytes; data/input.txt is 4


# ── Sessions: pool, rotation, cancellation, reaper ─────────────────────────


def test_pool_caps_sessions_across_calls(fake, project, ws, monkeypatch):
    for n in ("a", "b", "c", "d"):
        fake.jobs[n] = Job(waits=10)

    async def two_calls():
        return await asyncio.gather(cr.run_async(project, ws, _jobs("a", "b"), "L4", 600, []),
                                    cr.run_async(project, ws, _jobs("c", "d"), "L4", 600, []))

    results = asyncio.run(two_calls())
    assert fake.max_live == 1 and all(j["exit_code"] == 0 for r in results for j in r["jobs"])
    monkeypatch.setattr(cr.settings, "colab_max_sessions", 2)
    fake.max_live = 0
    for n in ("a", "b", "c", "d"):
        fake.jobs[n].waits = 10
    asyncio.run(two_calls())
    assert fake.max_live == 2


def test_sessions_rotate_instead_of_refusing(fake, project, ws, monkeypatch):
    monkeypatch.setattr(cr, "MAX_SESSION_S", 650)  # a session cannot fit a second 600 s job (+60 s overhead)
    monkeypatch.setattr(cr, "SESSION_OVERHEAD_S", 10)
    for n in ("a", "b", "c"):
        fake.jobs[n] = Job()
    out = cr.run_jobs(project, ws, _jobs("a", "b", "c"), "L4", 600, [])
    assert all(j["exit_code"] == 0 for j in out["jobs"]) and fake.count("new") == 3 and not fake.sessions


def test_cancellation_kills_and_stops(fake, project, ws):
    fake.jobs["a"] = Job(never_done=True)

    async def go():
        task = asyncio.create_task(cr.run_async(project, ws, _jobs("a"), "L4", 3600, []))
        while not fake.sessions or not fake.sessions[next(iter(fake.sessions))].get("launched"):
            await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(go())
    assert fake.killed == ["a"] and not fake.sessions
    assert any(r.job == "a" for r in _usage(project))  # what ran is still metered


def test_cancel_while_waiting_for_a_slot_allocates_nothing(fake, project, ws):
    fake.jobs["a"] = Job(never_done=True)
    fake.jobs["b"] = Job()

    async def go():
        first = asyncio.create_task(cr.run_async(project, ws, _jobs("a"), "L4", 3600, []))
        while not fake.sessions:
            await asyncio.sleep(0.01)
        second = asyncio.create_task(cr.run_async(project, ws, _jobs("b"), "L4", 3600, []))
        await asyncio.sleep(0.2)
        second.cancel()
        with pytest.raises(asyncio.CancelledError):
            await second
        assert fake.count("new") == 1  # the queued call never started a VM
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first

    asyncio.run(go())
    assert not fake.sessions


def test_reaper_stops_only_dead_owners(fake, monkeypatch):
    sessions = cr.COLAB_HOME / "sessions"
    sessions.mkdir(parents=True)
    monkeypatch.setattr(cr, "_boot_id", lambda: "boot-1")
    monkeypatch.setattr(cr, "_proc_start", lambda pid: {111: "500", 222: "999"}.get(pid))
    for name, pid, start in (("live", 111, "500"), ("dead", 222, "777"), ("gone", 333, "1")):
        fake.sessions[name] = {"files": {}}
        (sessions / f"{name}.owner").write_text(json.dumps(
            {"pid": pid, "start": start, "boot": "boot-1", "created": time.time()}))
    del fake.sessions["gone"]  # Colab already reclaimed it: "not found" counts as stopped
    assert cr.reap() == 2
    assert set(fake.sessions) == {"live"} and [p.name for p in sessions.iterdir()] == ["live.owner"]


def test_reaper_meters_what_the_crashed_process_did_not(fake, project, monkeypatch):
    sessions = cr.COLAB_HOME / "sessions"
    sessions.mkdir(parents=True)
    monkeypatch.setattr(cr, "_boot_id", lambda: "boot-now")  # the owner's host rebooted
    fake.sessions["orphan"] = {"files": {}}
    (sessions / "orphan.owner").write_text(json.dumps({"pid": 1, "start": "1", "boot": "boot-then", "project_id": project,
                                                       "gpu": "L4", "created": time.time() - 600, "job_seconds": 100}))
    assert cr.reap() == 1
    row = next(r for r in _usage(project) if r.job == "(orphaned session)")
    assert row.seconds == pytest.approx(500, abs=5) and row.cost == pytest.approx(500 * cr.rate("L4"), abs=1e-3)


@pytest.mark.skipif(sys.platform == "win32", reason="finds processes through /proc")
def test_reaper_kills_cli_processes_a_crashed_backend_left(fake, tmp_path):
    """They would otherwise rewrite the session's state (with its proxy token) after it is forgotten."""
    (cr.COLAB_HOME / "sessions").mkdir(parents=True)
    orphan = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)", "--config", str(cr._cfg("os-x-1"))])
    bystander = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)", "--config", str(cr._cfg("os-y-2"))])
    try:
        time.sleep(0.5)
        assert cr._kill_cli("os-x-1") == 1
        assert orphan.wait(5) == -9 and bystander.poll() is None
    finally:
        for p in (orphan, bystander):
            p.kill()
            p.wait()


def test_reaper_keeps_entries_it_could_not_stop(fake, monkeypatch):
    sessions = cr.COLAB_HOME / "sessions"
    sessions.mkdir(parents=True)
    monkeypatch.setattr(cr, "_boot_id", lambda: "boot-2")  # host rebooted: the owner is gone
    (sessions / "stuck.owner").write_text(json.dumps({"pid": 1, "start": "1", "boot": "boot-1", "created": time.time()}))
    monkeypatch.setattr(cr, "_stop", lambda name: False)
    assert cr.reap() == 0 and (sessions / "stuck.owner").exists()


# ── Small pieces ───────────────────────────────────────────────────────────


def test_redaction_strips_every_credential_shape():
    text = ("Authorization: Bearer ya29.a0AfB_byC-secret token=ya29.ZZZ refresh 1//0gXyz-secret "
            "https://8080-m-s-x.prod.colab.dev/api/contents/x?authuser=0&colab-runtime-proxy-token=eyJhbGci.eyJhdWQ.sig "
            "jwt eyJabc_DEF.eyJpayload_x.signature-1 {\"refresh_token\": \"1//abc\", \"client_secret\": \"s3cr3t\"} "
            "\x1b[0;31mValueError\x1b[0m")
    clean = cr._redact(text)
    for secret in ("ya29", "1//0g", "eyJ", "s3cr3t", "secret token", "\x1b["):
        assert secret not in clean, secret
    assert "ValueError" in clean


def test_extraction_never_escapes_the_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(cr, "COLAB_HOME", tmp_path / "colab")
    root = tmp_path / "ws"
    root.mkdir()
    blob = tmp_path / "out.tgz"
    with tarfile.open(blob, "w:gz") as tar:
        for name in ("ok/a.txt", "../evil.txt", ".hidden/x.txt", "__pycache__/m.pyc"):
            info = tarfile.TarInfo(name)
            info.size = 2
            tar.addfile(info, io.BytesIO(b"hi"))
        link = tarfile.TarInfo("link")
        link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
        tar.addfile(link)
    call = cr._Call.__new__(cr._Call)
    call.root = root.resolve()
    assert cr._extract(call, blob) == ["ok/a.txt"]
    assert not (tmp_path / "evil.txt").exists() and not (root / "link").exists() and not (root / ".hidden").exists()


def test_configured_needs_cli_and_credentials(tmp_path, monkeypatch):
    creds = tmp_path / "credentials.json"
    monkeypatch.setattr(cr, "_bin", lambda: "/usr/bin/colab")
    monkeypatch.setattr(cr.settings, "colab_credentials_file", str(creds))
    monkeypatch.setattr(cr.sys, "platform", "linux")
    assert not cr.configured()  # no credentials file yet
    creds.write_text("{}")
    assert cr.configured()
    monkeypatch.setattr(cr.sys, "platform", "win32")
    assert not cr.configured()  # the CLI does not support Windows


@pytest.mark.skipif(sys.platform == "win32", reason="the debug-log symlink is POSIX-only")
def test_home_setup_is_safe_under_concurrency(tmp_path, monkeypatch):
    monkeypatch.setattr(cr, "COLAB_HOME", tmp_path / "colab")
    errors = []

    def setup():
        try:
            cr._prepare_home()
        except Exception as exc:  # noqa: BLE001 — any error is the failure under test
            errors.append(exc)

    threads = [threading.Thread(target=setup) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    log = tmp_path / "colab" / ".config" / "colab-cli" / "colab.log"
    assert errors == [] and os.readlink(log) == "/dev/null"
    assert oct((tmp_path / "colab").stat().st_mode & 0o777) == "0o700"


def test_result_line_parsing():
    assert cr._parse("[colab] noise\n__OS_RESULT__{\"rc\": 0}\n") == {"rc": 0}
    assert cr._parse("Traceback ...\nValueError: boom\n") is None  # `colab exec` exits 0 here
    assert cr._reason("│ x │\n╰──╯\nColabRequestError: Failed: Service Unavailable\n").startswith("ColabRequestError")


# ── Wiring: tool spec, the only provider, capability, startup reaper ───────


def test_gpu_tool_spec_is_colab():
    from app.execution.tools import TOOLS, _gpu_tool

    colab = TOOLS["run_gpu_jobs"]
    assert colab == _gpu_tool() and "Modal" not in colab.description
    assert colab.parameters["properties"]["gpu"]["enum"] == sorted(cr.GPU_PRICES, reverse=True) == ["T4", "L4"]
    assert "Google Colab" in colab.description and "queue" in colab.description
    assert colab.requires == ("cuda_gpu",) and colab.parameters["required"] == ["jobs", "pip_packages"]


def test_colab_is_the_only_gpu_provider(tmp_path, monkeypatch):
    import importlib

    from app.config import Settings
    from app.execution.e2b_sandbox import E2BSandbox
    from app.execution.sandbox import gpu_runner
    from app.execution.tools import TOOLS, ToolContext

    monkeypatch.setenv("GPU_PROVIDER", "modal")  # the old switch is ignored, never an error or a fallback
    assert not hasattr(Settings(_env_file=None), "gpu_provider")
    assert gpu_runner() is cr
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.execution.modal_runner")
    # No credentials (the suite's environment): a clear error, no GPU capability, no other provider.
    monkeypatch.setattr(cr.settings, "colab_credentials_file", None)
    sb = E2BSandbox("_c")
    sb.root = tmp_path
    args = {"jobs": [{"name": "a", "command": "python x.py"}], "gpu": "L4", "timeout_minutes": 10, "pip_packages": []}
    assert not cr.configured() and "cuda_gpu" not in sb.capabilities
    assert asyncio.run(TOOLS["run_gpu_jobs"].handler(ToolContext("_c", sb, None), args)) == (
        "Cloud GPUs are not configured (no Colab credentials).")


def test_run_gpu_jobs_routes_to_colab(tmp_path, monkeypatch):
    from app.execution.e2b_sandbox import E2BSandbox
    from app.execution.tools import TOOLS, ToolContext

    sb = E2BSandbox("_c")
    sb.root = tmp_path
    ctx = ToolContext("_c", sb, None)
    args = {"jobs": [{"name": "a", "command": "python x.py"}], "gpu": "L4", "timeout_minutes": 10, "pip_packages": []}

    monkeypatch.setattr(cr, "configured", lambda: False)
    assert "no Colab credentials" in asyncio.run(TOOLS["run_gpu_jobs"].handler(ctx, args))
    assert "cuda_gpu" not in sb.capabilities

    monkeypatch.setattr(cr, "configured", lambda: True)
    assert "cuda_gpu" in sb.capabilities
    monkeypatch.setattr(cr, "gpu_budget", lambda pid: 10.0)
    monkeypatch.setattr(cr, "gpu_spent", lambda pid: 0.5)
    seen = {}

    async def run_async(project_id, root, jobs, gpu, timeout_s, packages):
        seen.update(project_id=project_id, gpu=gpu, timeout_s=timeout_s)
        return {"jobs": [{"name": "a", "exit_code": 0}], "files_synced_back": 1, "changed_files": ["r.csv"]}

    monkeypatch.setattr(cr, "run_async", run_async)
    out = json.loads(asyncio.run(TOOLS["run_gpu_jobs"].handler(ctx, args)))
    assert seen == {"project_id": "_c", "gpu": "L4", "timeout_s": 600}
    assert out["gpu_budget"] == {"spent": 0.5, "remaining": 9.5} and out["changed_files"] == ["r.csv"]

    assert "Unknown GPU A100-80GB; choose from T4, L4" in asyncio.run(
        TOOLS["run_gpu_jobs"].handler(ctx, {**args, "gpu": "A100-80GB"}))

    async def refused(*a):
        raise cr.ColabError("Refused: the Colab account has 11.00 compute units")

    monkeypatch.setattr(cr, "run_async", refused)
    assert asyncio.run(TOOLS["run_gpu_jobs"].handler(ctx, args)).startswith("Refused: the Colab account")

    async def rejected(*a):
        raise cr.ColabAuthError()

    monkeypatch.setattr(cr, "run_async", rejected)
    assert asyncio.run(TOOLS["run_gpu_jobs"].handler(ctx, args)) == cr.AUTH_MESSAGE


def test_startup_reaper_always_runs(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    started = []
    monkeypatch.setattr(cr, "start_reaper", lambda: started.append(1))
    monkeypatch.setenv("GPU_PROVIDER", "modal")
    with TestClient(app):
        pass
    assert started == [1]


def test_reaper_is_a_noop_without_credentials(monkeypatch):
    checked = threading.Event()
    monkeypatch.setattr(cr, "_startup_check", checked.set)
    monkeypatch.setattr(cr, "configured", lambda: False)
    cr.start_reaper()
    assert not checked.wait(0.2)  # unconfigured: no thread, no CLI call
    monkeypatch.setattr(cr, "configured", lambda: True)
    cr.start_reaper()
    assert checked.wait(5)


# ── The VM-side scripts, run for real on this machine ──────────────────────


@pytest.mark.skipif(sys.platform == "win32", reason="the VM-side steps need bash, coreutils timeout and /proc")
def test_remote_steps_locally(tmp_path):
    state, root = tmp_path / "state", tmp_path / "ws"

    def step(script, **params):
        path = tmp_path / f"step_{secrets.token_hex(3)}.py"
        path.write_text(cr._code(script, {"state": str(state), "root": str(root), **params}))
        p = subprocess.run([sys.executable, str(path)], capture_output=True, text=True, timeout=120)
        out = cr._parse(p.stdout)
        assert out is not None, p.stderr[-2000:]
        return out

    assert "gpu" in step(cr._GPUCHECK)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("data/in.txt")
        info.size = 2
        tar.addfile(info, io.BytesIO(b"3\n"))
    data = buf.getvalue()
    (state / "in" / "part_000").write_bytes(data[: len(data) // 2])
    (state / "in" / "part_001").write_bytes(data[len(data) // 2:])
    assert step(cr._SETUP, sha=hashlib.sha256(data).hexdigest(), parts=2, packages=[])["sha_ok"]
    assert (state / "environment.txt").exists()

    def run_job(name, command, timeout=30):
        assert step(cr._LAUNCH, name=name, timeout=timeout, command=command)["resumed"] is False
        return step(cr._WAIT, name=name, chunk=60)["rc"]

    assert run_job("j1", "mkdir -p results && cp data/in.txt results/out.txt && echo MPL=$MPLBACKEND") == 0
    c = step(cr._COLLECT, name="j1", part=512)
    blob = b"".join((state / "out" / "j1" / f"part_{i:03d}").read_bytes() for i in range(c["parts"]))
    assert hashlib.sha256(blob).hexdigest() == c["sha"]
    with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
        names = set(tar.getnames())
        log = tar.extractfile("logs/gpu/j1.log").read().decode()
    assert names == {"results/out.txt", "logs/gpu/j1.log", "logs/gpu/j1.log.time"}  # inputs are not re-synced
    assert "MPL=Agg" in log

    assert run_job("j2", "test ! -e results/out.txt") == 0  # every job starts from the pristine snapshot
    assert run_job("j3", "sleep 20", timeout=1) == 124  # coreutils timeout enforces the limit on the VM

    assert step(cr._LAUNCH, name="j4", timeout=600, command="sleep 300")["resumed"] is False
    pid = int((state / "jobs" / "j4.pid").read_text())
    assert step(cr._LAUNCH, name="j4", timeout=600, command="sleep 300")["resumed"] is True  # never a 2nd copy
    step(cr._KILL, name="j4")
    time.sleep(1)
    alive = [d for d in os.listdir("/proc") if d.isdigit() and _sid(int(d)) == pid]
    assert alive == []


def _sid(pid: int) -> int | None:
    try:
        return os.getsid(pid)
    except OSError:
        return None
