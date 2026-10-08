"""Isolated integration test of the real `run_gpu_jobs` tool handler on Colab (no LLM calls).

Runs as a fresh backend process with stored ADC credentials. Everything it writes goes to a temp
SQLite DB and a temp workspace dir; it refuses to start otherwise. GPU spend is capped by the test
project's own GPU budget ($0.10 = 1 CU), i.e. by the product's existing guard, plus a balance check.
Prints only tool results, job logs and summaries — never CLI state or credentials.
Run it through colab_gpu_tool_check.sh, which sets the environment (see docs/colab-gpu.md).
"""

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

DB = os.environ["DATABASE_URL"]
assert DB.startswith("sqlite:////tmp/"), "refusing to run: DATABASE_URL must be a throwaway SQLite file"

from app import llm  # noqa: E402
from app.db import BetaUser, GpuUsage, Project, engine, init_db  # noqa: E402

assert str(engine.url).startswith("sqlite:////tmp/"), f"refusing to run: engine is {engine.url.drivername}"


class _NoLLM:
    def __getattr__(self, name):
        raise RuntimeError("LLM call attempted during the GPU tool test")


llm.client = _NoLLM()  # any Bedrock use would fail loudly

from sqlmodel import Session, select  # noqa: E402

from app.execution import colab_runner as cr, e2b_sandbox  # noqa: E402
from app.execution.sandbox import gpu_runner, sandbox_for  # noqa: E402
from app.execution.tools import TOOLS, ToolContext  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []
MODAL_JOB_KEYS = {"name", "exit_code", "seconds", "log", "timed_out", "log_tail", "wall_seconds", "cost"}
MODAL_ERROR_KEYS = {"name", "exit_code", "error", "seconds", "log", "log_tail", "wall_seconds", "cost"}
USER = "11111111-2222-3333-4444-555555555555"


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""), flush=True)
    return bool(ok)


def clean_state(label: str) -> None:
    out = cr._cli(["sessions"], 120)[1]
    left = [p.name for p in (cr.COLAB_HOME / "sessions").iterdir()]
    check(f"{label}: Colab session terminated (server lists none, ledger empty)",
          "No active sessions" in out and not left, f"server: {out.strip()[:60]}; ledger files: {len(left)}")


def spend_ok(b0: float) -> None:
    metered = sum(r.cost for r in Session(engine).exec(select(GpuUsage))) / cr.USD_PER_CU
    bal = cr.balance()[0]
    if max(b0 - bal, metered) >= 1.0:
        print(f"ABORT: spend reached {max(b0 - bal, metered):.2f} CU")
        sys.exit(2)


async def tool(ctx, **args) -> str:
    """Exactly what the agent loop does: the JSON arguments dict to the registered handler."""
    return await TOOLS["run_gpu_jobs"].handler(ctx, json.loads(json.dumps(args)))


TRAIN = r'''
import json, os, numpy as np, torch, matplotlib.pyplot as plt
torch.manual_seed(0)
d = torch.device("cuda")
x = torch.tensor(np.loadtxt("data/input.csv", delimiter=",", skiprows=1), dtype=torch.float32, device=d)
X, y = x[:, :1], x[:, 1:]
net = torch.nn.Sequential(torch.nn.Linear(1, 64), torch.nn.Tanh(), torch.nn.Linear(64, 1)).to(d)
opt = torch.optim.Adam(net.parameters(), 1e-2)
losses = []
for step in range(500):
    opt.zero_grad(); loss = ((net(X) - y) ** 2).mean(); loss.backward(); opt.step(); losses.append(loss.item())
os.makedirs("results", exist_ok=True); os.makedirs("figures", exist_ok=True); os.makedirs("ckpt", exist_ok=True)
open("results/curve.csv", "w").write("step,loss\n" + "".join(f"{i},{l:.6f}\n" for i, l in enumerate(losses)))
json.dump({"final_loss": losses[-1], "steps": 500, "device": torch.cuda.get_device_name(0), "seed": 0,
           "torch": torch.__version__}, open("results/metrics.json", "w"), indent=2)
plt.plot(losses); plt.yscale("log"); plt.xlabel("step"); plt.ylabel("MSE"); plt.savefig("figures/loss.png")
torch.save(net.state_dict(), "ckpt/model.pt")
print("final loss", losses[-1], "on", torch.cuda.get_device_name(0))
'''


def main() -> None:
    init_db()
    work = Path(tempfile.mkdtemp(prefix="osci-gpu-it-"))
    e2b_sandbox.WORKSPACES = work  # isolated workspaces; no real project is touched
    with Session(engine) as s:
        s.merge(BetaUser(user_id=USER, approved=True))
        p = Project(title="_gpu_tool_integration_test", user_id=USER, settings={"gpu_budget_usd": 0.10})
        s.add(p)
        s.commit()
        pid = p.id
    sb = sandbox_for(pid)
    sb.root.mkdir(parents=True)
    (sb.root / "data").mkdir()
    (sb.root / "data" / "input.csv").write_text("x,y\n" + "".join(f"{i / 50:.3f},{(i / 50) ** 2:.4f}\n" for i in range(100)))
    (sb.root / "train.py").write_text(TRAIN)
    ctx = ToolContext(pid, sb, None, agent_name="integration-test")

    print("\n[1] Fresh process, stored ADC credentials, no interactive login")
    check("GPU provider is Colab and configured (CLI + credentials file present)",
          gpu_runner() is cr and cr.configured() and "cuda_gpu" in sb.capabilities)
    b0, _, active0 = cr.balance()
    check("Authenticated headless (stdin closed) and read the compute-unit balance", b0 > cr.MIN_BALANCE_CU,
          f"{b0:.2f} CU, {active0} active session(s)")
    check("run_gpu_jobs is offered to agents with the Colab spec",
          "Google Colab" in TOOLS["run_gpu_jobs"].description
          and TOOLS["run_gpu_jobs"].parameters["properties"]["gpu"]["enum"] == ["T4", "L4"])

    print("\n[2] Refusals happen before any GPU is allocated")
    out = asyncio.run(tool(ctx, jobs=[{"name": "x", "command": "true"}], gpu="A100-80GB", pip_packages=[]))
    check("Unavailable GPU type rejected with the agent-facing message", out.startswith("Unknown GPU A100-80GB"), out)
    out = asyncio.run(tool(ctx, jobs=[{"name": f"j{i}", "command": "true"} for i in range(40)], gpu="L4",
                           timeout_minutes=180, pip_packages=[]))
    check("Over-budget request refused by the existing budget guard", out.startswith("Refused:"), out[:120])
    clean_state("after refusals")

    print("\n[3] Real PyTorch experiment + a crashing job, through the tool handler (L4)")
    t0 = time.time()
    raw = asyncio.run(tool(ctx, jobs=[{"name": "train", "command": "python train.py"},
                                      {"name": "crash", "command": "python -c \"raise ValueError('intentional')\""}],
                           gpu="L4", timeout_minutes=10, pip_packages=[]))
    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        check("Tool returned JSON", False, raw[:300])
        return finish(pid, work, b0)
    print(f"      ({time.time() - t0:.0f}s) tool output:")
    print(textwrap_indent(json.dumps(out, indent=2)[:3000]))
    check("Top-level output structure = Modal's + gpu_budget",
          set(out) == {"jobs", "files_synced_back", "changed_files", "gpu_budget"}, str(sorted(out)))
    train, crash = out["jobs"]
    check("Per-job structure identical to Modal's success shape", set(train) == MODAL_JOB_KEYS == set(crash),
          str(sorted(train)))
    check("Experiment succeeded on the GPU", train["exit_code"] == 0 and train["timed_out"] is False
          and "NVIDIA L4" in train["log_tail"] and "final loss" in train["log_tail"])
    check("Failing job reported as failure with its traceback (not success)",
          crash["exit_code"] == 1 and "intentional" in crash["log_tail"])
    check("Usage accounting in the tool result", out["gpu_budget"]["spent"] > 0 and out["gpu_budget"]["remaining"] < 0.10,
          json.dumps(out["gpu_budget"]))
    for rel in ("results/curve.csv", "results/metrics.json", "figures/loss.png", "ckpt/model.pt",
                "logs/gpu/train.log", "logs/gpu/train.log.time", "logs/gpu/crash.log", "logs/gpu/_environment.txt"):
        check(f"artifact synced to the workspace: {rel}", sb.path(rel).is_file(), f"{sb.path(rel).stat().st_size} B"
              if sb.path(rel).is_file() else "missing")
    metrics = json.loads(sb.path("results/metrics.json").read_text())
    check("JSON metrics written by CUDA code", "L4" in metrics["device"] and metrics["final_loss"] < 0.01,
          json.dumps(metrics))
    check("Input data not re-synced as an output", "data/input.csv" not in out["changed_files"])
    report = asyncio.run(TOOLS["report_result"].handler(ctx, {
        "status": "success", "summary": "GPU tool integration test",
        "artifacts": ["results/curve.csv", "results/metrics.json", "figures/loss.png", "logs/gpu/train.log"]}))
    check("Orchestrator's artifact check (report_result) accepts the synced files", report == "Result recorded.", report)
    clean_state("after the experiment")
    spend_ok(b0)

    print("\n[4] Error after allocation: failing pip install")
    out = json.loads(asyncio.run(tool(ctx, jobs=[{"name": "a", "command": "python train.py"}], gpu="L4",
                                      timeout_minutes=5, pip_packages=["openscientist-no-such-package==0.0.1"])))
    job = out["jobs"][0]
    check("Setup failure reported in Modal's error shape", set(job) == MODAL_ERROR_KEYS and "pip install failed" in job["error"],
          job.get("error", "")[:120])
    clean_state("after the setup error")
    spend_ok(b0)

    print("\n[5] Timeout enforced on the VM")
    out = json.loads(asyncio.run(tool(ctx, jobs=[{"name": "slow", "command": "echo started > partial.txt && sleep 600"}],
                                      gpu="L4", timeout_minutes=1, pip_packages=[])))
    job = out["jobs"][0]
    check("Job past its timeout reported as timed out (exit 124), partial output synced",
          job["timed_out"] is True and job["exit_code"] == 124 and sb.path("partial.txt").exists(),
          f"exit {job['exit_code']}, {job['seconds']}s")
    clean_state("after the timeout")

    finish(pid, work, b0)


def finish(pid: str, work: Path, b0: float) -> None:
    print("\n[6] Existing artifact workflow and usage accounting (FastAPI routes, auth overridden to the test user)")
    from fastapi.testclient import TestClient

    from app.auth import CurrentUser, get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=USER, email="test@example.invalid")
    with TestClient(app) as client:
        files = {f["path"] for f in client.get(f"/api/projects/{pid}/workspace/files").json()}
        want = {"results/curve.csv", "results/metrics.json", "figures/loss.png", "logs/gpu/train.log",
                "logs/gpu/_environment.txt", "ckpt/model.pt"}
        check("Workspace browser lists the GPU outputs", want <= files, f"{len(files)} files")
        png = client.get(f"/api/projects/{pid}/workspace/file", params={"path": "figures/loss.png"})
        check("PNG served by the workspace file route", png.status_code == 200 and png.content[:4] == b"\x89PNG")
        csv = client.get(f"/api/projects/{pid}/workspace/file", params={"path": "results/curve.csv"})
        check("CSV served by the workspace file route", csv.status_code == 200 and csv.text.startswith("step,loss"))
        usage = client.get(f"/api/projects/{pid}/usage").json()
        check("Notebook usage API reports GPU spend and budget", usage["gpu"]["spent"] > 0 and usage["gpu"]["budget"] <= 0.10,
              json.dumps(usage["gpu"]))
    with Session(engine) as s:
        rows = s.exec(select(GpuUsage).where(GpuUsage.project_id == pid)).all()
    jobs = sorted({r.job for r in rows})
    metered = sum(r.cost for r in rows) / cr.USD_PER_CU
    check("GpuUsage ledger rows written (per job + session overhead)", "train" in jobs and "(session overhead)" in jobs,
          f"{len(rows)} rows: {jobs}")
    time.sleep(60)  # the compute-unit balance updates with a lag
    b1, _, active = cr.balance()
    check("Total GPU spend below 1 compute unit", max(b0 - b1, metered) < 1.0,
          f"metered {metered:.3f} CU; balance {b0:.2f} -> {b1:.2f}")
    check("No active Colab assignments at the end", active == 0)
    print(f"\nSUMMARY: {sum(ok for _, ok, _ in RESULTS)} passed, {sum(not ok for _, ok, _ in RESULTS)} failed")
    for name, ok, _ in RESULTS:
        if not ok:
            print(f"  FAILED: {name}")


def textwrap_indent(text: str) -> str:
    return "\n".join("      " + line for line in text.splitlines())


if __name__ == "__main__":
    main()
