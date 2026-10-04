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
    out = await tool("run_shell", command="echo key=$MY_SERVICE_KEY; echo openai=${OPENAI_API_KEY:-none}")
    assert "key=abc123" in out and "openai=none" in out, out
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
