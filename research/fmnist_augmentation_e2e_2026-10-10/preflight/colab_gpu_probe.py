"""Minimal pre-launch Colab GPU probe through the real `run_gpu_jobs` tool handler (no LLM calls).

Isolated exactly like backend/scripts/colab_gpu_tool_check.py: throwaway SQLite DB, temp workspace
root, LLM client blocked, E2B key blank. One job: report torch's CUDA view and run a matmul on the
device. GPU spend is capped by the throwaway project's own GPU budget ($0.10 = 1 CU).
This is infrastructure verification only; nothing here belongs to the research project.
Run through colab_gpu_probe.sh.
"""
import asyncio, json, os, tempfile
from pathlib import Path

assert os.environ["DATABASE_URL"].startswith("sqlite:////tmp/"), "refusing: DATABASE_URL must be a throwaway SQLite file"

from app import llm  # noqa: E402
from app.db import BetaUser, GpuUsage, Project, engine, init_db  # noqa: E402

assert str(engine.url).startswith("sqlite:////tmp/"), f"refusing: engine is {engine.url.drivername}"


class _NoLLM:
    def __getattr__(self, name):
        raise RuntimeError("LLM call attempted during the GPU probe")


llm.client = _NoLLM()

from sqlmodel import Session, select  # noqa: E402

from app.execution import colab_runner as cr, e2b_sandbox  # noqa: E402
from app.execution.sandbox import gpu_runner, sandbox_for  # noqa: E402
from app.execution.tools import TOOLS, ToolContext  # noqa: E402

USER = "11111111-2222-3333-4444-555555555555"
PROBE = r'''
import torch, time
print("torch", torch.__version__, "cuda build", torch.version.cuda)
print("cuda_available", torch.cuda.is_available())
print("device_count", torch.cuda.device_count())
print("device_name", torch.cuda.get_device_name(0))
x = torch.randn(2048, 2048, device="cuda"); torch.cuda.synchronize(); t = time.time()
for _ in range(20): y = x @ x
torch.cuda.synchronize(); print("matmul_device", y.device, "seconds", round(time.time() - t, 4))
'''


def main() -> None:
    init_db()
    work = Path(tempfile.mkdtemp(prefix="osci-gpu-probe-"))
    e2b_sandbox.WORKSPACES = work
    with Session(engine) as s:
        s.merge(BetaUser(user_id=USER, approved=True))
        p = Project(title="_preflight_gpu_probe", user_id=USER, settings={"gpu_budget_usd": 0.10})
        s.add(p)
        s.commit()
        pid = p.id
    sb = sandbox_for(pid)
    sb.root.mkdir(parents=True)
    (sb.root / "probe.py").write_text(PROBE)
    ctx = ToolContext(pid, sb, None, agent_name="preflight-probe")
    print("gpu runner is Colab:", gpu_runner() is cr, "| configured:", cr.configured(),
          "| cuda_gpu capability:", "cuda_gpu" in sb.capabilities)
    b0, _, active0 = cr.balance()
    print(f"balance before: {b0:.2f} CU, {active0} active session(s)")
    raw = asyncio.run(TOOLS["run_gpu_jobs"].handler(ctx, {"jobs": [{"name": "probe", "command": "python probe.py"}],
                                                         "gpu": "T4", "timeout_minutes": 5, "pip_packages": []}))
    out = json.loads(raw)
    for job in out.get("jobs", []):
        print(json.dumps({k: job.get(k) for k in ("name", "exit_code", "seconds", "timed_out", "cost", "error")}))
    for rel in ("logs/gpu/probe.log", "logs/gpu/_environment.txt"):
        f = sb.root / rel
        print(f"--- {rel}\n" + (f.read_text(errors="replace") if f.exists() else "(missing)"))
    with Session(engine) as s:
        rows = s.exec(select(GpuUsage).where(GpuUsage.project_id == pid)).all()
    print("GpuUsage rows:", [(r.job, r.gpu, round(r.seconds, 1), round(r.cost, 4)) for r in rows])
    print("server sessions after:", cr._cli(["sessions"], 120)[1].strip()[:80])
    print("ledger files after:", len(list((cr.COLAB_HOME / "sessions").iterdir())))


if __name__ == "__main__":
    main()
