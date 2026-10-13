"""Session 2: restart the real backend and perform ONE user-equivalent resume of execution via the
real route handler (resume_execution == the UI's Resume button, POST /api/projects/{id}/execution/resume)
with a default body (no budget or model-policy change).

Execution ended with T4.1 failed after its 2 allowed attempts, so the autonomous pipeline stopped
before the report. The user chose "Resume once": the orchestrator sets the failed task back to pending
(attempt count kept, so it gets exactly one more attempt at escalated effort); completed tasks are not
re-run, and no check is overridden. Guarded by a marker file so the resume can never happen twice.
Adapted from research/fmnist_augmentation_rerun_2026-10-09/launch/launcher_resume_review.py.
Nothing in OpenScientist is patched.
"""
import asyncio, logging, sys
from datetime import datetime, timezone
from pathlib import Path

import uvicorn

HERE = Path(__file__).resolve().parent
OWNER = "56ec46c1-8aa1-467d-a4c9-7a76a7248153"
PID = (HERE / "project_id.txt").read_text().strip()
MARKER = HERE / "intervention_execution_resume.txt"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                    handlers=[logging.FileHandler(HERE / "backend_session2.log"), logging.StreamHandler(sys.stdout)])
log = logging.getLogger("launcher")

from app.main import app  # noqa: E402
from app import beta  # noqa: E402
from app.auth import CurrentUser  # noqa: E402
from app.db import engine  # noqa: E402
from app.routes import projects  # noqa: E402
from sqlmodel import Session  # noqa: E402


async def act(server: uvicorn.Server) -> None:
    while not server.started:
        await asyncio.sleep(0.5)
    if MARKER.exists():
        log.info("execution resume already performed once (%s); serving only", MARKER.read_text().strip())
        return
    user = CurrentUser(id=OWNER, email="pranavrbhalerao@gmail.com")
    beta.require_allowance(beta.require_approved(user))  # the route's billable dependencies, called explicitly
    MARKER.write_text(f"{datetime.now(timezone.utc).isoformat()} resume_execution called once for {PID} "
                      f"(user chose 'Resume once' after T4.1 failed; default body, no settings changed)\n")
    with Session(engine) as s:
        out = await projects.resume_execution(PID, projects.ExecutionStart(), session=s, user=user)
        log.info("execution resume: %s", out)


async def main() -> None:
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info"))
    await asyncio.gather(server.serve(), act(server))


asyncio.run(main())
