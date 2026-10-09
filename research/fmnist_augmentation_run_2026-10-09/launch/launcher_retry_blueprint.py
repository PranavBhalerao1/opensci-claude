"""Session 2: restart the real backend and perform ONE user-equivalent retry of the blueprint
stage via the real route handler (rerun_blueprint == the UI's re-run button,
POST /api/projects/{id}/blueprint/run). Authorized by the operator after the autonomous
blueprint run failed with "Model returned no structured output (stop reason: max_tokens)".
Guarded by a marker file so the retry can never happen twice. Nothing in OpenScientist is patched.
"""
import asyncio, logging, sys
from datetime import datetime, timezone
from pathlib import Path

import uvicorn

HERE = Path(__file__).resolve().parent
OWNER = "56ec46c1-8aa1-467d-a4c9-7a76a7248153"
PID = (HERE / "project_id.txt").read_text().strip()
MARKER = HERE / "intervention_blueprint_retry.txt"

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
        log.info("blueprint retry already performed once (%s); serving only", MARKER.read_text().strip())
        return
    user = CurrentUser(id=OWNER, email="pranavrbhalerao@gmail.com")
    beta.require_allowance(beta.require_approved(user))
    MARKER.write_text(f"{datetime.now(timezone.utc).isoformat()} rerun_blueprint called once for {PID}\n")
    with Session(engine) as s:
        run = await projects.rerun_blueprint(PID, session=s, user=user)
        log.info("blueprint retry started: run %s", run.id)


async def main() -> None:
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info"))
    await asyncio.gather(server.serve(), act(server))


asyncio.run(main())
