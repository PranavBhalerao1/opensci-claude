"""Real E2B run of the sandbox through the agent tools (network; uses E2B credits).

Run with:  E2B_INTEGRATION=1 uv run pytest -q tests/test_e2b_integration.py -s
"""

import asyncio
import os
import re
import shutil
import time
import uuid
import zipfile

import pytest

from app.config import settings

pytestmark = pytest.mark.skipif(
    os.environ.get("E2B_INTEGRATION") != "1" or not settings.e2b_api_key,
    reason="set E2B_INTEGRATION=1 and E2B_API_KEY to run against real E2B",
)


def _step(name: str, t0: float) -> None:
    print(f"  ✓ {name} ({time.monotonic() - t0:.1f}s)")


async def _scenario(sb, pid: str) -> None:
    from app.agents import report
    from app.execution import orchestrator
    from app.execution.tools import TOOLS, ToolContext

    ctx = ToolContext(pid, sb, None)

    async def tool(tool_name: str, **args) -> str:
        return await TOOLS[tool_name].handler(ctx, args)

    t0 = time.monotonic()
    await sb.ensure()
    _step("sandbox created, venv + base packages installed", t0)

    # Host → E2B → host: a host-written input is read remotely; remote outputs come back.
    t0 = time.monotonic()
    await tool("write_file", path="data/input.txt", content="3\n4\n5\n")
    out = await tool("run_python", code=(
        "import platform, numpy as np, pandas as pd, matplotlib.pyplot as plt, os\n"
        "x = np.loadtxt('data/input.txt')\n"
        "os.makedirs('results', exist_ok=True); os.makedirs('figures', exist_ok=True)\n"
        "pd.DataFrame({'x': x, 'sq': x**2}).to_csv('results/out.csv', index=False)\n"
        "plt.plot(x, x**2); plt.savefig('figures/fig.png')\n"
        "print('sum', x.sum(), platform.system(), os.getcwd())\n"))
    assert "exit_code: 0" in out and "sum 12.0 Linux /home/user/workspace" in out, out
    assert sb.path("results/out.csv").read_text().splitlines()[1] == "3.0,9.0"
    assert sb.path("figures/fig.png").read_bytes()[:4] == b"\x89PNG"
    _step("run_python: host input read remotely; CSV + figure synced back", t0)

    # Remote deletions and new files propagate; exit codes and stderr surface.
    t0 = time.monotonic()
    out = await tool("run_shell", command="rm results/out.csv && echo hi > results/new.txt && echo oops >&2 && exit 3")
    assert "exit_code: 3" in out and "oops" in out, out
    assert not sb.path("results/out.csv").exists() and sb.path("results/new.txt").read_text() == "hi\n"
    _step("run_shell: deletion + new file synced, exit code and stderr reported", t0)

    # Host-side edits made between commands are pushed.
    t0 = time.monotonic()
    await tool("edit_file", path="results/new.txt", old="hi", new="edited")
    out = await tool("run_shell", command="cat results/new.txt")
    assert "edited" in out, out
    _step("edit_file on host pushed before the next command", t0)

    t0 = time.monotonic()
    out = await tool("run_shell", command="sleep 30", timeout_seconds=3)
    assert "(timed out)" in out, out
    _step("timeouts kill the remote command", t0)

    t0 = time.monotonic()
    sb.secrets = {"MY_SERVICE_KEY": "abc123"}
    out = await tool("run_shell", command="echo key=$MY_SERVICE_KEY; echo aws=${AWS_SECRET_ACCESS_KEY:-none}; "
                                          "echo tavily=${TAVILY_API_KEY:-none}")
    assert "key=abc123" in out and "aws=none" in out and "tavily=none" in out, out
    _step("project credentials exposed, host secrets not", t0)

    t0 = time.monotonic()
    out = await tool("install_packages", packages=["tabulate"])
    assert "exit_code: 0" in out, out
    out = await tool("run_python", code="import tabulate; print(tabulate.tabulate([[1, 2]]))")
    assert "exit_code: 0" in out, out
    out = await tool("run_shell", command="python -c 'import sys, numpy, tabulate; print(sys.prefix)' && pip --version")
    assert "exit_code: 0" in out and "/home/user/.venv" in out, out
    _step("install_packages (pip) into the sandbox venv; plain python/pip in run_shell use it", t0)

    # Background process: output file and log come back via check_process and via pull().
    t0 = time.monotonic()
    out = await tool("start_process", name="bg", command="echo started; sleep 4; echo done > results/bg.txt; echo finished")
    assert re.fullmatch(r"Started bg \(pid \d+\); logs in \.logs/bg\.log", out), out  # same wording as before E2B
    assert "running" in await tool("check_process", name="bg")
    for _ in range(30):
        await asyncio.sleep(1)
        await sb.pull()  # what the workspace browser and package export do
        if sb.path("results/bg.txt").exists():
            break
    assert sb.path("results/bg.txt").read_text() == "done\n"
    status = await tool("check_process", name="bg")
    assert "exited with code 0" in status and "finished" in status, status
    out = await tool("start_process", name="long", command="sleep 300")
    assert "Sent SIGTERM" in await tool("stop_process", name="long")
    _step("start/check/stop_process with synced outputs", t0)

    # Platform-run pytest used by task verification.
    t0 = time.monotonic()
    await tool("write_file", path="src/mathx.py", content="def sq(x):\n    return x * x\n")
    await tool("write_file", path="tests/test_mathx.py", content=(
        "import sys; sys.path.insert(0, 'src')\nfrom mathx import sq\n\ndef test_sq():\n    assert sq(3) == 9\n"))
    facts = await orchestrator._run_tests(sb, [{"path": "tests/test_mathx.py"}])
    assert "exit code 0" in facts, facts
    _step("orchestrator pytest verification runs in E2B", t0)

    # No size cap (there was none before E2B): >500 MB files sync both ways (zeros compress, so this is quick).
    t0 = time.monotonic()
    big = 520 * 1024**2
    with sb.path("data/big_in.bin").open("wb") as f:
        f.truncate(big)
    out = await tool("run_shell", command="stat -c %s data/big_in.bin && head -c 545259520 /dev/zero > results/big_out.bin")
    assert "exit_code: 0" in out and str(big) in out, out
    assert sb.path("results/big_out.bin").stat().st_size == big
    await tool("run_shell", command="rm data/big_in.bin results/big_out.bin")
    assert not sb.path("results/big_out.bin").exists()
    sb.path("data/big_in.bin").unlink(missing_ok=True)
    _step("520 MB files synced host→E2B and E2B→host", t0)

    # Parallel tasks and sub-agents share one sandbox; every command's outputs must come back.
    t0 = time.monotonic()
    outs = await asyncio.gather(*(tool("run_shell", command=f"sleep 1; seq {i} > results/par_{i}.txt")
                                  for i in range(1, 7)))
    assert all("exit_code: 0" in o for o in outs), outs
    assert all(sb.path(f"results/par_{i}.txt").read_text().split()[-1] == str(i) for i in range(1, 7))
    _step("6 concurrent commands, all outputs synced", t0)

    # Conda (micromamba) software and a LaTeX compile, as the Report Agent does it.
    t0 = time.monotonic()
    out = await tool("install_conda_packages", packages=["tectonic"])
    assert "exit_code: 0" in out, out
    await tool("write_file", path="report/paper.tex", content=(
        "\\documentclass{article}\\begin{document}Hello from E2B.\\end{document}\n"))
    out = await tool("run_shell", command="cd report && tectonic paper.tex", timeout_seconds=600)
    assert "exit_code: 0" in out, out
    assert sb.path("report/paper.pdf").read_bytes()[:4] == b"%PDF"
    _step("install_conda_packages + tectonic paper compile, PDF synced back", t0)

    t0 = time.monotonic()
    zpath = report.package(pid)
    names = zipfile.ZipFile(zpath).namelist()
    assert f"{pid}/report/paper.pdf" in names and f"{pid}/figures/fig.png" in names, names
    assert not any("/.venv/" in n for n in names)
    zpath.unlink()
    _step("package export includes files produced in E2B", t0)

    # A dead sandbox is recreated from the host copy, with installed packages replayed.
    t0 = time.monotonic()
    await sb._sbx.kill()
    out = await tool("run_python", code="import tabulate, pathlib; print(pathlib.Path('results/bg.txt').read_text())")
    assert "exit_code: 0" in out and "done" in out, out
    _step("expired sandbox recreated from the host workspace", t0)


async def _fence_scenario(sb, pid: str) -> None:
    """A retry boundary in a real sandbox: attempt 1's processes are stopped and can never publish;
    attempt 2's own output is accepted; attempt 1's leftover output is not."""
    from app.execution.tools import TOOLS, ToolContext

    async def tool(ctx, tool_name: str, **args) -> str:
        return await TOOLS[tool_name].handler(ctx, args)

    t0 = time.monotonic()
    await sb.ensure()
    _step("sandbox created", t0)

    t0 = time.monotonic()
    a1 = ToolContext(pid, sb, None, owner="T2.2")
    other = ToolContext(pid, sb, None, owner="T9")
    wait_go = "while [ ! -f go ]; do sleep 0.2; done"
    await tool(a1, "write_file", path="src/runner.py", content="print('v1')\n")
    out = await tool(a1, "run_shell", command="mkdir -p data && echo leftover-v1 > data/left.txt")
    assert "exit_code: 0" in out, out
    out = await tool(a1, "start_process", name="run", command=f"{wait_go}; echo stale > data/out.txt")
    assert out.startswith("Started run"), out
    # An untracked job: detached into its own session, with a child that clears its environment.
    out = await tool(a1, "run_shell", command=(
        "nohup setsid bash -c 'env -i /bin/sh -c \"while [ ! -f go ]; do /bin/sleep 0.2; done; "
        "echo stale2 > data/out2.txt\" & sleep 600' >/dev/null 2>&1 & echo started"))
    assert "started" in out, out
    await tool(other, "start_process", name="other", command=f"{wait_go}; echo other > data/other.txt")
    out = await tool(a1, "run_shell", command="grep -lzx OPENSCI_TASK=T2.2 /proc/[0-9]*/environ 2>/dev/null | wc -l")
    assert int(out.split("stdout:\n")[1].split()[0]) >= 3, out  # the tag reached detached processes
    _step("attempt 1: tagged start_process job, detached run_shell job and a leftover output", t0)

    t0 = time.monotonic()
    paths = ["data/out.txt", "data/out2.txt", "data/left.txt"]
    fence = await sb.fence("T2.2", paths)
    assert fence.clean and fence.leftovers() == ["data/left.txt"]
    res = await sb._sh("grep -lzx OPENSCI_TASK=T2.2 /proc/[0-9]*/environ 2>/dev/null | wc -l", 30)
    assert res.stdout.strip() == "0", res  # nothing of attempt 1 is left that could write ...
    res = await sb._sh("for f in /proc/[0-9]*/cmdline; do tr '\\0' ' ' < $f 2>/dev/null; echo; done | "
                       "grep -c '[e]cho stale2'", 30)
    assert res.stdout.strip() == "0", res  # ... including the child that cleared its environment
    assert "stopped" in await tool(a1, "check_process", name="run")
    _step("fence: attempt 1's processes stopped and confirmed gone", t0)

    t0 = time.monotonic()
    a2 = ToolContext(pid, sb, None, owner="T2.2")
    await tool(a2, "run_shell", command="touch go")  # releases anything still waiting on it
    for _ in range(50):  # the other task's job proves the release happened
        if "exited with code 0" in await tool(other, "check_process", name="other"):
            break
        await asyncio.sleep(0.2)
    assert sb.path("data/other.txt").read_text() == "other\n"  # other tasks are untouched
    assert not sb.path("data/out.txt").exists() and not sb.path("data/out2.txt").exists()
    _step("released: attempt 1's jobs never published; another task's job ran normally", t0)

    t0 = time.monotonic()
    await tool(a2, "write_file", path="src/runner.py", content="print('v2')\n")
    out = await tool(a2, "start_process", name="run", command="python src/runner.py > data/out.txt")
    assert out.startswith("Started run"), out
    for _ in range(50):
        if "exited with code 0" in await tool(a2, "check_process", name="run"):
            break
        await asyncio.sleep(0.2)
    await tool(a2, "run_shell", command="python src/runner.py > data/out2.txt")
    assert sb.path("data/out.txt").read_text() == "v2\n"
    assert sb.stale(fence, paths) == {"data/left.txt": ["data/left.txt"]}  # only the leftover is rejected
    assert await sb.reap("T2.2")
    _step("attempt 2 publishes its own outputs; the leftover is still flagged", t0)


def test_e2b_retry_fence():
    from app.execution.e2b_sandbox import E2BSandbox

    pid = f"e2bfence-{uuid.uuid4().hex[:8]}"
    sb = E2BSandbox(pid)
    print(f"\nE2B template {settings.e2b_template}, project {pid}")

    async def main() -> None:
        try:
            await _fence_scenario(sb, pid)
        finally:
            await sb.close()

    try:
        asyncio.run(main())
    finally:
        shutil.rmtree(sb.root, ignore_errors=True)


def test_e2b_end_to_end():
    from app.execution.e2b_sandbox import E2BSandbox

    pid = f"e2btest-{uuid.uuid4().hex[:8]}"
    sb = E2BSandbox(pid)
    print(f"\nE2B template {settings.e2b_template}, project {pid}")

    async def main() -> None:
        try:
            await _scenario(sb, pid)
        finally:
            await sb.close()

    try:
        asyncio.run(main())
    finally:
        shutil.rmtree(sb.root, ignore_errors=True)


async def _unreachable_scenario(sb, pid: str) -> None:
    """A network outage, simulated at the E2B client boundary of a real sandbox: the sandbox, its
    files and its processes are kept, and work continues in it once it can be reached again."""
    import httpx

    from app.execution.sandbox import SandboxUnreachable
    from app.execution.tools import TOOLS, ToolContext

    ctx = ToolContext(pid, sb, None, owner="T1")

    async def tool(tool_name: str, **args) -> str:
        return await TOOLS[tool_name].handler(ctx, args)

    t0 = time.monotonic()
    await sb.ensure()
    out = await tool("run_shell", command="echo before-outage > marker.txt")
    assert "exit_code: 0" in out, out
    assert (await tool("start_process", name="job", command="sleep 600")).startswith("Started job")
    remote = sb._sbx
    _step("sandbox created; marker written; background job started", t0)

    t0 = time.monotonic()

    async def offline(*args, **kw):
        raise httpx.ConnectError("[Errno 11001] getaddrinfo failed")

    run, sb._sbx.commands.run, sb._sbx.is_running = sb._sbx.commands.run, offline, offline
    try:
        assert await sb._alive() is None
        with pytest.raises(SandboxUnreachable):
            await tool("run_shell", command="cat marker.txt")
        with pytest.raises(SandboxUnreachable):
            await sb.fence("T1", [])
    finally:
        sb._sbx.commands.run = run
        del sb._sbx.is_running
    assert sb._sbx is remote and sb.procs["job"] == "running"
    _step("outage: unreachable, not declared dead, not recreated", t0)

    t0 = time.monotonic()
    assert await sb._alive() is True
    out = await tool("run_shell", command="cat marker.txt; pgrep -f 'sleep 600' >/dev/null && echo job-alive")
    assert "before-outage" in out and "job-alive" in out, out
    assert sb._sbx is remote
    assert await sb.reap("T1") and sb.procs["job"] == "stopped"
    _step("back online: same sandbox, same files, job still running until reaped", t0)


def test_e2b_unreachable_keeps_sandbox():
    from app.execution.e2b_sandbox import E2BSandbox

    pid = f"e2bnet-{uuid.uuid4().hex[:8]}"
    sb = E2BSandbox(pid)
    print(f"\nE2B template {settings.e2b_template}, project {pid}")

    async def main() -> None:
        try:
            await _unreachable_scenario(sb, pid)
        finally:
            await sb.close()

    try:
        asyncio.run(main())
    finally:
        shutil.rmtree(sb.root, ignore_errors=True)
