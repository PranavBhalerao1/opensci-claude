"""Where agent-written code runs.

`Sandbox` is the interface; `E2BSandbox` (e2b_sandbox.py) is the implementation:
agent code always runs in an E2B cloud sandbox, against a synced copy of the
per-project workspace, which stays on this machine as the source of truth. There
is no local execution. Explicit CUDA GPU jobs go to Modal (modal_runner.py).
"""

import re
import shutil
from dataclasses import dataclass
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


class Sandbox:
    """Interface every execution backend implements."""

    root: Path
    capabilities: set[str]

    async def run(self, argv: list[str], timeout: float) -> ExecResult: ...
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


_sandboxes: dict[str, Sandbox] = {}


def sandbox_for(project_id: str) -> Sandbox:
    if project_id not in _sandboxes:
        from .e2b_sandbox import E2BSandbox  # imports modal_runner, which imports the db

        _sandboxes[project_id] = E2BSandbox(project_id)
    return _sandboxes[project_id]
