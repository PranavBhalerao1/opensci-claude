"""In-process background jobs for long stages. Progress lives in the Run table so
the UI can poll it and a page refresh never loses state."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from sqlmodel import Session, select

from .db import Run, engine
from .llm import current_project, current_run

log = logging.getLogger("openscientist.jobs")
_tasks: dict[str, asyncio.Task] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RunHandle:
    """Write-through progress reporting for one Run row."""

    def __init__(self, run_id: str):
        self.run_id = run_id

    def _update(self, fn: Callable[[Run], None]) -> None:
        with Session(engine) as s:
            run = s.get(Run, self.run_id)
            fn(run)
            s.add(run)
            s.commit()

    def phase(self, phase: str, text: str | None = None) -> None:
        def f(run: Run) -> None:
            run.phase = phase
            if text:
                run.log = [*run.log, {"t": _now().isoformat(), "text": text}]

        self._update(f)

    def note(self, text: str) -> None:
        self._update(lambda run: setattr(run, "log", [*run.log, {"t": _now().isoformat(), "text": text}]))

    def counts(self, **counts: int) -> None:
        self._update(lambda run: setattr(run, "counts", {**run.counts, **counts}))


def is_running(project_id: str, kind: str) -> bool:
    task = _tasks.get(f"{project_id}:{kind}")
    return bool(task and not task.done())


def start(
    project_id: str,
    kind: str,
    job: Callable[[str, RunHandle], Awaitable[dict]],
    then: Callable[[str], Awaitable[None]] | None = None,
) -> Run:
    """Create a Run and execute `job(project_id, handle)` in the background.

    Must be called from the event loop (an `async def` route or coroutine); sync
    FastAPI routes run in a worker thread with no loop to schedule the task on.
    """
    asyncio.get_running_loop()  # fail fast, before a Run row is left dangling
    key = f"{project_id}:{kind}"
    if is_running(project_id, kind):
        raise RuntimeError(f"A {kind} run is already in progress")

    with Session(engine) as s:
        run = Run(project_id=project_id, kind=kind)
        s.add(run)
        s.commit()
        s.refresh(run)

    handle = RunHandle(run.id)

    async def wrapper() -> None:
        done_ok = False
        current_project.set(project_id)
        current_run.set(run.id)
        try:
            result = await job(project_id, handle)
        except Exception as exc:
            log.exception("%s run failed", kind)

            def fail(r: Run) -> None:
                r.status, r.error, r.finished_at = "error", str(exc) or type(exc).__name__, _now()

            handle._update(fail)
        else:

            def finish(r: Run) -> None:
                r.status, r.phase, r.result, r.finished_at = "done", "done", result, _now()

            handle._update(finish)
            done_ok = True
        finally:
            _tasks.pop(key, None)
        # Chain the next stage only after this run is marked done and released.
        if done_ok and then:
            try:
                await then(project_id)
            except Exception:
                log.exception("follow-up after %s run failed", kind)

    _tasks[key] = asyncio.create_task(wrapper())
    return run


def mark_interrupted() -> None:
    """Runs left 'running' by a previous process can never finish."""
    with Session(engine) as s:
        for run in s.exec(select(Run).where(Run.status == "running")):
            run.status, run.error, run.finished_at = "error", "Interrupted by a server restart", _now()
            s.add(run)
        s.commit()
