"""E2B cloud sandboxes: where agent code runs by default.

Each project gets one E2B sandbox (template `settings.e2b_template`), created on
first use. The host workspace stays the source of truth: before every command the
files changed on the host are pushed, and afterwards the files the command
created, changed or deleted are pulled back. File tools, verification, reports,
the workspace browser and package export therefore keep reading the host copy.
Python and conda environments live in the sandbox, outside the synced workspace.
If a sandbox expires it is recreated from the host copy and its packages reinstalled.

Every process a task attempt starts carries OPENSCI_TASK=<task id> in its environment, inherited by
all its descendants, so the attempt's processes can be found and stopped when it ends (see reap).
"""

import asyncio
import logging
import os
import shlex
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath

from ..config import settings
from .sandbox import (
    _CONDA_CHANNELS, _CONDA_PKG, _NAME, _PKG, BASE_PACKAGES, PYTHON_VERSION, WORKSPACES, ExecResult, Sandbox,
    SandboxUnreachable, _clip,
)

log = logging.getLogger(__name__)

HOME = "/home/user"
REMOTE_ROOT = f"{HOME}/workspace"
VENV = f"{HOME}/.venv"
CONDA_ENV = f"{HOME}/.conda"
MAMBA_ROOT = f"{HOME}/.mamba"
MICROMAMBA = f"{HOME}/.local/bin/micromamba"
SYNC = f"{HOME}/.sync"  # scratch files for workspace transfers
MICROMAMBA_URL = "https://micro.mamba.pm/api/micromamba/linux-64/latest"
SANDBOX_TIMEOUT = 86400  # idle lifetime in seconds; extended on every use
KEEPALIVE_EVERY = 300
# Never synced in either direction: environments, caches, scratch temp files.
SKIP = {".venv", ".conda", ".home", ".tmp", "__pycache__", ".pytest_cache", ".sandbox.sb"}
# Lists remote files as `path<TAB>size<TAB>mtime`; paths start with "./".
_LIST = ("-printf '%p\\t%s\\t%T@\\n'")
# All files, plus empty directories as `DIR<TAB>path` (archives carry only files, so a directory an agent
# created and left empty would otherwise never exist in the host copy that checks and the verifier read).
_FIND_ALL = (f"find . \\( {' -o '.join(f'-name {shlex.quote(s)}' for s in sorted(SKIP))} \\) -prune -o "
             f"-type f {_LIST} -o -type d -empty -printf 'DIR\\t%p\\n'")
_EMPTY_DIR = "DIR\t./"
TAG = "OPENSCI_TASK"
# Stops every process whose environment holds argv[1] (exactly, or as a prefix) and all of their
# descendants (children that cleared their environment, or run via sudo). The whole tree is frozen
# first, so nothing forks or is orphaned out of sight while it is killed. Prints "clean" only if
# nothing is left; the pause between rounds only lets the kernel finish killing.
_REAP = r"""
import os, signal, sys, time
want, exact, me = sys.argv[1].encode(), sys.argv[2] == "exact", os.getpid()

def scan():
    tagged, parent = set(), {}
    for d in os.listdir("/proc"):
        if not d.isdigit() or int(d) == me:
            continue
        try:
            with open(f"/proc/{d}/stat") as f:
                fields = f.read().rsplit(")", 1)[1].split()
        except (OSError, IndexError):
            continue
        if fields[0] in ("Z", "X"):  # zombies cannot run or write
            continue
        parent[int(d)] = int(fields[1])
        try:
            with open(f"/proc/{d}/environ", "rb") as f:
                env = f.read().split(b"\0")
        except OSError:
            continue
        if any(v == want if exact else v.startswith(want) for v in env):
            tagged.add(int(d))
    found = set(tagged)
    while more := {p for p, pp in parent.items() if pp in found} - found:
        found |= more
    return found

def send(pids, sig):
    for p in pids:
        try:
            os.kill(p, sig)
        except OSError:
            pass

seen = set()
for _ in range(50):
    found = scan()
    send(found - seen, signal.SIGSTOP)
    if found <= seen:
        break
    seen |= found
for _ in range(50):
    found = scan()
    if not found:
        print("clean")
        break
    send(found, signal.SIGKILL)
    time.sleep(0.05)
else:
    print("alive", *sorted(scan()))
"""


def _skip(rel: str) -> bool:
    return any(part in SKIP for part in rel.split("/"))


def _parse_listing(text: str) -> dict[str, tuple[int, str]]:
    out = {}
    for line in text.splitlines():
        parts = line.rsplit("\t", 2)
        if len(parts) == 3 and parts[0].startswith("./") and not _skip(parts[0][2:]):
            out[parts[0][2:]] = (int(parts[1]), parts[2])
    return out


def _empty_dirs(text: str) -> list[str]:
    """The empty directories in a _FIND_ALL listing (which _parse_listing ignores)."""
    return [line[len(_EMPTY_DIR):] for line in text.splitlines()
            if line.startswith(_EMPTY_DIR) and line[len(_EMPTY_DIR):] and not _skip(line[len(_EMPTY_DIR):])]


class E2BSandbox(Sandbox):
    BASE_CAPABILITIES = frozenset({"python", "shell", "internet", "files", "cpu", "background", "conda"})

    @property
    def capabilities(self) -> set[str]:  # type: ignore[override]
        """No local GPU: CUDA work goes to Google Colab (run_gpu_jobs) when it is configured."""
        from . import colab_runner

        return set(self.BASE_CAPABILITIES) | ({"cuda_gpu"} if colab_runner.configured() else set())

    @capabilities.setter
    def capabilities(self, value: set[str]) -> None:
        self.BASE_CAPABILITIES = frozenset(value)

    def __init__(self, project_id: str):
        # No network here: routes and the Blueprint Agent construct sandboxes just to read paths.
        self.project_id = project_id
        self.root = (WORKSPACES / project_id).resolve()
        self.secrets: dict[str, str] = {}
        self.procs: dict[str, str] = {}  # background process name → "running" | "done" | "stopped"
        self.proc_owner: dict[str, str | None] = {}  # background process name → task id that started it
        self._sbx = None
        self._lock = asyncio.Lock()  # sandbox creation
        self._sync = asyncio.Lock()  # push / pull
        self._conda_lock = asyncio.Lock()
        self._host_seen: dict[str, tuple[int, int]] = {}  # host files as of the last sync
        self._remote_seen: dict[str, tuple[int, str]] = {}  # remote files as of the last sync
        self._pip_specs: list[str] = []  # replayed if the sandbox has to be recreated
        self._conda_specs: list[tuple[list[str], list[str]]] = []
        self._touched = 0.0

    @property
    def python(self) -> PurePosixPath:
        return PurePosixPath(f"{VENV}/bin/python")

    def _remote(self, arg: str) -> str:
        """Host workspace paths in argv (e.g. the run_python cell file) → sandbox paths."""
        root = str(self.root)
        if arg == root or arg.startswith(root + os.sep):
            return REMOTE_ROOT + arg[len(root):].replace(os.sep, "/")
        return arg

    def _env(self, owner: str | None = None) -> dict[str, str]:
        # Only the credentials the user supplied for this project; no host secrets.
        return {
            **self.secrets,
            **({TAG: owner} if owner else {}),
            "PATH": f"{VENV}/bin:{CONDA_ENV}/bin:{HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin",
            "VIRTUAL_ENV": VENV,
            "MPLBACKEND": "Agg",
            "PYTHONUNBUFFERED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "LANG": "C.UTF-8",
        }

    # ── Sandbox lifecycle ──────────────────────────────────────────────────

    async def ensure(self) -> None:
        """Create the sandbox, its Python environment and the remote workspace on first use."""
        from e2b import AsyncSandbox

        async with self._lock:
            if self._sbx is not None:
                return
            if not settings.e2b_api_key:
                raise RuntimeError("E2B is not configured: set E2B_API_KEY (code never runs locally)")
            for d in (self.root, self.root / ".scratch", self.root / ".logs"):
                d.mkdir(parents=True, exist_ok=True)
            # After a backend restart the host copy may be gone (Heroku's disk is ephemeral) while the
            # project's sandbox still has every file: reattach to it rather than start an empty one.
            if await self._reattach():
                return
            create = dict(template=settings.e2b_template, api_key=settings.e2b_api_key,
                          timeout=SANDBOX_TIMEOUT, metadata={"project_id": self.project_id})
            try:
                try:
                    # Idle past the timeout, the sandbox is paused, not killed, so its files survive.
                    sbx = await AsyncSandbox.create(**create, lifecycle={"on_timeout": "pause"})
                except Exception as exc:
                    # An account without pausing still gets a sandbox, killed when idle as before.
                    log.warning("E2B refused a pausing sandbox for %s (%s: %s); creating one without",
                                self.project_id, type(exc).__name__, exc)
                    sbx = await AsyncSandbox.create(**create)
            except Exception as exc:
                raise RuntimeError(f"E2B sandbox (template {settings.e2b_template}) could not be started: "
                                   f"{type(exc).__name__}: {exc}") from exc
            self._sbx, self._host_seen, self._remote_seen = sbx, {}, {}
            self._touched = time.monotonic()
            try:
                res = await self._sh(
                    f"mkdir -p {REMOTE_ROOT} {SYNC} && if command -v uv >/dev/null; then "
                    f"uv venv {VENV} --python {PYTHON_VERSION} --seed --quiet; else python3 -m venv {VENV}; fi",
                    600, cwd=HOME)
                if res.exit_code:
                    raise RuntimeError(f"Could not create the sandbox environment: {res.stderr}")
                res = await self._pip(BASE_PACKAGES + self._pip_specs)
                if res.exit_code:
                    raise RuntimeError(f"Could not install base packages: {res.stderr}")
                for packages, channels in self._conda_specs:
                    await self._conda(packages, channels)
                async with self._sync:
                    await self._push()
            except BaseException:
                self._sbx = None
                await sbx.kill()
                raise

    async def _find(self):
        """Connect to this project's newest existing sandbox, running or paused (a paused one is
        resumed); None if it has none or E2B cannot be asked."""
        from e2b import AsyncSandbox, SandboxQuery, SandboxState

        if not settings.e2b_api_key:
            return None
        try:
            pager = AsyncSandbox.list(query=SandboxQuery(metadata={"project_id": self.project_id},
                                                         state=[SandboxState.RUNNING, SandboxState.PAUSED]),
                                      api_key=settings.e2b_api_key)
            found = await pager.next_items()
            if not found:
                return None
            newest = max(found, key=lambda info: info.started_at)
            return await AsyncSandbox.connect(newest.sandbox_id, timeout=SANDBOX_TIMEOUT, api_key=settings.e2b_api_key)
        except Exception as exc:
            log.warning("Could not reattach to an E2B sandbox for %s: %s: %s", self.project_id, type(exc).__name__, exc)
            return None

    async def _reattach(self) -> bool:
        """Adopt the project's existing sandbox, if any, and restore every file from it into the host
        copy. Called with self._lock held and no sandbox attached."""
        sbx = await self._find()
        if sbx is None:
            return False
        self._sbx, self._host_seen, self._remote_seen = sbx, {}, {}
        self._touched = time.monotonic()
        try:
            res = await self._sh(f"mkdir -p {REMOTE_ROOT} {SYNC} && test -x {VENV}/bin/python", 60, cwd=HOME)
            if res.exit_code:  # never finished setting up: start over with a fresh one
                raise RuntimeError("sandbox environment missing")
            async with self._sync:
                await self._pull()  # nothing seen yet: brings back every file
                await self._push()  # then anything only the host has
        except Exception as exc:
            log.warning("Reattached E2B sandbox for %s is unusable (%s); starting a new one", self.project_id, exc)
            self._sbx = None
            return False
        log.info("Reattached E2B sandbox %s for %s and restored its workspace", sbx.sandbox_id, self.project_id)
        return True

    async def save(self) -> None:
        """Push host-side writes (review records, downloads) to the attached sandbox, never creating one."""
        if self._sbx is None:
            return
        try:
            async with self._sync:
                await self._push()
        except Exception as exc:
            log.warning("Saving the workspace of %s to E2B failed: %s", self.project_id, exc)

    async def recover(self) -> bool:
        """Restore the workspace from the project's existing sandbox after a restart, without ever
        creating one (readers call this). True if a sandbox is attached afterwards."""
        async with self._lock:
            if self._sbx is None:
                await self._reattach()
            return self._sbx is not None

    async def forget(self) -> None:
        """Kill every sandbox this project has, running or paused (the project was deleted)."""
        from e2b import AsyncSandbox, SandboxQuery, SandboxState

        self._sbx = None
        if not settings.e2b_api_key:
            return
        try:
            pager = AsyncSandbox.list(query=SandboxQuery(metadata={"project_id": self.project_id},
                                                         state=[SandboxState.RUNNING, SandboxState.PAUSED]),
                                      api_key=settings.e2b_api_key)
            while True:
                for info in await pager.next_items():
                    await AsyncSandbox.kill(info.sandbox_id, api_key=settings.e2b_api_key)
                if not pager.has_next:
                    break
        except Exception as exc:
            log.warning("Could not delete E2B sandboxes for %s: %s: %s", self.project_id, type(exc).__name__, exc)

    async def _alive(self) -> bool | None:
        """False only when E2B reports the sandbox gone (killed, expired); None when E2B could not
        be asked (network down, timeout, outage), which is no evidence either way. Same rule as
        the SDK's own health probe (e2b.envd.api.acheck_sandbox_health)."""
        if self._sbx is None:
            return False
        try:
            return await self._sbx.is_running()
        except Exception as exc:
            log.warning("E2B sandbox for %s could not be reached: %s: %s", self.project_id, type(exc).__name__, exc)
            return None

    async def _retrying(self, fn):
        """Run fn against the sandbox; if the sandbox died (expired, killed), recreate it once.
        If it cannot be reached, keep it (and everything running in it) and raise SandboxUnreachable."""
        await self.ensure()
        try:
            return await fn()
        except Exception as exc:
            alive = await self._alive()
            if alive:
                raise
            if alive is None:
                raise SandboxUnreachable(f"E2B sandbox for {self.project_id} could not be reached: "
                                         f"{type(exc).__name__}: {exc}") from exc
            log.warning("E2B sandbox for %s is gone; recreating it from the host workspace", self.project_id)
            self._sbx = None
            self.procs = {n: "done" for n in self.procs}
            await self.ensure()
            return await fn()

    async def _keepalive(self, seconds: float = 0) -> None:
        if seconds + 600 > SANDBOX_TIMEOUT or time.monotonic() - self._touched > KEEPALIVE_EVERY:
            await self._sbx.set_timeout(int(max(SANDBOX_TIMEOUT, seconds + 600)))
            self._touched = time.monotonic()

    async def close(self) -> None:
        if self._sbx is not None:
            sbx, self._sbx = self._sbx, None
            await sbx.kill()

    async def _sh(self, cmd: str, timeout: float, cwd: str = REMOTE_ROOT,
                  envs: dict[str, str] | None = None, clip: bool = True) -> ExecResult:
        from e2b import CommandExitException, TimeoutException

        c = _clip if clip else (lambda text: text)  # sync listings must stay whole
        if envs and "PATH" in envs:  # commands run in a login shell, which resets PATH from /etc/profile
            cmd = f"export PATH={shlex.quote(envs['PATH'])}; {cmd}"
        try:
            r = await self._sbx.commands.run(cmd, cwd=cwd, envs=envs, timeout=timeout)
            return ExecResult(r.exit_code, c(r.stdout), _clip(r.stderr))
        except CommandExitException as e:
            return ExecResult(e.exit_code, c(e.stdout), _clip(e.stderr))
        except TimeoutException as e:
            return ExecResult(-9, "", str(e), timed_out=True)

    # ── Sync (host workspace ⇄ sandbox) ────────────────────────────────────

    def _scan_host(self) -> dict[str, tuple[int, int]]:
        out = {}
        if not self.root.exists():
            return out
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in SKIP]
            for name in filenames:
                if name in SKIP:
                    continue
                p = Path(dirpath) / name
                try:
                    st = p.stat()
                except OSError:
                    continue
                out[p.relative_to(self.root).as_posix()] = (st.st_size, st.st_mtime_ns)
        return out

    async def _push(self) -> None:
        """Send host-side changes (file tools, downloads, GPU job results) to the sandbox."""
        host = self._scan_host()
        changed = [r for r, sig in host.items() if self._host_seen.get(r) != sig]
        deleted = [r for r in self._host_seen if r not in host]
        if not changed and not deleted:
            return
        steps = []
        if changed:
            with tempfile.SpooledTemporaryFile(64 * 1024**2) as buf:
                with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=1) as tar:
                    for r in changed:
                        tar.add(self.root / r, arcname=r, recursive=False)
                buf.seek(0)
                await self._sbx.files.write(f"{SYNC}/os_push.tgz", buf)
            await self._sbx.files.write(f"{SYNC}/os_push.list", "\n".join(changed) + "\n")
            steps.append(f"tar -xzf {SYNC}/os_push.tgz -C . && rm -f {SYNC}/os_push.tgz")
        if deleted:
            await self._sbx.files.write(f"{SYNC}/os_del.list", "\n".join(deleted) + "\n")
            steps.append(f"sed 's|^|./|' {SYNC}/os_del.list | tr '\\n' '\\0' | xargs -0 -r rm -f --")
        if changed:
            # Record the pushed files' remote state so the next pull does not bring them back.
            steps.append(f"sed 's|^|./|' {SYNC}/os_push.list | tr '\\n' '\\0' | "
                         f"xargs -0 -r sh -c 'find \"$@\" -maxdepth 0 {_LIST}' _")
        res = await self._sh(" && ".join(steps), 900, clip=False)
        if res.exit_code:
            raise RuntimeError(f"Workspace upload to E2B failed: {res.stderr[-500:]}")
        for r in deleted:
            self._remote_seen.pop(r, None)
        self._remote_seen.update(_parse_listing(res.stdout))
        self._host_seen = host

    async def _pull(self) -> None:
        """Bring back files the sandbox created, changed or deleted since the last sync."""
        res = await self._sh(_FIND_ALL, 300, clip=False)
        if res.exit_code:
            raise RuntimeError(f"Listing the E2B workspace failed: {res.stderr[-500:]}")
        remote, empty = _parse_listing(res.stdout), _empty_dirs(res.stdout)
        changed = [r for r, sig in remote.items() if self._remote_seen.get(r) != sig]
        deleted = [r for r in self._remote_seen if r not in remote]
        if changed:
            await self._sbx.files.write(f"{SYNC}/os_pull.list", "\n".join(changed) + "\n")
            res = await self._sh(f"tar -czf {SYNC}/os_pull.tgz --ignore-failed-read --verbatim-files-from "
                                 f"-T {SYNC}/os_pull.list", 900)
            if res.exit_code not in (0, 1):  # 1: a file changed while being archived
                raise RuntimeError(f"Workspace download from E2B failed: {res.stderr[-500:]}")
            with tempfile.SpooledTemporaryFile(64 * 1024**2) as buf:  # large outputs spill to disk
                async for chunk in await self._sbx.files.read(f"{SYNC}/os_pull.tgz", format="stream"):
                    buf.write(chunk)
                buf.seek(0)
                with tarfile.open(fileobj=buf, mode="r:gz") as tar:
                    for m in tar:
                        if not m.isfile() or _skip(m.name.removeprefix("./")):
                            continue
                        try:
                            tar.extract(m, self.root, filter="data")  # refuses paths outside the workspace
                        except (OSError, tarfile.TarError) as exc:
                            log.warning("Skipped %s from E2B: %s", m.name, exc)
        for r in deleted:
            p = self.root / r
            try:
                st = p.stat()
            except OSError:
                continue
            if self._host_seen.get(r) == (st.st_size, st.st_mtime_ns):  # never drop unsynced host edits
                p.unlink()
        for d in empty:
            try:
                self.path(d).mkdir(parents=True, exist_ok=True)
            except (ValueError, OSError) as exc:  # outside the workspace, or a host file in the way
                log.warning("Skipped empty directory %s from E2B: %s", d, exc)
        self._remote_seen = remote
        for r in changed + deleted:
            try:
                st = (self.root / r).stat()
                self._host_seen[r] = (st.st_size, st.st_mtime_ns)
            except OSError:
                self._host_seen.pop(r, None)
        for name, state in self.procs.items():
            if state == "running" and (self.root / ".logs" / f"{name}.exit").exists():
                self.procs[name] = "done"

    async def pull(self) -> None:
        """Sync before reading the host copy. Every command already syncs when it ends, so
        only background processes can leave changes behind; without them this is free. With no
        sandbox attached (e.g. after a restart), the files are restored from the project's sandbox."""
        if self._sbx is None:
            await self.recover()
            return
        if "running" not in self.procs.values():
            return
        try:
            async with self._sync:
                await self._pull()
        except Exception as exc:  # readers fall back to the last synced copy
            log.warning("E2B pull for %s failed: %s", self.project_id, exc)

    # ── Commands ───────────────────────────────────────────────────────────

    async def run(self, argv: list[str], timeout: float, owner: str | None = None) -> ExecResult:
        cmd = shlex.join(self._remote(a) for a in argv)
        t = max(1, int(timeout))

        async def go() -> ExecResult:
            await self._keepalive(t)
            async with self._sync:
                await self._push()
            start = time.monotonic()
            # On timeout, coreutils timeout kills the process group. Children detached from it (or
            # left running when the command ends) are found by their owner tag instead (reap).
            res = await self._sh(f"timeout -k 5 {t} {cmd}", t + 30, envs=self._env(owner))
            if res.exit_code in (124, 137) and time.monotonic() - start >= t - 1:
                res = ExecResult(-9, res.stdout, res.stderr, timed_out=True)
            async with self._sync:
                await self._pull()
            return res

        return await self._retrying(go)

    async def _pip(self, packages: list[str]) -> ExecResult:
        specs = " ".join(shlex.quote(p) for p in packages)
        return await self._sh(
            f"if command -v uv >/dev/null; then uv pip install --quiet --python {VENV}/bin/python {specs}; "
            f"else {VENV}/bin/python -m pip install --quiet {specs}; fi", 900, cwd=HOME)

    async def install(self, packages: list[str]) -> ExecResult:
        bad = [p for p in packages if not _PKG.match(p)]
        if bad:
            return ExecResult(2, "", f"Rejected package specs: {', '.join(bad)}")
        res = await self._retrying(lambda: self._pip(packages))
        if res.exit_code == 0:
            self._pip_specs += [p for p in packages if p not in self._pip_specs]
        return res

    async def _conda(self, packages: list[str], channels: list[str]) -> ExecResult:
        fetch = (f"[ -x {MICROMAMBA} ] || python3 -c \"import io,tarfile,urllib.request as u; "
                 f"t=tarfile.open(fileobj=io.BytesIO(u.urlopen('{MICROMAMBA_URL}').read()),mode='r:bz2'); "
                 f"t.extract('bin/micromamba','{HOME}/.local',filter='data')\" && chmod +x {MICROMAMBA}")
        chan = " ".join(f"-c {c}" for c in (channels or ["conda-forge"]))
        specs = " ".join(shlex.quote(p) for p in packages)
        async with self._conda_lock:  # one writer per environment
            return await self._sh(
                f"{fetch} && if [ -d {CONDA_ENV}/conda-meta ]; then v=install; else v=create; fi && "
                f"{MICROMAMBA} $v -y -q -r {MAMBA_ROOT} -p {CONDA_ENV} {chan} {specs}", 1800, cwd=HOME)

    async def install_conda(self, packages: list[str], channels: list[str]) -> ExecResult:
        bad = [p for p in packages if not _CONDA_PKG.match(p)] + [c for c in channels if c not in _CONDA_CHANNELS]
        if bad:
            return ExecResult(2, "", f"Rejected specs or channels: {', '.join(bad)}")
        res = await self._retrying(lambda: self._conda(packages, channels))
        if res.exit_code == 0:
            self._conda_specs.append((list(packages), list(channels)))
        return res

    # ── Background processes (training runs, servers, long simulations) ────

    async def spawn(self, name: str, command: str, owner: str | None = None) -> str:
        """Start a shell command in the background; output goes to .logs/<name>.log."""
        if not _NAME.match(name):
            raise ValueError("Process names may use letters, digits, - and _ (max 40)")
        if self.procs.get(name) == "running":
            await self.pull()
            if self.procs.get(name) == "running":
                raise ValueError(f"A process named {name} is already running")
        logs = self.root / ".logs"
        wrapped = (f"echo $$ > .logs/{name}.pid; ( {command}\n) > .logs/{name}.log 2>&1; "
                   f"echo $? > .logs/{name}.exit")

        async def go() -> str:
            logs.mkdir(parents=True, exist_ok=True)
            for suffix in ("exit", "pid"):  # clear a previous run's state on both sides
                (logs / f"{name}.{suffix}").unlink(missing_ok=True)
            await self._keepalive()
            async with self._sync:
                await self._push()
            # setsid -f detaches: the process outlives this call in its own process group.
            # Wait briefly for its pid: the reply reports it, as it did before the move to E2B.
            res = await self._sh(f"mkdir -p .logs && setsid -f bash -c {shlex.quote(wrapped)} "
                                 f"</dev/null >/dev/null 2>&1; for _ in $(seq 50); do "
                                 f"[ -s .logs/{name}.pid ] && break; sleep 0.1; done; cat .logs/{name}.pid",
                                 60, envs=self._env(owner))
            if res.exit_code:
                raise RuntimeError(f"Could not start {name}: {res.stderr}")
            return res.stdout.strip()

        pid = await self._retrying(go)
        self.procs[name], self.proc_owner[name] = "running", owner
        return f"Started {name} (pid {pid}); logs in .logs/{name}.log"

    async def status(self, name: str, tail: int = 30) -> str:
        if name not in self.procs:
            return f"No process named {name}. Known: {', '.join(self.procs) or 'none'}"
        if self.procs[name] == "running" and await self._alive():
            await self._keepalive()
            async with self._sync:
                await self._pull()
        log_file = self.root / ".logs" / f"{name}.log"
        exit_file = self.root / ".logs" / f"{name}.exit"
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines() if log_file.exists() else []
        if exit_file.exists():
            state = f"exited with code {exit_file.read_text(encoding='utf-8').strip()}"
        elif self.procs[name] == "stopped":
            state = "stopped (the task attempt that started it ended)"
        elif self.procs[name] == "done":
            state = "ended (the sandbox was recreated; it is no longer running)"
        else:
            state = "running"
        return f"{name}: {state}\nlast {min(tail, len(lines))} of {len(lines)} log lines:\n" + "\n".join(lines[-tail:])

    def _kill_cmd(self, name: str, signal: str) -> str:
        return (f"[ -f .logs/{name}.exit ] && echo done || "
                f"kill -{signal} -- -\"$(cat .logs/{name}.pid 2>/dev/null)\" 2>/dev/null; true")

    async def stop(self, name: str) -> str:
        if self.procs.get(name) != "running" or await self._alive() is False:
            return f"{name} is not running"
        res = await self._sh(self._kill_cmd(name, "TERM"), 30)
        return f"{name} is not running" if res.stdout.strip() == "done" else f"Sent SIGTERM to {name}"

    async def _reap(self, task_id: str | None) -> bool:
        want = f"{TAG}={task_id or ''}"
        res = await self._sh(f"python3 -c {shlex.quote(_REAP)} {shlex.quote(want)} "
                             f"{'exact' if task_id else 'prefix'}", 120, cwd=HOME)
        clean = res.exit_code == 0 and res.stdout.strip() == "clean"
        if clean:
            for name, owner in self.proc_owner.items():
                if owner and (task_id is None or owner == task_id) and self.procs.get(name) == "running":
                    self.procs[name] = "stopped"
        return clean

    async def reap(self, task_id: str | None) -> bool:
        if self._sbx is None:  # no sandbox in this server process: nothing can be running in it
            return True

        async def go() -> bool:
            clean = await self._reap(task_id)
            async with self._sync:  # whatever they wrote before they died
                await self._pull()
            return clean

        try:
            return await self._retrying(go)  # a dead sandbox is recreated: its processes died with it
        except SandboxUnreachable:  # cannot tell yet; the caller decides (the fence does not start the attempt)
            raise
        except Exception as exc:  # unknown, so not clean
            log.warning("Stopping the processes of %s in %s failed: %s", task_id or "all tasks", self.project_id, exc)
            return False

    async def stop_all(self) -> None:
        """Kill every background process (named, or started by any task attempt) and pull their final output."""
        if self._sbx is None:
            return
        names = [n for n, s in self.procs.items() if s == "running"]
        try:
            if names:
                await self._sh("; ".join(self._kill_cmd(n, "KILL") for n in names), 60)
            await self._reap(None)
            async with self._sync:
                await self._pull()
        except Exception as exc:
            log.warning("Stopping E2B processes for %s failed: %s", self.project_id, exc)
        for n in names:
            self.procs[n] = "done"
