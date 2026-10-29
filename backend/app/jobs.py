"""In-process background jobs for long stages. Progress lives in the Run table so
the UI can poll it and a page refresh never loses state."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from sqlalchemy import update as sa_update
from sqlmodel import Session, select

from .beta import check_project_allowance
from .db import Run, engine
from .llm import current_project, current_run, safe_error

log = logging.getLogger("openscientist.jobs")
_tasks: dict[str, asyncio.Task] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RunHandle:
    """Write-through progress reporting for one Run row.

    The handle is the only writer of its run's `log` and `counts` while the job runs, so it keeps
    its own copy of both (read once) and progress updates are plain UPDATEs: reporting progress
    never re-reads the row (its `log` and `result` JSON) from the database."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self._log: list | None = None
        self._counts: dict | None = None

    def _load(self) -> None:
        if self._log is None:
            with Session(engine) as s:
                log, counts = s.exec(select(Run.log, Run.counts).where(Run.id == self.run_id)).one()
            self._log, self._counts = list(log or []), dict(counts or {})

    def _write(self, **values) -> None:
        with Session(engine) as s:
            s.exec(sa_update(Run).where(Run.id == self.run_id).values(**values))
            s.commit()

    def _update(self, fn: Callable[[Run], None]) -> None:
        """Read-modify-write of the whole row, for the once-per-run transitions (finish, fail)."""
        with Session(engine) as s:
            run = s.get(Run, self.run_id)
            fn(run)
            s.add(run)
            s.commit()
            self._log, self._counts = list(run.log or []), dict(run.counts or {})

    def phase(self, phase: str, text: str | None = None) -> None:
        if text:
            self._load()
            self._log = [*self._log, {"t": _now().isoformat(), "text": text}]
            self._write(phase=phase, log=self._log)
        else:
            self._write(phase=phase)

    def note(self, text: str) -> None:
        self._load()
        self._log = [*self._log, {"t": _now().isoformat(), "text": text}]
        self._write(log=self._log)

    def counts(self, **counts: int) -> None:
        self._load()
        merged = {**self._counts, **counts}
        if merged != self._counts:
            self._counts = merged
            self._write(counts=merged)


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
            check_project_allowance(project_id)  # private-beta cap; also covers chained stages
            result = await job(project_id, handle)
        except asyncio.CancelledError:

            def cancelled(r: Run) -> None:
                r.status, r.error, r.finished_at = "error", "Cancelled", _now()

            handle._update(cancelled)
        except Exception as exc:
            log.exception("%s run failed", kind)

            def fail(r: Run) -> None:
                r.status, r.error, r.finished_at = "error", safe_error(exc), _now()

            handle._update(fail)
        else:

            def finish(r: Run) -> None:
                r.status, r.phase, r.result, r.finished_at = "done", "done", result, _now()

            handle._update(finish)
            done_ok = True
        finally:
            _tasks.pop(key, None)
        # What the job wrote on the server (e.g. the review record) goes to the cloud sandbox,
        # whose copy survives restarts.
        from .execution.sandbox import sandbox_for  # execution imports this module

        await sandbox_for(project_id).save()
        # Chain the next stage only after this run is marked done and released.
        if done_ok and then:
            try:
                await then(project_id)
            except Exception as exc:
                log.exception("follow-up after %s run failed", kind)
                # The run itself succeeded (status stays "done" so its result remains usable),
                # but record why the next stage never started instead of stalling silently.
                msg = f"Next stage failed to start: {type(exc).__name__}: {exc}"

                def follow_up_failed(r: Run) -> None:
                    r.error = msg
                    r.log = [*r.log, {"t": _now().isoformat(), "text": msg}]

                handle._update(follow_up_failed)

    _tasks[key] = asyncio.create_task(wrapper())
    return run


def cancel(project_id: str, kind: str) -> bool:
    """Stop a running stage job. The wrapper marks its Run as an error ("Cancelled")."""
    task = _tasks.get(f"{project_id}:{kind}")
    if not task or task.done():
        return False
    task.cancel()
    return True


INTERRUPTED = "Interrupted by a server restart"


def mark_interrupted() -> list[tuple[str, str]]:
    """Runs left 'running' by a previous process can never finish. Returns their
    (project_id, kind), so autonomous work can be picked up again."""
    found = []
    with Session(engine) as s:
        for run in s.exec(select(Run).where(Run.status == "running")):
            run.status, run.error, run.finished_at = "error", INTERRUPTED, _now()
            s.add(run)
            found.append((run.project_id, run.kind))
        s.commit()
    return found
