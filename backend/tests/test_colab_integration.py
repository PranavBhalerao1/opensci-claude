"""Real Colab runs of the GPU runner (network; uses compute units — needs your approval per tier).

Run on Linux/macOS with the backend's environment:
    COLAB_INTEGRATION=1 COLAB_CREDENTIALS_FILE=~/.openscientist/colab/credentials.json \\
    COLAB_TEST_TIER=core COLAB_TEST_MAX_CU=3 uv run pytest -q tests/test_colab_integration.py -s

Tiers: `core` (protocol scenarios on CPU runtimes at ~0.08 CU/h, one L4 CUDA job) and `long`
(the decay-clock reference experiment on L4 and a 45-minute GPU job). A session-wide guard skips
every remaining test once spend (the larger of the balance drop and the metered GpuUsage cost)
exceeds COLAB_TEST_MAX_CU. The database is the suite's temporary SQLite (conftest).
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import textwrap
import threading
import time
import uuid
from pathlib import Path

import pytest
from sqlmodel import Session, func, select

from app.config import settings
from app.db import GpuUsage, Project, engine
from app.execution import colab_runner as cr

TIER = os.environ.get("COLAB_TEST_TIER", "core")
MAX_CU = float(os.environ.get("COLAB_TEST_MAX_CU", "3"))
REPO = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(
    os.environ.get("COLAB_INTEGRATION") != "1" or sys.platform == "win32" or not cr.configured(),
    reason="set COLAB_INTEGRATION=1 and COLAB_CREDENTIALS_FILE on Linux/macOS to run against real Colab",
)


def _step(name: str, t0: float) -> None:
    print(f"  ✓ {name} ({time.monotonic() - t0:.0f}s)")


@pytest.fixture(scope="module")
def budget():
    start = cr.balance()[0]
    state = {"start": start}
    yield state
    end = cr.balance()[0]
    print(f"\nColab test spend: balance {start:.2f} → {end:.2f} (may lag by minutes); metered {_metered_cu():.3f} CU")


def _metered_cu() -> float:
    with Session(engine) as s:
        return float(s.exec(select(func.coalesce(func.sum(GpuUsage.cost), 0.0))).one()) / cr.USD_PER_CU


@pytest.fixture(autouse=True)
def guard(budget):
    spent = max(budget["start"] - cr.balance()[0], _metered_cu())
    if spent > MAX_CU:
        pytest.skip(f"Colab test budget exhausted: {spent:.2f} CU > COLAB_TEST_MAX_CU={MAX_CU}")
    yield
    time.sleep(5)  # a leftover CLI process would rewrite session state about now
    left = [p.name for p in (cr.COLAB_HOME / "sessions").iterdir()]  # names only: state files hold proxy tokens
    assert not left, f"a test left Colab session state behind: {left}"


@pytest.fixture
def project(tmp_path):
    with Session(engine) as s:
        p = Project(title="_colab_live", settings={"gpu_budget_usd": 2.0})
        s.add(p)
        s.commit()
        pid = p.id
    root = tmp_path / "ws"
    root.mkdir()
    return pid, root


@pytest.fixture
def cpu(monkeypatch):
    """Protocol scenarios on a CPU runtime (~0.08 CU/h): no --gpu flag and no GPU check. Test-only."""
    monkeypatch.setitem(cr.CU_PER_HOUR, "CPU", 0.08)
    monkeypatch.setitem(cr.GPU_PRICES, "CPU", 0.08 * cr.USD_PER_CU / 3600)
    monkeypatch.setattr(cr, "_GPUCHECK", 'import os\nfor d in ("in", "jobs", "out"):\n'
                                         '    os.makedirs(P["state"] + "/" + d, exist_ok=True)\nOUT = {"gpu": "CPU"}\n')
    real = cr._cli

    def cli(args, timeout, session=None):
        if args[:1] == ["new"] and "--gpu" in args and args[args.index("--gpu") + 1] == "CPU":
            args = args[: args.index("--gpu")]
        return real(args, timeout, session)

    monkeypatch.setattr(cr, "_cli", cli)
    return "CPU"


def _jobs(**commands: str) -> list[dict]:
    return [{"name": n, "command": c} for n, c in commands.items()]


def _server_sessions() -> str:
    return cr._cli(["sessions"], 120)[1]


# ── core ───────────────────────────────────────────────────────────────────


@pytest.mark.skipif(TIER not in ("core", "all"), reason="core tier")
def test_cuda_job_with_artifacts_on_l4(project):
    pid, root = project
    (root / "data").mkdir()
    (root / "data" / "input.txt").write_text("1\n2\n3\n")
    (root / "train.py").write_text(textwrap.dedent("""
        import json, os, numpy as np, torch, matplotlib.pyplot as plt
        assert torch.cuda.is_available(), "no CUDA"
        x = torch.tensor(np.loadtxt("data/input.txt"), device="cuda").float()
        os.makedirs("results", exist_ok=True); os.makedirs("figures", exist_ok=True); os.makedirs("ckpt", exist_ok=True)
        json.dump({"sum": float(x.sum()), "device": torch.cuda.get_device_name(0), "mpl": os.environ.get("MPLBACKEND")},
                  open("results/metrics.json", "w"))
        open("results/rows.csv", "w").write("i,v\\n" + "".join(f"{i},{v}\\n" for i, v in enumerate(x.tolist())))
        plt.plot(x.cpu()); plt.savefig("figures/fig.png")
        torch.save(torch.nn.Linear(4, 2).cuda().state_dict(), "ckpt/model.pt")
        print("done")
    """))
    t0 = time.monotonic()
    out = cr.run_jobs(pid, root, _jobs(train="python train.py"), "L4", 600, [])
    job = out["jobs"][0]
    assert job["exit_code"] == 0 and job["timed_out"] is False, job
    metrics = json.loads((root / "results" / "metrics.json").read_text())
    assert metrics["sum"] == 6.0 and "L4" in metrics["device"] and metrics["mpl"] == "Agg"
    assert (root / "figures" / "fig.png").read_bytes()[:4] == b"\x89PNG"
    assert (root / "ckpt" / "model.pt").read_bytes()[:2] == b"PK"
    assert "NVIDIA L4" in job["log_tail"] and (root / "logs" / "gpu" / "train.log.time").exists()
    assert (root / "logs" / "gpu" / "_environment.txt").read_text().startswith("Python")
    assert "data/input.txt" not in out["changed_files"]
    _step(f"L4 CUDA job: CSV/JSON/PNG/checkpoint synced, {job['seconds']}s run, ${job['cost']}", t0)


@pytest.mark.skipif(TIER not in ("core", "all"), reason="core tier")
def test_job_semantics_on_cpu(project, cpu):
    pid, root = project
    (root / "data.txt").write_text("input\n")
    t0 = time.monotonic()
    out = cr.run_jobs(pid, root, _jobs(
        marker="echo one > marker.txt && cat data.txt",
        fresh="test ! -e marker.txt",  # every job starts from the pristine workspace
        exit3="python -c 'import sys; sys.exit(3)'",
        boom="python -c 'raise ValueError(\"boom-xyz\")'",
        big="python -c \"import os; open('big.bin', 'wb').write(os.urandom(200 * 1024 * 1024))\"",
    ), cpu, 600, [])
    by = {j["name"]: j for j in out["jobs"]}
    assert by["marker"]["exit_code"] == 0 and "input" in by["marker"]["log_tail"]
    assert by["fresh"]["exit_code"] == 0
    assert by["exit3"]["exit_code"] == 3
    assert by["boom"]["exit_code"] == 1 and "boom-xyz" in by["boom"]["log_tail"]
    assert by["big"]["exit_code"] == 0 and (root / "big.bin").stat().st_size == 200 * 1024 * 1024
    _step("exit codes, tracebacks, fresh snapshot per job, 200 MB output in 7 parts", t0)


@pytest.mark.skipif(TIER not in ("core", "all"), reason="core tier")
def test_timeout_and_bad_packages_on_cpu(project, cpu):
    pid, root = project
    t0 = time.monotonic()
    job = cr.run_jobs(pid, root, _jobs(slow="echo partial > partial.txt && sleep 600"), cpu, 60, [])["jobs"][0]
    assert job["timed_out"] is True and job["exit_code"] == 124 and (root / "partial.txt").exists(), job
    _step("timeout enforced on the VM; partial output synced", t0)
    t0 = time.monotonic()
    jobs = cr.run_jobs(pid, root, _jobs(a="true", b="true"), cpu, 60, ["openscientist-no-such-package==0.0.1"])["jobs"]
    assert all("pip install failed" in j["error"] for j in jobs), jobs
    _step("failed pip install reported for every job", t0)


@pytest.mark.skipif(TIER not in ("core", "all"), reason="core tier")
def test_lost_runtime_is_never_success(project, cpu):
    pid, root = project
    result = {}
    t = threading.Thread(target=lambda: result.update(cr.run_jobs(pid, root, _jobs(long="sleep 900"), cpu, 1200, [])))
    t0 = time.monotonic()
    t.start()
    owner = _wait_for(lambda: next((cr.COLAB_HOME / "sessions").glob("*.owner"), None), 300)
    time.sleep(40)  # launched and waiting
    cr._cli(["stop", "-s", owner.stem], 120, owner.stem)  # the VM disappears under the job
    t.join(600)
    job = result["jobs"][0]
    assert job["exit_code"] is None and "lost" in job["error"], job
    _step("runtime lost mid-job reported as lost", t0)


@pytest.mark.skipif(TIER not in ("core", "all"), reason="core tier")
def test_crashed_backend_session_is_reaped(project, cpu, tmp_path):
    pid, root = project
    script = tmp_path / "victim.py"
    script.write_text(textwrap.dedent(f"""
        from app.execution import colab_runner as cr
        cr.CU_PER_HOUR["CPU"] = 0.08; cr.GPU_PRICES["CPU"] = 0.08 * cr.USD_PER_CU / 3600
        cr._GPUCHECK = {cr._GPUCHECK!r}
        real = cr._cli
        def cli(args, timeout, session=None):
            if args[:1] == ["new"]:
                args = args[:args.index("--gpu")]
            return real(args, timeout, session)
        cr._cli = cli
        cr.run_jobs({pid!r}, {str(root)!r}, [{{"name": "v", "command": "sleep 900"}}], "CPU", 1200, [])
    """))
    t0 = time.monotonic()
    victim = subprocess.Popen([sys.executable, str(script)], cwd=REPO / "backend",
                              env={**os.environ, "PYTHONPATH": str(REPO / "backend")})
    owner = _wait_for(lambda: next((cr.COLAB_HOME / "sessions").glob("*.owner"), None), 300)
    time.sleep(30)
    victim.kill()  # kill -9: no finally, no cleanup
    victim.wait()
    assert owner.exists()
    assert cr.reap() == 1 and not owner.exists()
    _step("kill -9 of the backend: the reaper stopped its session", t0)


@pytest.mark.skipif(TIER not in ("core", "all"), reason="core tier")
def test_cancel_stops_the_session(project, cpu):
    pid, root = project

    async def go():
        task = asyncio.create_task(cr.run_async(pid, root, _jobs(long="sleep 900"), cpu, 1200, []))
        await asyncio.to_thread(_wait_for, lambda: next((cr.COLAB_HOME / "sessions").glob("*.owner"), None), 300)
        await asyncio.sleep(40)
        t0 = time.monotonic()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return time.monotonic() - t0

    took = asyncio.run(go())
    assert took < 180 and not list((cr.COLAB_HOME / "sessions").glob("*.owner"))
    _step(f"cancellation stopped the job and its VM in {took:.0f}s", time.monotonic())


@pytest.mark.skipif(TIER not in ("core", "all"), reason="core tier")
def test_end_state_no_sessions_left():
    assert "No active sessions" in _server_sessions(), _server_sessions()
    assert cr.balance()[2] == 0


# ── long ───────────────────────────────────────────────────────────────────


@pytest.mark.skipif(TIER not in ("long", "all"), reason="long tier")
def test_reference_experiment_matches_modal(project):
    """research/decay_clock: the same run that Modal produced (8 runs shared one L4 there)."""
    pid, root = project
    shutil.copy(REPO / "research" / "decay_clock" / "grok.py", root / "grok.py")
    ref = json.loads((REPO / "research" / "decay_clock" / "runs" / "add_const1.0_s0" / "summary.json").read_text())
    t0 = time.monotonic()
    job = cr.run_jobs(pid, root, _jobs(grok="python grok.py add_const1.0_s0 add const1.0 0 50000 out"),
                      "L4", 40 * 60, [])["jobs"][0]
    assert job["exit_code"] == 0, job
    got = json.loads((root / "out" / "add_const1.0_s0" / "summary.json").read_text())
    assert got["device"] == "cuda" and got["final_test_acc"] >= 0.99
    assert abs(got["t_gen"] - ref["t_gen"]) <= 0.25 * ref["t_gen"], (got["t_gen"], ref["t_gen"])
    _step(f"grokking reproduced: t_gen {got['t_gen']} vs Modal {ref['t_gen']}, acc {got['final_test_acc']:.4f}, "
          f"{job['seconds']}s, ${job['cost']}", t0)


@pytest.mark.skipif(TIER not in ("long", "all"), reason="long tier")
def test_gpu_job_survives_45_minutes(project):
    pid, root = project
    (root / "burn.py").write_text(textwrap.dedent("""
        import time, torch
        a, end, n = torch.randn(2048, 2048, device="cuda"), time.time() + 45 * 60, 0
        while time.time() < end:
            for _ in range(50): a = (a @ a).tanh()
            torch.cuda.synchronize(); n += 1
            if n % 2000 == 0: print("alive", int(time.time()), flush=True)
        open("survived.txt", "w").write("yes")
    """))
    t0 = time.monotonic()
    gpu = os.environ.get("COLAB_TEST_LONG_GPU", "T4")
    job = cr.run_jobs(pid, root, _jobs(burn="python burn.py"), gpu, 60 * 60, [])["jobs"][0]
    assert job["exit_code"] == 0 and job["seconds"] >= 45 * 60 and (root / "survived.txt").exists(), job
    _step(f"{gpu} job ran {job['seconds'] / 60:.0f} min under polling, ${job['cost']}", t0)


def _wait_for(probe, timeout: float):
    end = time.time() + timeout
    while time.time() < end:
        found = probe()
        if found:
            return found
        time.sleep(2)
    raise AssertionError("timed out waiting")
