"""Cloud GPU jobs on Modal.

Agents work in the local sandbox and send heavy computation here: each job runs in
its own Modal Sandbox (one GPU each, all jobs in parallel) with the project
workspace mounted from a Modal Volume. Files are synced up before the jobs and
changed or new files are synced back afterwards. GPU spend is metered per second
and capped per project.
"""

import os
import time
from pathlib import Path

from sqlmodel import Session, func, select

from ..db import GpuUsage, Project, engine
from ..llm import current_run

# USD per second (modal.com/pricing). Sandboxes also bill CPU and memory at the
# sandbox tier; each job reserves 2 cores and 8 GiB.
GPU_PRICES = {
    "T4": 0.000164,
    "L4": 0.000222,
    "A10": 0.000306,
    "L40S": 0.000542,
    "A100-40GB": 0.000583,
    "A100-80GB": 0.000694,
    "H100": 0.001097,
}
CPU_CORES, MEMORY_GIB = 2, 8
SANDBOX_CPU, SANDBOX_MEM = 0.00003942, 0.00000667
DEFAULT_GPU_BUDGET = 10.0
MAX_PARALLEL_JOBS = 40
MAX_SYNC_FILE_BYTES = 500 * 1024**2
APP_NAME = "openscientist"


def rate(gpu: str) -> float:
    return GPU_PRICES[gpu] + CPU_CORES * SANDBOX_CPU + MEMORY_GIB * SANDBOX_MEM


def configured() -> bool:
    return Path("~/.modal.toml").expanduser().exists() or bool(os.environ.get("MODAL_TOKEN_ID"))


def gpu_budget(project_id: str) -> float:
    with Session(engine) as s:
        cfg = s.get(Project, project_id).settings or {}
    return float(cfg.get("gpu_budget_usd", DEFAULT_GPU_BUDGET))


def gpu_spent(project_id: str) -> float:
    with Session(engine) as s:
        return float(s.exec(select(func.coalesce(func.sum(GpuUsage.cost), 0.0))
                            .where(GpuUsage.project_id == project_id)).one())


def _skip(rel: Path) -> bool:
    return any(p.startswith(".") or p == "__pycache__" for p in rel.parts)


def _upload(vol, root: Path) -> dict[str, int]:
    """Upload the workspace (minus environments, caches and huge files); return path → size."""
    manifest: dict[str, int] = {}
    with vol.batch_upload(force=True) as batch:
        for p in root.rglob("*"):
            rel = p.relative_to(root)
            if p.is_file() and not _skip(rel) and p.stat().st_size <= MAX_SYNC_FILE_BYTES:
                batch.put_file(str(p), "/" + str(rel))
                manifest[str(rel)] = p.stat().st_size
    return manifest


def _download(vol, root: Path, manifest: dict[str, int], since: float) -> list[str]:
    """Bring back files the jobs created or changed."""
    changed = []
    for entry in vol.listdir("/", recursive=True):
        if entry.type.name != "FILE":
            continue
        rel = entry.path.lstrip("/")
        if _skip(Path(rel)):
            continue
        if rel in manifest and manifest[rel] == entry.size and entry.mtime <= since:
            continue
        dest = (root / rel).resolve()
        if root not in dest.parents:
            continue  # never write outside the workspace
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as f:
            vol.read_file_into_fileobj(entry.path, f)
        changed.append(rel)
    return changed


CONTAINER_STARTUP_S = 45


def _running_seconds(time_file: Path) -> float | None:
    """Seconds between the in-container start and end stamps, if both were written."""
    if not time_file.exists():
        return None
    stamps = dict(line.split()[:2] for line in time_file.read_text().splitlines() if line.startswith("__OS_"))
    try:
        return float(stamps["__OS_END__"]) - float(stamps["__OS_START__"])
    except (KeyError, ValueError):
        return None


def run_jobs(project_id: str, root: Path, jobs: list[dict], gpu: str, timeout_s: int,
             packages: list[str]) -> dict:
    """Run jobs in parallel Modal sandboxes (blocking; call from a thread)."""
    import modal
    from concurrent.futures import ThreadPoolExecutor

    app = modal.App.lookup(APP_NAME, create_if_missing=True)
    image = modal.Image.debian_slim(python_version="3.12").uv_pip_install(*packages)
    vol = modal.Volume.from_name(f"{APP_NAME}-{project_id}", create_if_missing=True)
    since = time.time()
    manifest = _upload(vol, root)

    def one(job: dict) -> dict:
        name = job["name"]
        log = f"logs/gpu/{name}.log"
        # Timestamps written inside the container: billing covers running time, not queueing
        # for a free GPU (plans cap concurrent GPUs, so large grids wait in waves).
        script = (f"mkdir -p logs/gpu && echo __OS_START__ $(date +%s) > {log}.time && "
                  f"{{ {job['command']} ; }} > {log} 2>&1; rc=$?; echo __OS_END__ $(date +%s) >> {log}.time; "
                  f"nvidia-smi --query-gpu=name --format=csv,noheader >> {log} 2>/dev/null; sync; exit $rc")
        start = time.time()
        try:
            sb = modal.Sandbox.create("bash", "-c", script, app=app, image=image, gpu=gpu,
                                      cpu=CPU_CORES, memory=MEMORY_GIB * 1024, timeout=timeout_s,
                                      volumes={"/workspace": vol}, workdir="/workspace")
            sb.wait(raise_on_termination=False)
            code = sb.returncode
        except Exception as exc:  # surfaced to the agent, which can adapt
            return {"name": name, "exit_code": None, "error": f"{type(exc).__name__}: {exc}",
                    "seconds": round(time.time() - start, 1), "log": log}
        return {"name": name, "exit_code": code, "seconds": round(time.time() - start, 1), "log": log,
                "timed_out": code is None or (time.time() - start) >= timeout_s - 2}

    with ThreadPoolExecutor(max_workers=min(len(jobs), MAX_PARALLEL_JOBS)) as pool:
        results = list(pool.map(one, jobs))

    changed = _download(vol, root, manifest, since)
    for r in results:
        path = root / r["log"]
        r["log_tail"] = "\n".join(path.read_text(errors="replace").splitlines()[-25:]) if path.exists() else ""
        r["wall_seconds"] = r["seconds"]  # includes queueing for a GPU
        run = _running_seconds(root / f"{r['log']}.time")
        if run is not None:
            # Running time plus container start-up (~45 s), which Modal also bills.
            r["seconds"] = round(run + CONTAINER_STARTUP_S, 1)
        r["cost"] = round(r["seconds"] * rate(gpu), 4)
    with Session(engine) as s:
        for r in results:
            s.add(GpuUsage(project_id=project_id, run_id=current_run.get(), gpu=gpu, job=r["name"],
                           seconds=r["seconds"], cost=r["cost"]))
        s.commit()
    return {"jobs": results, "files_synced_back": len(changed), "changed_files": changed[:50]}
