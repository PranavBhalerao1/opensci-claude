"""Where agent-written code runs.

`Sandbox` is the interface; `E2BSandbox` (e2b_sandbox.py) is the implementation:
agent code always runs in an E2B cloud sandbox, against a synced copy of the
per-project workspace, which stays on this machine as the source of truth. There
is no local execution. Explicit CUDA GPU jobs go to Google Colab (colab_runner.py).
"""

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

# Host copy of each project's workspace (the source of truth), outside the repo.
WORKSPACES = Path.home() / ".openscientist" / "workspaces"
PYTHON_VERSION = "3.12"
BASE_PACKAGES = ["numpy", "pandas", "scipy", "matplotlib", "requests"]
OUTPUT_LIMIT = 16_000
MIN_FREE_BYTES = 2 * 1024**3

# pip requirement spec: name, optional extras, optional single version constraint.
_PKG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9,._-]+\])?((==|>=|<=|~=|!=|>|<)[A-Za-z0-9.*+!-]+)?$")
# conda spec: [channel::]name[=version[=build]] or name with a comparison.
_CONDA_PKG = re.compile(r"^([A-Za-z0-9_.-]+::)?[A-Za-z0-9][A-Za-z0-9._-]*((=|==|>=|<=|>|<)[A-Za-z0-9.*_+!-]+(=[A-Za-z0-9.*_]+)?)?$")
_CONDA_CHANNELS = {"conda-forge", "bioconda", "pytorch", "nvidia", "defaults"}
_NAME = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


@dataclass
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False

    def render(self) -> str:
        parts = [f"exit_code: {self.exit_code}" + (" (timed out)" if self.timed_out else "")]
        if self.stdout:
            parts.append(f"stdout:\n{self.stdout}")
        if self.stderr:
            parts.append(f"stderr:\n{self.stderr}")
        return "\n".join(parts)


def _clip(text: str, limit: int = OUTPUT_LIMIT) -> str:
    """Keep the head and (mostly) the tail — errors live at the end."""
    if len(text) <= limit:
        return text
    head = limit // 4
    return f"{text[:head]}\n… [{len(text) - limit} chars omitted] …\n{text[-(limit - head):]}"


class SandboxUnreachable(RuntimeError):
    """The sandbox could not be reached (network down, timeout, provider unavailable). That is no
    evidence it is gone: its handle, processes and files are kept, and the work is retried later."""


@dataclass
class Fence:
    """Where a task attempt starts (see Sandbox.fence)."""

    clean: bool  # every process the task's earlier attempts started is confirmed stopped
    before: dict[str, frozenset] = field(default_factory=dict)  # output path → its files at the fence

    def leftovers(self) -> list[str]:
        """Outputs that already existed when the attempt started."""
        return [p for p, files in self.before.items() if files]


class Sandbox:
    """Interface every execution backend implements."""

    root: Path
    capabilities: set[str]

    # owner: the task id; every process the command starts is tagged with it (see reap).
    async def run(self, argv: list[str], timeout: float, owner: str | None = None) -> ExecResult: ...
    async def install(self, packages: list[str]) -> ExecResult: ...

    def path(self, rel: str) -> Path:
        """Resolve a workspace-relative path, refusing anything outside it."""
        p = (self.root / rel.lstrip("/")).resolve()
        if p != self.root and self.root not in p.parents:
            raise ValueError(f"Path escapes the workspace: {rel}")
        return p

    def free_bytes(self) -> int:
        return shutil.disk_usage(self.root).free

    async def pull(self) -> None:
        """Bring files changed by remote execution back into `root`."""

    async def reap(self, task_id: str | None) -> bool:
        """Stop every process the task's attempts started (every task's if None) and bring back what
        they wrote. True only if none is left running. Raises SandboxUnreachable if the sandbox
        cannot be reached at all."""
        return True

    async def fence(self, task_id: str, paths: list[str]) -> Fence:
        """Start a task attempt: stop what its earlier attempts left running, then record its outputs'
        files. A file still unchanged later was not written by this attempt (see stale). If the old
        processes cannot be confirmed stopped, the fence is not clean and nothing this attempt
        produces can be told apart from theirs. If the sandbox cannot be reached, SandboxUnreachable
        is raised and the attempt does not start."""
        clean = await self.reap(task_id)
        return Fence(clean, {p: self.files(p) for p in paths})

    def files(self, rel: str) -> frozenset:
        """(path, size, mtime_ns) of each file at `rel`, a file or a directory; empty if missing."""
        try:
            p = self.path(rel)
        except ValueError:
            return frozenset()
        found = [p] if p.is_file() else [q for q in p.rglob("*") if q.is_file()] if p.is_dir() else []
        out = set()
        for q in found:
            try:
                st = q.stat()
            except OSError:
                continue
            out.add((q.relative_to(self.root).as_posix(), st.st_size, st.st_mtime_ns))
        return frozenset(out)

    def stale(self, fence: Fence, paths: list[str]) -> dict[str, list[str]]:
        """For each output, its files that are unchanged since the fence: left by an earlier attempt,
        not written by this one."""
        out = {}
        for p in paths:
            if left := sorted(f[0] for f in self.files(p) & fence.before.get(p, frozenset())):
                out[p] = left
        return out


_sandboxes: dict[str, Sandbox] = {}


def sandbox_for(project_id: str) -> Sandbox:
    if project_id not in _sandboxes:
        from .e2b_sandbox import E2BSandbox  # imports colab_runner, which imports the db

        _sandboxes[project_id] = E2BSandbox(project_id)
    return _sandboxes[project_id]


def gpu_runner():
    """The module behind run_gpu_jobs: always colab_runner (Google Colab is the only GPU provider)."""
    from . import colab_runner

    return colab_runner
