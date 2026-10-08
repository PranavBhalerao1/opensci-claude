"""Cloud GPU jobs on Google Colab, through Google's `colab` CLI (google-colab-cli).

Same contract as modal_runner.run_jobs. A call runs its jobs on up to
`settings.colab_max_sessions` Colab GPU VMs, drawn from one pool shared by every
project. Each VM is set up once per call (workspace upload, pip packages) and runs
that call's jobs one after another, each from a fresh copy of the workspace,
detached on the VM under coreutils `timeout`; the files a job creates or changes are
synced back to the host as soon as it ends. VMs are stopped when the call ends or is
cancelled, and by the reaper after a crash (an idle VM keeps billing). GPU time is
metered per second from Colab's compute-unit rates and capped per project.

The CLI is used only through its documented commands, and its quirks shape the
protocol (docs/colab-gpu.md): `exec` exits 0 when remote code raises and its
--timeout bounds nothing, so every remote step prints one __OS_RESULT__ JSON line and
runs under our own timeout; connections drop now and then, so every remote step is
idempotent and retried; the Contents API is rooted at `/`, needs existing parent
directories and drops requests of 128 MB, so transfers go in 32 MB parts.
"""

import asyncio
import base64
import contextlib
import hashlib
import json
import logging
import math
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tarfile
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import Session, func, select

from ..beta import owner_of, project_allowance
from ..config import settings
from ..db import GpuUsage, Project, engine
from ..llm import current_run

log = logging.getLogger(__name__)

# Compute units per hour, measured with `colab usage` (one session active, 2026-10-08).
# A100 and H100 are not offered until their rates have been measured.
CU_PER_HOUR = {"T4": 1.07, "L4": 1.54}
USD_PER_CU = 0.10  # Pay As You Go: $9.99 per 100 compute units
GPU_PRICES = {gpu: cu * USD_PER_CU / 3600 for gpu, cu in CU_PER_HOUR.items()}  # USD per second
DEFAULT_GPU_BUDGET = 10.0
MAX_PARALLEL_JOBS = 40
MAX_SYNC_FILE_BYTES = 500 * 1024**2
MIN_BALANCE_CU = 10.0  # Colab disallows automation on accounts without a positive balance
MAX_SESSION_S = int(10.5 * 3600)  # Colab VMs live at most ~12 h; sessions are rotated before that
SESSION_OVERHEAD_S = 180  # allocation, GPU check, setup and stop (measured ~1 min)
PER_JOB_OVERHEAD_S = 60  # fresh workspace, launch and collect, plus transfer time
TRANSFER_BYTES_PER_S = 6 * 1024**2
PART_BYTES = 32 * 1024**2
WAIT_CHUNK_S = 110
DEADLINE_GRACE_S = 120  # past its timeout a job is killed by us (coreutils `timeout` normally acts first)
RETRY_S = 10  # base delay between retries of a failed CLI step
BACKOFF_S = (30, 60, 120)  # waiting for GPU capacity (Colab answers 503/412 when it has none)
COLAB_HOME = Path.home() / ".openscientist" / "colab"  # CLI state, session ledger, temp files (0700)
STATE = "/content/os_state"  # on the VM: transfer parts, job scripts, exit files
CONTENTS = STATE.lstrip("/")  # the same directory as the Contents API names it (rooted at /)
REMOTE_ROOT = "/workspace"
SENTINEL = "__OS_RESULT__"
AUTH_MESSAGE = ("Colab GPU credentials were rejected (expired, revoked, or reauthentication required). "
                "GPU jobs cannot run until the setup login is repeated; see docs/colab-gpu.md.")

_REDACT = re.compile(r"ya29\.[\w.\-]+|1//[\w.\-]+|Bearer\s+\S+|colab-runtime-proxy-token=[^&\s'\"]+"
                     r"|eyJ[\w-]+\.[\w-]+\.[\w-]+|\"(access_token|refresh_token|client_secret|id_token)\"\s*:\s*\"[^\"]*\"")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_AUTH = re.compile(r"invalid_grant|invalid_rapt|invalid_scope|RefreshError|DefaultCredentialsError|"
                   r"application-default login|reauthenticat|EOFError", re.I)
_UNAVAILABLE = re.compile(r"Service Unavailable|\b503\b|\b412\b|Precondition Failed|too many active sessions|"
                          r"capacity|usage limit", re.I)
_GONE = re.compile(r"Session '[^']*' not found")


class ColabError(RuntimeError):
    pass


class ColabAuthError(ColabError):
    def __init__(self) -> None:
        super().__init__(AUTH_MESSAGE)


class _Transport(ColabError):
    """A connection dropped or a CLI call hung; the VM and its job may be fine."""


class _Gone(ColabError):
    """The Colab session no longer exists."""


class _Cancelled(ColabError):
    pass


def _redact(text) -> str:
    if isinstance(text, bytes):
        text = text.decode(errors="replace")
    return _ANSI.sub("", _REDACT.sub("[REDACTED]", text or ""))


def _reason(text: str) -> str:
    """The CLI's own error line (it prints `[colab] …` or ends a traceback with `SomeError: …`)."""
    lines = [ln.strip() for ln in _redact(text).splitlines() if ln.strip() and not ln.strip().startswith(("│", "╰", "╭"))]
    for ln in reversed(lines):
        if ln.startswith("[colab]") or re.match(r"^\w*(Error|Exception)\b", ln):
            return ln[:300]
    return (lines[-1] if lines else "no output")[:300]


# ── Budget (provider-independent: sums of GpuUsage) ────────────────────────


def rate(gpu: str) -> float:
    return GPU_PRICES[gpu]


def configured() -> bool:
    """Cheap and offline: the CLI is installed and a credentials file exists (Linux/macOS only)."""
    if sys.platform == "win32" or not settings.colab_credentials_file:
        return False
    return _bin() is not None and Path(settings.colab_credentials_file).expanduser().is_file()


def gpu_budget(project_id: str) -> float:
    with Session(engine) as s:
        cfg = s.get(Project, project_id).settings or {}
    budget = float(cfg.get("gpu_budget_usd", DEFAULT_GPU_BUDGET))
    # Private beta: GPU jobs may not plan to spend past the owner's remaining allowance.
    return min(budget, gpu_spent(project_id) + project_allowance(project_id))


def gpu_spent(project_id: str) -> float:
    with Session(engine) as s:
        return float(s.exec(select(func.coalesce(func.sum(GpuUsage.cost), 0.0))
                            .where(GpuUsage.project_id == project_id)).one())


def _skip(rel: Path) -> bool:
    return any(p.startswith(".") or p == "__pycache__" for p in rel.parts)


def _running_seconds(time_file: Path) -> float | None:
    """Seconds between the on-VM start and end stamps, if both were written."""
    if not time_file.exists():
        return None
    stamps = dict(line.split()[:2] for line in time_file.read_text().splitlines() if line.startswith("__OS_"))
    try:
        return float(stamps["__OS_END__"]) - float(stamps["__OS_START__"])
    except (KeyError, ValueError):
        return None


# ── The CLI ────────────────────────────────────────────────────────────────


def _bin() -> str | None:
    venv = Path(sys.executable).with_name("colab")
    return str(venv) if venv.exists() else shutil.which("colab")


def _prepare_home() -> None:
    """The CLI runs with HOME=COLAB_HOME: its state stays out of the user's own CLI setup."""
    cfg = COLAB_HOME / ".config" / "colab-cli"
    for d in (COLAB_HOME, COLAB_HOME / "sessions", COLAB_HOME / "tmp", COLAB_HOME / ".config", cfg):
        d.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not (cfg / "settings.json").exists():
        (cfg / "settings.json").write_text('{"enable_update_check": false}\n')
    debug_log = cfg / "colab.log"  # the CLI's DEBUG log records request headers, bearer tokens included
    if os.name != "nt" and not debug_log.is_symlink():
        debug_log.unlink(missing_ok=True)
        with contextlib.suppress(FileExistsError):  # a concurrent call got there first
            debug_log.symlink_to("/dev/null")


def _cfg(session: str) -> Path:
    return COLAB_HOME / "sessions" / f"{session}.json"


def _cli(args: list[str], timeout: float, session: str | None = None) -> tuple[int | str, str, str]:
    """Run one CLI command: our own timeout, no stdin (an auth prompt fails instead of hanging),
    a minimal environment (no backend secrets), its own process group (survives a terminal ^C)."""
    exe = _bin()
    if exe is None:
        raise ColabError("The colab CLI is not installed")
    argv = [exe, "--auth=adc"] + (["--config", str(_cfg(session))] if session else []) + args
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8", "HOME": str(COLAB_HOME),
           "GOOGLE_APPLICATION_CREDENTIALS": str(Path(settings.colab_credentials_file or "").expanduser())}
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env, stdin=subprocess.DEVNULL,
                           start_new_session=True, umask=0o077)
        rc, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as exc:
        rc, out, err = "TIMEOUT", _redact(exc.stdout), _redact(exc.stderr)
    if rc != 0 and _AUTH.search(out + err):
        log.error("%s", AUTH_MESSAGE)
        raise ColabAuthError()
    return rc, out, err


def balance() -> tuple[float, float, int]:
    """(compute units left, current usage per hour, active assignments) from `colab usage`."""
    rc, out, err = _cli(["usage"], 120)
    b = re.search(r"Current balance:\s*([\d.]+)", out)
    r = re.search(r"Usage rate:\s*([\d.]+)", out)
    a = re.search(r"Active assignments:\s*(\d+)", out)
    if not b:  # fail safe: no compute-unit floor without a readable balance
        raise ColabError(f"Could not read the Colab compute-unit balance: {_reason(out + err)}")
    return float(b[1]), float(r[1]) if r else 0.0, int(a[1]) if a else 0


def _code(script: str, params: dict) -> str:
    """A remote step: parameters travel as base64 JSON; the script sets OUT, printed as one JSON line."""
    p = base64.b64encode(json.dumps({"state": STATE, "root": REMOTE_ROOT, **params}).encode()).decode()
    return (f"import base64, json\nP = json.loads(base64.b64decode('{p}'))\n{script}\n"
            f"print({SENTINEL!r} + json.dumps(OUT))\n")


def _parse(out: str) -> dict | None:
    hits = [ln for ln in out.splitlines() if ln.startswith(SENTINEL)]
    return json.loads(hits[-1][len(SENTINEL):]) if hits else None


def _tmp() -> Path:
    return COLAB_HOME / "tmp" / secrets.token_hex(8)


def _pause(cancel: threading.Event | None, seconds: float) -> bool:
    """Sleep, waking early on cancellation; True if cancelled."""
    return (cancel or threading.Event()).wait(seconds)


def _exec(session: str, script: str, params: dict, timeout: float, retries: int = 2,
          cancel: threading.Event | None = None) -> dict:
    """Run a remote step. `colab exec` exits 0 even when the code raises, so only the result line
    counts. Dropped connections leave the CLI hanging: the timeout is tight and the step is retried."""
    path = _tmp()
    path.write_text(_code(script, params))
    try:
        for attempt in range(retries + 1):
            rc, out, err = _cli(["exec", "-s", session, "-f", str(path), "--timeout", str(int(timeout))],
                                timeout + 30, session)
            res = _parse(out)
            if res is not None:
                return res
            if _GONE.search(out):
                raise _Gone(f"Colab session {session} is gone")
            if attempt == retries or _pause(cancel, min(3 * RETRY_S, RETRY_S * (attempt + 1))):
                break
        raise _Transport(f"Colab step failed: {_reason(out + err)}")
    finally:
        path.unlink(missing_ok=True)


# ── Remote steps (run in the VM's Jupyter kernel; P = parameters, OUT = result) ──

_GPUCHECK = '''
import os, subprocess
for d in ("in", "jobs", "out"):
    os.makedirs(P["state"] + "/" + d, exist_ok=True)
try:
    r = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], capture_output=True, text=True)
    OUT = {"gpu": r.stdout.strip() if r.returncode == 0 else ""}
except FileNotFoundError:
    OUT = {"gpu": ""}
'''

_SETUP = '''
import hashlib, os, shutil, subprocess, sys
S = P["state"]
arc = S + "/ws.tgz"
def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()
if not (os.path.exists(arc) and sha(arc) == P["sha"]):
    with open(arc, "wb") as w:
        for i in range(P["parts"]):
            with open(f"{S}/in/part_{i:03d}", "rb") as f:
                shutil.copyfileobj(f, w)
OUT = {"sha_ok": sha(arc) == P["sha"]}
if OUT["sha_ok"]:
    shutil.rmtree(S + "/in", ignore_errors=True)
    if P["packages"]:
        cmd = (["uv", "pip", "install", "--system"] if shutil.which("uv") else [sys.executable, "-m", "pip", "install"])
        try:
            r = subprocess.run(cmd + P["packages"], capture_output=True, text=True, timeout=1200)
            OUT["pip_rc"], OUT["pip_tail"] = r.returncode, (r.stdout + r.stderr)[-1500:]
        except subprocess.TimeoutExpired:
            OUT["pip_rc"], OUT["pip_tail"] = "timeout", "pip install took longer than 20 minutes"
    env = subprocess.run("python --version; nvidia-smi; pip freeze", shell=True, capture_output=True, text=True, timeout=300)
    with open(S + "/environment.txt", "w") as f:
        f.write(env.stdout)
'''

_KILL_SESSION = '''
import os, signal
def kill_session(sid):
    """SIGKILL every process in a job's session (coreutils timeout moves the job to its own group)."""
    for d in os.listdir("/proc"):
        if d.isdigit():
            try:
                if os.getsid(int(d)) == sid:
                    os.kill(int(d), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
'''

_LAUNCH = _KILL_SESSION + '''
import json, shutil, subprocess, tarfile
S, W, n = P["state"], P["root"], P["name"]
J = f"{S}/jobs/{n}"
def running(pid):
    try:
        return open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False
if os.path.exists(J + ".pid") and running(int(open(J + ".pid").read())):
    OUT = {"pid": int(open(J + ".pid").read()), "resumed": True}  # a retried launch never starts a second copy
else:
    for f in os.listdir(S + "/jobs"):  # leftovers of earlier jobs on this VM
        if f.endswith(".pid"):
            kill_session(int(open(f"{S}/jobs/{f}").read()))
    shutil.rmtree(S + "/out", ignore_errors=True)
    os.makedirs(S + "/out")
    for s in (".exit", ".exit.tmp"):
        if os.path.exists(J + s):
            os.remove(J + s)
    shutil.rmtree(W, ignore_errors=True)
    os.makedirs(W)
    with tarfile.open(S + "/ws.tgz") as tar:
        tar.extractall(W, filter="data")
    base = {}
    for dp, dn, fn in os.walk(W):
        for f in fn:
            st = os.lstat(os.path.join(dp, f))
            base[os.path.relpath(os.path.join(dp, f), W)] = [st.st_size, st.st_mtime_ns, st.st_ctime_ns]
    with open(J + ".base.json", "w") as f:
        json.dump(base, f)
    with open(J + ".sh", "w") as f:
        f.write(P["command"] + "\\n")
    L, X = f"{W}/logs/gpu/{n}.log", J + ".exit"
    wrapper = (f"mkdir -p {W}/logs/gpu && echo __OS_START__ $(date +%s) > {L}.time && "
               f"{{ timeout -k 30 {P['timeout']} bash {J}.sh ; }} > {L} 2>&1; rc=$?; "
               f"echo __OS_END__ $(date +%s) >> {L}.time; "
               f"nvidia-smi --query-gpu=name --format=csv,noheader >> {L} 2>/dev/null; sync; "
               f"echo $rc > {X}.tmp && mv {X}.tmp {X}")
    p = subprocess.Popen(["bash", "-c", wrapper], cwd=W, env={**os.environ, "MPLBACKEND": "Agg", "PYTHONUNBUFFERED": "1"},
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    with open(J + ".pid", "w") as f:
        f.write(str(p.pid))
    OUT = {"pid": p.pid, "resumed": False}
'''

_WAIT = '''
import os, time
X, end = f"{P['state']}/jobs/{P['name']}.exit", time.time() + P["chunk"]
def rc():
    try:
        text = open(X).read().strip()
        return int(text) if text else None
    except (OSError, ValueError):
        return None
while time.time() < end and rc() is None:
    time.sleep(2)
OUT = {"rc": rc()}
'''

_KILL = _KILL_SESSION + '''
pid_file = f"{P['state']}/jobs/{P['name']}.pid"
if os.path.exists(pid_file):
    kill_session(int(open(pid_file).read()))
OUT = {"killed": os.path.exists(pid_file)}
'''

_COLLECT = '''
import hashlib, json, os, shutil, stat, tarfile
S, W, n = P["state"], P["root"], P["name"]
base = json.load(open(f"{S}/jobs/{n}.base.json"))
changed = []
for dp, dn, fn in os.walk(W):
    dn[:] = [d for d in dn if not d.startswith(".") and d != "__pycache__"]
    for f in fn:
        p = os.path.join(dp, f)
        try:
            st = os.lstat(p)
        except OSError:
            continue
        rel = os.path.relpath(p, W)
        if f.startswith(".") or not stat.S_ISREG(st.st_mode):
            continue
        if base.get(rel) != [st.st_size, st.st_mtime_ns, st.st_ctime_ns]:
            changed.append(rel)
out = f"{S}/out/{n}"
shutil.rmtree(out, ignore_errors=True)
os.makedirs(out)
with tarfile.open(out + ".tgz", "w:gz", compresslevel=1) as tar:
    for rel in changed:
        try:
            tar.add(os.path.join(W, rel), arcname=rel, recursive=False)
        except OSError:
            pass
h, parts = hashlib.sha256(), 0
with open(out + ".tgz", "rb") as f:
    for b in iter(lambda: f.read(P["part"]), b""):
        h.update(b)
        with open(f"{out}/part_{parts:03d}", "wb") as w:
            w.write(b)
        parts += 1
os.remove(out + ".tgz")
OUT = {"files": len(changed), "parts": parts, "sha": h.hexdigest()}
'''


# ── Session ledger: what to stop after a crash ─────────────────────────────


def _proc_start(pid: int) -> str | None:
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def _boot_id() -> str | None:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return None


def _write_owner(session: str, project_id: str, gpu: str, job_seconds: float = 0.0, created: float | None = None) -> None:
    """The ledger entry; job_seconds is what is already metered, so a reaper can meter the rest."""
    owner = {"pid": os.getpid(), "start": _proc_start(os.getpid()), "boot": _boot_id(), "project_id": project_id,
             "gpu": gpu, "created": created or time.time(), "job_seconds": job_seconds}
    path = COLAB_HOME / "sessions" / f"{session}.owner"
    tmp = path.with_suffix(".owner.tmp")
    tmp.write_text(json.dumps(owner))
    os.replace(tmp, path)


def _meter_orphan(owner: dict) -> None:
    """Bill a reaped session's unmetered time (it ran, unwatched, until now) to its project."""
    seconds = max(0.0, time.time() - owner.get("created", time.time()) - owner.get("job_seconds", 0.0))
    project_id = owner.get("project_id")
    with Session(engine) as s:
        s.add(GpuUsage(project_id=project_id, user_id=owner_of(project_id), gpu=owner.get("gpu", "?"),
                       job="(orphaned session)", seconds=round(seconds, 1),
                       cost=round(seconds * GPU_PRICES.get(owner.get("gpu"), 0.0), 4)))
        s.commit()


def _owner_alive(owner: dict) -> bool:
    if owner.get("boot") != _boot_id() or time.time() - owner.get("created", 0) > MAX_SESSION_S + 3600:
        return False
    if owner.get("start") is not None:
        return _proc_start(owner["pid"]) == owner["start"]
    if sys.platform == "win32":  # no /proc, and os.kill(pid, 0) would send CTRL_C: never reap there
        return True
    try:
        os.kill(owner["pid"], 0)
        return True
    except OSError:
        return False


def _kill_cli(session: str) -> int:
    """Kill CLI processes a crashed backend left working on a session. They run in their own process
    group, so they outlive it; a dropped connection can leave one hanging, and when it exits it
    rewrites the session's state file after we have forgotten it. Matched by its --config path."""
    marker, killed = str(_cfg(session)).encode(), 0
    proc = Path("/proc")
    for d in proc.iterdir() if proc.is_dir() else []:
        if d.name.isdigit() and int(d.name) != os.getpid():
            try:
                if marker in (d / "cmdline").read_bytes():
                    os.kill(int(d.name), signal.SIGKILL)
                    killed += 1
            except OSError:
                pass
    return killed


def _stop(session: str) -> bool:
    """Stop a session; True once Colab confirms it is gone."""
    for attempt in range(3):
        try:
            rc, out, err = _cli(["stop", "-s", session], 120, session)
        except ColabAuthError:
            return False
        if "terminated" in out or _GONE.search(out):
            return True
        time.sleep(RETRY_S / 2 * (attempt + 1))
    return False


def _forget(session: str) -> None:
    sessions = COLAB_HOME / "sessions"
    for p in (sessions / f"{session}.json", sessions / f"{session}.json.lock", sessions / f"{session}.owner",
              sessions / f"{session}.owner.tmp", sessions / f"{session}.reaping",
              COLAB_HOME / ".config" / "colab-cli" / "history" / f"{session}.jsonl"):
        p.unlink(missing_ok=True)


def reap() -> int:
    """Stop sessions whose owning backend process is gone (crash, kill -9, reboot). Live owners —
    this process, another backend, an integration test — are never touched."""
    stopped = 0
    for owner_file in sorted((COLAB_HOME / "sessions").glob("*.owner")) + sorted((COLAB_HOME / "sessions").glob("*.reaping")):
        session = owner_file.stem
        try:
            owner = json.loads(owner_file.read_text())
        except (OSError, ValueError):
            owner = {}
        if owner_file.suffix == ".reaping":
            if time.time() - owner_file.stat().st_mtime < 600:
                continue  # another reaper is on it
        elif owner and _owner_alive(owner):
            continue
        claim = owner_file.with_suffix(".reaping")
        try:
            os.replace(owner_file, claim) if owner_file != claim else claim.touch()
        except OSError:
            continue
        _kill_cli(session)
        if _stop(session):
            if owner:
                _meter_orphan(owner)
            _forget(session)
            stopped += 1
        else:
            log.error("Could not stop orphaned Colab session %s; it may still be billing. Stop it at "
                      "colab.research.google.com or run `python -m app.execution.colab_runner reap`.", session)
            os.replace(claim, claim.with_suffix(".owner"))
    return stopped


def start_reaper() -> None:
    """At startup: stop sessions a previous backend process left running (idle VMs keep billing)."""
    if configured():
        threading.Thread(target=_startup_check, name="colab-reaper", daemon=True).start()


def _startup_check() -> None:
    try:
        _prepare_home()
        stopped = reap()
        if stopped:
            log.warning("Stopped %d orphaned Colab session(s) left by a previous run", stopped)
        _, _, active = balance()
        owned = len(list((COLAB_HOME / "sessions").glob("*.owner")))
        if active > owned:
            log.warning("Colab reports %d active session(s) OpenScientist does not own (your own notebooks?); "
                        "they were left running", active - owned)
    except ColabAuthError:
        pass  # already logged
    except Exception as exc:
        log.warning("Colab startup check failed: %s", _redact(str(exc)))


# ── One call ───────────────────────────────────────────────────────────────


@dataclass
class _Session:
    name: str
    created: float
    job_seconds: float = 0.0
    lost: bool = False


def _max_sessions() -> int:
    return max(1, int(settings.colab_max_sessions))


_host_lock = threading.Lock()  # one writer into a workspace at a time


class _Call:
    def __init__(self, project_id: str, root: Path, jobs: list[dict], gpu: str, timeout_s: int, packages: list[str]):
        self.project_id, self.root, self.jobs, self.gpu = project_id, root.resolve(), jobs, gpu
        self.timeout_s, self.packages = timeout_s, packages
        self.run_id, self.user_id = current_run.get(), owner_of(project_id)  # worker threads lack the context
        self.cancel = threading.Event()
        self.started = time.time()
        self.pending = deque(range(len(jobs)))
        self.results: list[dict | None] = [None] * len(jobs)
        self.not_run = "not run: no Colab session could be started"
        self.fatal = False  # a failure every session would repeat (bad packages, credentials)
        self.changed: list[str] = []
        self.skipped: list[str] = []
        self.archive = _tmp()
        self.sha, self.parts, self.archive_bytes = "", 0, 0
        self._lock = threading.Lock()

    def take(self) -> int | None:
        with self._lock:
            return self.pending.popleft() if self.pending else None

    def give_back(self, i: int) -> None:
        with self._lock:
            self.pending.appendleft(i)

    def synced(self, files: list[str]) -> None:
        with self._lock:
            self.changed += [f for f in files if f not in self.changed]

    def prepare(self) -> None:
        """Before any VM exists: reap, refuse what the budget or balance cannot cover, pack the workspace."""
        _prepare_home()
        reap()
        cu_left, _, _ = balance()
        self._pack()
        workers = min(_max_sessions(), len(self.jobs))
        per_worker = math.ceil(len(self.jobs) / workers) * (self.timeout_s + PER_JOB_OVERHEAD_S)
        sessions = workers * max(1, math.ceil(per_worker / (MAX_SESSION_S - SESSION_OVERHEAD_S)))
        worst_s = (len(self.jobs) * (self.timeout_s + PER_JOB_OVERHEAD_S)
                   + sessions * (SESSION_OVERHEAD_S + self.archive_bytes / TRANSFER_BYTES_PER_S))
        worst_usd = worst_s * rate(self.gpu)
        remaining = gpu_budget(self.project_id) - gpu_spent(self.project_id)
        if worst_usd > remaining:
            raise ColabError(f"Refused: worst case {len(self.jobs)} jobs x {self.timeout_s // 60} min on {self.gpu} plus "
                             f"Colab session start-up = ${worst_usd:.2f}, but only ${remaining:.2f} of the GPU budget "
                             f"remains. Lower timeout_minutes or use fewer jobs.")
        worst_cu = worst_s / 3600 * CU_PER_HOUR[self.gpu]
        if cu_left - worst_cu < MIN_BALANCE_CU:
            raise ColabError(f"Refused: the Colab account has {cu_left:.2f} compute units; this call could use "
                             f"{worst_cu:.2f} and at least {MIN_BALANCE_CU:.0f} must remain. Lower timeout_minutes "
                             f"or use fewer jobs.")

    def _pack(self) -> None:
        """tar.gz of the workspace with Modal's filter (no hidden dirs or caches; files ≤500 MB)."""
        with tarfile.open(self.archive, "w:gz", compresslevel=1) as tar:
            # os.walk prunes hidden dirs (never entering other calls' .tmp staging) and skips a dir that
            # vanishes mid-walk; other tasks and E2B syncs write into this workspace concurrently.
            for dirpath, dirnames, filenames in os.walk(self.root):
                dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d != "__pycache__")
                for name in sorted(filenames):
                    p = Path(dirpath) / name
                    rel = p.relative_to(self.root)
                    if _skip(rel):
                        continue
                    try:
                        if not p.is_file():
                            continue
                        if p.stat().st_size > MAX_SYNC_FILE_BYTES:
                            self.skipped.append(rel.as_posix())
                            continue
                        with p.open("rb") as f:  # follow file symlinks: the job gets the content, as on Modal
                            tar.addfile(tar.gettarinfo(arcname=rel.as_posix(), fileobj=f), f)
                    except OSError:
                        continue  # vanished or unreadable; never fail the call over it
        h = hashlib.sha256()
        with self.archive.open("rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        self.sha, self.archive_bytes = h.hexdigest(), self.archive.stat().st_size
        self.parts = max(1, math.ceil(self.archive_bytes / PART_BYTES))

    def finish(self) -> dict:
        for i, r in enumerate(self.results):
            if r is None:
                self.results[i] = _result(self, i, error=self.not_run)
        out = {"jobs": self.results, "files_synced_back": len(self.changed), "changed_files": self.changed[:50]}
        if self.skipped:
            out["skipped_uploads"] = self.skipped[:50]
        return out

    def cleanup(self) -> None:
        self.archive.unlink(missing_ok=True)


def _record(call: _Call, job: str, seconds: float) -> None:
    with Session(engine) as s:
        s.add(GpuUsage(project_id=call.project_id, user_id=call.user_id, run_id=call.run_id, gpu=call.gpu, job=job,
                       seconds=round(seconds, 1), cost=round(seconds * rate(call.gpu), 4)))
        s.commit()


def _result(call: _Call, i: int, *, exit_code: int | None = None, seconds: float = 0.0, timed_out: bool = False,
            synced: bool = False, error: str | None = None) -> dict:
    """Modal's result shape. Logs are read only when this call synced them (never a stale log)."""
    log_rel = f"logs/gpu/{call.jobs[i]['name']}.log"
    path = call.root / log_rel
    r = {"name": call.jobs[i]["name"], "exit_code": exit_code, "seconds": round(seconds, 1), "log": log_rel}
    if error is not None:
        r["error"] = error
    else:
        r["timed_out"] = timed_out
    r["log_tail"] = "\n".join(path.read_text(errors="replace").splitlines()[-25:]) if synced and path.exists() else ""
    r["wall_seconds"] = round(time.time() - call.started, 1)  # includes waiting for a session and earlier jobs
    r["cost"] = round(r["seconds"] * rate(call.gpu), 4)
    return r


def _upload_part(call: _Call, s: _Session, i: int) -> None:
    part = _tmp()
    with call.archive.open("rb") as f:
        f.seek(i * PART_BYTES)
        part.write_bytes(f.read(PART_BYTES))
    try:
        for attempt in range(3):
            if call.cancel.is_set():
                raise _Cancelled("cancelled")
            rc, out, err = _cli(["upload", "-s", s.name, str(part), f"{CONTENTS}/in/part_{i:03d}"], 600, s.name)
            if "Uploaded" in out:
                return
            if _GONE.search(out):
                raise _Gone(f"Colab session {s.name} is gone")
            call.cancel.wait(RETRY_S / 2 * (attempt + 1))
        raise _Transport(f"workspace upload failed: {_reason(out + err)}")
    finally:
        part.unlink(missing_ok=True)


def _place(call: _Call, tmp: Path, rel: str) -> None:
    """Move a downloaded file into the workspace atomically (via a skipped staging dir on the same disk)."""
    dest = (call.root / rel).resolve()
    staging = call.root / ".tmp" / f"gpu-{secrets.token_hex(4)}"
    staging.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(tmp, staging)
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, dest)


def _open(call: _Call) -> _Session:
    """Allocate a VM of the requested GPU type and set it up (workspace, packages)."""
    cu_left, _, _ = balance()
    need = (call.timeout_s + PER_JOB_OVERHEAD_S + SESSION_OVERHEAD_S) / 3600 * CU_PER_HOUR[call.gpu]
    if cu_left - need < MIN_BALANCE_CU:
        raise ColabError(f"the Colab account is down to {cu_left:.2f} compute units (at least {MIN_BALANCE_CU:.0f} "
                         "must remain)")
    name = f"os-{re.sub(r'[^A-Za-z0-9]', '', call.project_id)[:12]}-{secrets.token_hex(3)}"
    _write_owner(name, call.project_id, call.gpu)  # before `new`: a crash mid-allocation is still reaped
    s, text = _Session(name, time.time()), ""
    for backoff in (*BACKOFF_S, None):
        rc, out, err = _cli(["new", "-s", name, "--gpu", call.gpu], 300, name)
        if "READY" in out:
            break
        text = out + err
        if backoff is None or not _UNAVAILABLE.search(text) or call.cancel.wait(backoff):
            if _stop(name):  # Colab may have assigned a VM despite the error
                _forget(name)
            raise ColabError(f"Colab could not start a {call.gpu} GPU: {_reason(text)}")
    try:
        gpu = _exec(name, _GPUCHECK, {}, 120, cancel=call.cancel)["gpu"]
        if call.gpu not in gpu:  # the CLI maps unknown types to A100 silently; never run on the wrong GPU
            raise ColabError(f"Colab gave this session {gpu or 'no GPU'} instead of {call.gpu}")
        for i in range(call.parts):
            _upload_part(call, s, i)
        r = _exec(name, _SETUP, {"sha": call.sha, "parts": call.parts, "packages": call.packages}, 1500, retries=1,
                  cancel=call.cancel)
        if not r.get("sha_ok"):
            raise ColabError("the workspace upload arrived corrupted")
        if r.get("pip_rc") not in (None, 0):
            call.fatal = True
            raise ColabError(f"pip install failed: {_redact(r.get('pip_tail', ''))[-800:]}")
        env = _tmp()
        rc, out, err = _cli(["download", "-s", name, f"{CONTENTS}/environment.txt", str(env)], 300, name)
        if "Downloaded" in out:
            _place(call, env, "logs/gpu/_environment.txt")  # exact versions, for reproducibility
        env.unlink(missing_ok=True)
    except BaseException:
        _close(call, s)
        raise
    return s


def _close(call: _Call, s: _Session) -> None:
    """Stop the VM and meter what the jobs did not: start-up, setup, transfers."""
    if _stop(s.name):
        _forget(s.name)
    else:
        log.error("Could not stop Colab session %s; it may still be billing. The reaper retries it.", s.name)
    _record(call, "(session overhead)", max(0.0, time.time() - s.created - s.job_seconds))


def _kill(call: _Call, s: _Session, name: str) -> None:
    with contextlib.suppress(ColabError):
        _exec(s.name, _KILL, {"name": name}, 60, retries=1)


def _wait(call: _Call, s: _Session, name: str, launched: float) -> tuple[int | None, bool]:
    """(exit code, killed by our deadline). Busy WAIT cells keep the VM active; dropped connections
    are retried until the deadline, because the detached job keeps running."""
    deadline, failures = launched + call.timeout_s + DEADLINE_GRACE_S, 0
    while True:
        if call.cancel.is_set():
            raise _Cancelled("cancelled")
        if time.time() > deadline:
            _kill(call, s, name)
            return None, True
        try:
            r = _exec(s.name, _WAIT, {"name": name, "chunk": WAIT_CHUNK_S}, WAIT_CHUNK_S + 20, retries=0)
        except _Transport:
            failures += 1
            if failures % 3 == 0:
                rc, out, err = _cli(["status", "-s", s.name], 60, s.name)  # prunes sessions Colab no longer has
                if _GONE.search(out):
                    raise _Gone(f"Colab session {s.name} is gone")
            call.cancel.wait(min(3 * RETRY_S, RETRY_S / 2 * failures))
            continue
        failures = 0
        if r["rc"] is not None:
            return r["rc"], False


def _download(call: _Call, s: _Session, name: str, parts: int, sha: str) -> Path:
    for _ in range(3):
        blob, h, ok = _tmp(), hashlib.sha256(), True
        with blob.open("wb") as w:
            for i in range(parts):
                part = _tmp()
                rc, out, err = _cli(["download", "-s", s.name, f"{CONTENTS}/out/{name}/part_{i:03d}", str(part)], 600, s.name)
                if "Downloaded" not in out:
                    part.unlink(missing_ok=True)
                    ok = False
                    break
                data = part.read_bytes()
                part.unlink()
                h.update(data)
                w.write(data)
        if ok and h.hexdigest() == sha:
            return blob
        blob.unlink(missing_ok=True)
    raise ColabError("its output files could not be downloaded intact; nothing was synced")


def _extract(call: _Call, blob: Path) -> list[str]:
    """Unpack into a skipped staging dir, then move each file into place atomically, so E2B's
    sync never sees a half-written file. Never writes outside the workspace."""
    staging = call.root / ".tmp" / f"gpu-{secrets.token_hex(4)}"
    staging.mkdir(parents=True)
    synced = []
    try:
        with _host_lock, tarfile.open(blob, "r:gz") as tar:
            for m in tar:
                rel = Path(m.name)
                dest = (call.root / rel).resolve()
                if not m.isfile() or _skip(rel) or call.root not in dest.parents:
                    continue
                try:
                    tar.extract(m, staging, filter="data")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(staging / rel, dest)
                    synced.append(rel.as_posix())
                except (OSError, tarfile.TarError) as exc:
                    log.warning("Skipped %s from Colab: %s", m.name, exc)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return synced


def _run_job(call: _Call, s: _Session, i: int) -> dict:
    name, launched = call.jobs[i]["name"], time.time()
    rc, timed_out, collected = None, False, False
    try:
        _exec(s.name, _LAUNCH, {"name": name, "timeout": call.timeout_s, "command": call.jobs[i]["command"]},
              120 + call.archive_bytes / 20e6, cancel=call.cancel)
        rc, killed = _wait(call, s, name, launched)
        c = _exec(s.name, _COLLECT, {"name": name, "part": PART_BYTES}, 600, cancel=call.cancel)
        blob = _download(call, s, name, c["parts"], c["sha"])
        try:
            files = _extract(call, blob)
        finally:
            blob.unlink(missing_ok=True)
        call.synced(files)
        collected = f"logs/gpu/{name}.log" in files
        run = _running_seconds(call.root / f"logs/gpu/{name}.log.time") if collected else None
        seconds = run if run is not None else time.time() - launched
        timed_out = killed or (rc in (124, 137) and seconds >= call.timeout_s - 1)
        result = _result(call, i, exit_code=rc, seconds=seconds, timed_out=timed_out, synced=collected)
    except _Cancelled:
        _kill(call, s, name)
        result = _result(call, i, seconds=time.time() - launched, error="cancelled")
    except _Gone:
        s.lost = True
        result = _result(call, i, seconds=time.time() - launched,
                         error=f"Colab runtime lost after {time.time() - launched:.0f} s; the job did not finish "
                               "and no results were synced")
    except ColabError as exc:  # transport retries exhausted, a download that never verified, credentials
        s.lost = rc is None
        if isinstance(exc, ColabAuthError):
            call.fatal, call.not_run = True, f"not run: {AUTH_MESSAGE}"
        result = _result(call, i, exit_code=rc, seconds=time.time() - launched, error=_redact(str(exc)))
    s.job_seconds += result["seconds"]
    _record(call, name, result["seconds"])
    _write_owner(s.name, call.project_id, call.gpu, s.job_seconds, s.created)  # metered so far, for the reaper
    return result


def _worker(call: _Call) -> None:
    """Run jobs from the call's queue on one VM at a time, rotating VMs before Colab's lifetime limit."""
    s = None
    try:
        while not call.cancel.is_set() and not call.fatal:
            i = call.take()
            if i is None:
                return
            if s is not None and time.time() - s.created + call.timeout_s + PER_JOB_OVERHEAD_S > MAX_SESSION_S:
                _close(call, s)
                s = None
            if s is None:
                try:
                    s = _open(call)
                except Exception as exc:
                    call.give_back(i)
                    call.fatal = call.fatal or isinstance(exc, ColabAuthError)
                    call.not_run = f"not run: {_redact(str(exc))}"
                    log.warning("Colab session for %s could not start: %s", call.project_id, call.not_run)
                    return
            call.results[i] = _run_job(call, s, i)
            if s.lost:
                if not call.fatal:
                    call.not_run = "not run: the Colab runtime was lost"
                return
    finally:
        if s is not None:
            _close(call, s)


_pool: asyncio.Semaphore | None = None
_pool_loop: asyncio.AbstractEventLoop | None = None


def _slots() -> asyncio.Semaphore:
    """One pool of Colab sessions for the whole backend (the account's concurrency is limited)."""
    global _pool, _pool_loop
    loop = asyncio.get_running_loop()
    if _pool is None or _pool_loop is not loop:
        _pool, _pool_loop = asyncio.Semaphore(_max_sessions()), loop
    return _pool


async def run_async(project_id: str, root: Path, jobs: list[dict], gpu: str, timeout_s: int,
                    packages: list[str]) -> dict:
    """Run jobs on Colab GPUs. Waiting for a session costs nothing and is cancellable; on cancellation
    running jobs are killed and their VMs stopped before this returns."""
    call = _Call(project_id, Path(root), jobs, gpu, timeout_s, packages)
    try:
        await asyncio.to_thread(call.prepare)
        holding: set[asyncio.Task] = set()

        async def worker() -> None:
            async with _slots():
                if call.cancel.is_set() or call.fatal or not call.pending:
                    return
                holding.add(asyncio.current_task())
                await asyncio.to_thread(_worker, call)

        tasks = [asyncio.create_task(worker()) for _ in range(min(_max_sessions(), len(jobs)))]
        try:
            await asyncio.shield(asyncio.gather(*tasks))
        except asyncio.CancelledError:
            call.cancel.set()
            for t in tasks:
                if t not in holding:
                    t.cancel()
            with contextlib.suppress(BaseException):
                await asyncio.gather(*tasks, return_exceptions=True)  # until their VMs are stopped
            raise
        return await asyncio.to_thread(call.finish)
    finally:
        call.cleanup()


def run_jobs(project_id: str, root: Path, jobs: list[dict], gpu: str, timeout_s: int, packages: list[str]) -> dict:
    """Blocking entry point for scripts (the backend awaits run_async, which shares the session pool)."""
    return asyncio.run(run_async(project_id, root, jobs, gpu, timeout_s, packages))


def _main(argv: list[str]) -> int:
    """`python -m app.execution.colab_runner check|reap` — setup verification and crash cleanup."""
    command = argv[1] if len(argv) > 1 else "check"
    if not configured():
        print("Colab is not configured: install google-colab-cli (Linux/macOS) and set COLAB_CREDENTIALS_FILE")
        return 2
    _prepare_home()
    try:
        if command == "reap":
            print(f"Stopped {reap()} orphaned Colab session(s)")
            return 0
        cu_left, usage_rate, active = balance()
    except ColabError as exc:
        print(f"FAILED: {exc}")
        return 1
    owned = len(list((COLAB_HOME / "sessions").glob("*.owner")))
    print(f"Colab OK: {cu_left:.2f} compute units left, usage {usage_rate:.2f}/h, {active} active session(s), "
          f"{owned} owned by OpenScientist")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
