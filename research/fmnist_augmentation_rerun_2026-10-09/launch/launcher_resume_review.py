"""Session 2: restart the real backend and perform ONE user-equivalent resume of the scientific
review via the real route handler (resume_review == the UI's Resume button,
POST /api/projects/{id}/review/resume). The operator's budget guard paused the backend (SIGINT)
when the 3rd review requested a 3rd repair round at $11.26; the user then authorized resuming to the
end. Guarded by a marker file so the resume can never happen twice. Nothing in OpenScientist is patched.
"""
import asyncio, logging, sys
from datetime import datetime, timezone
from pathlib import Path

import uvicorn

HERE = Path(__file__).resolve().parent
OWNER = "56ec46c1-8aa1-467d-a4c9-7a76a7248153"
PID = (HERE / "project_id.txt").read_text().strip()
MARKER = HERE / "intervention_review_resume.txt"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                    handlers=[logging.FileHandler(HERE / "backend.log"), logging.StreamHandler(sys.stdout)])
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
        log.info("review resume already performed once (%s); serving only", MARKER.read_text().strip())
        return
    user = CurrentUser(id=OWNER, email="pranavrbhalerao@gmail.com")
    beta.require_allowance(beta.require_approved(user))
    MARKER.write_text(f"{datetime.now(timezone.utc).isoformat()} resume_review called once for {PID}\n")
    with Session(engine) as s:
        out = await projects.resume_review(PID, session=s, user=user)
        log.info("review resumed: %s", out.get("resumed"))


async def main() -> None:
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info"))
    await asyncio.gather(server.serve(), act(server))


asyncio.run(main())
