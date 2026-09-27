"""Where agent-written code runs.

`Sandbox` is the interface; `LocalSandbox` runs on this machine inside a
per-project workspace, confined by macOS `sandbox-exec` (writes only inside the
workspace; no reading the repo, secrets or the database; network allowed so
agents can reach scientific APIs). A cloud implementation (e.g. Modal) can be
added behind the same interface later.

This is defence in depth for development, not a hardened multi-tenant boundary.
"""

import asyncio
import os
import re
import shutil
import signal
import sys
from dataclasses import dataclass
from pathlib import Path

from ..config import BACKEND_DIR, ROOT_DIR

WORKSPACES = BACKEND_DIR / "data" / "workspaces"
PYTHON_VERSION = "3.12"
BASE_PACKAGES = ["numpy", "pandas", "scipy", "matplotlib", "requests"]
OUTPUT_LIMIT = 16_000
MIN_FREE_BYTES = 2 * 1024**3

# pip requirement spec: name, optional extras, optional single version constraint.
_PKG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9,._-]+\])?((==|>=|<=|~=|!=|>|<)[A-Za-z0-9.*+!-]+)?$")


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


class LocalSandbox(Sandbox):
    capabilities = {"python", "shell", "internet", "files", "cpu"} | (
        {"apple_gpu"} if sys.platform == "darwin" else set()
    )

    def __init__(self, project_id: str):
        self.root = (WORKSPACES / project_id).resolve()
        self.venv = self.root / ".venv"
        self._ready = False
        self._lock = asyncio.Lock()

    @property
    def python(self) -> Path:
        return self.venv / "bin" / "python"

    def _profile(self) -> str:
        home = Path.home()
        secret_dirs = [home / ".ssh", home / ".aws", home / ".config", home / ".gnupg", home / ".kube"]
        denies = "\n".join(f'(deny file-read* (subpath "{d}"))' for d in secret_dirs)
        return f"""(version 1)
(allow default)
(deny file-write* (subpath "/"))
(allow file-write* (subpath "{self.root}") (literal "/dev/null") (literal "/dev/tty")
       (literal "/dev/stdout") (literal "/dev/stderr") (subpath "/private/var/folders"))
(deny file-read* (subpath "{ROOT_DIR}"))
(allow file-read* (subpath "{self.root}"))
{denies}
(deny file-read* (literal "{home / '.netrc'}"))
"""

    def _env(self) -> dict[str, str]:
        # Deliberately minimal: no API keys or host credentials reach agent code.
        return {
            "PATH": f"{self.venv / 'bin'}:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin",
            "HOME": str(self.root),
            "TMPDIR": str(self.root / ".tmp"),
            "MPLBACKEND": "Agg",
            "PYTHONUNBUFFERED": "1",
            "LANG": "en_US.UTF-8",
            "VIRTUAL_ENV": str(self.venv),
        }

    async def ensure(self) -> None:
        """Create the workspace and its Python environment on first use."""
        async with self._lock:
            if self._ready:
                return
            for d in (self.root, self.root / ".tmp", self.root / ".scratch"):
                d.mkdir(parents=True, exist_ok=True)
            (self.root / ".sandbox.sb").write_text(self._profile())
            if not self.python.exists():
                res = await self._host(["uv", "venv", str(self.venv), "--python", PYTHON_VERSION, "--quiet"], 300)
                if res.exit_code:
                    raise RuntimeError(f"Could not create the workspace environment: {res.stderr}")
                res = await self.install(BASE_PACKAGES)
                if res.exit_code:
                    raise RuntimeError(f"Could not install base packages: {res.stderr}")
            self._ready = True

    async def _host(self, argv: list[str], timeout: float, sandboxed: bool = False) -> ExecResult:
        if sandboxed:
            argv = ["/usr/bin/sandbox-exec", "-f", str(self.root / ".sandbox.sb"), *argv]
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=self.root,
            env=self._env() if sandboxed else {**os.environ, "VIRTUAL_ENV": str(self.venv)},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,  # own process group, so a timeout kills children too
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout)
            timed_out = False
        except TimeoutError:
            os.killpg(proc.pid, signal.SIGKILL)
            out, err = await proc.communicate()
            timed_out = True
        return ExecResult(
            exit_code=proc.returncode if not timed_out else -9,
            stdout=_clip(out.decode(errors="replace")),
            stderr=_clip(err.decode(errors="replace")),
            timed_out=timed_out,
        )

    async def run(self, argv: list[str], timeout: float) -> ExecResult:
        await self.ensure()
        return await self._host(argv, timeout, sandboxed=True)

    async def install(self, packages: list[str]) -> ExecResult:
        bad = [p for p in packages if not _PKG.match(p)]
        if bad:
            return ExecResult(2, "", f"Rejected package specs: {', '.join(bad)}")
        if self.free_bytes() < MIN_FREE_BYTES:
            return ExecResult(2, "", "Not enough free disk space to install packages")
        # Runs outside the sandbox: uv needs its shared cache. Only validated specs reach here.
        return await self._host(["uv", "pip", "install", "--quiet", "--python", str(self.python), *packages], 900)


_sandboxes: dict[str, LocalSandbox] = {}


def sandbox_for(project_id: str) -> LocalSandbox:
    if project_id not in _sandboxes:
        _sandboxes[project_id] = LocalSandbox(project_id)
    return _sandboxes[project_id]
