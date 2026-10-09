"""Launch one autonomous OpenScientist project inside the real backend process.

Runs the real FastAPI app (uvicorn, same lifespan as `uvicorn app.main:app`) and, once it
is up, calls the real route handlers create_project and post_turn for the owner's user id
-- exactly what the frontend does (createProject({autonomous: true}) then the first chat
message). Only the HTTP bearer-token verification is skipped; the beta approval and
allowance checks are called explicitly. Autonomous mode then chains every stage itself.
Nothing in OpenScientist is patched.
"""
import asyncio, json, logging, sys
from pathlib import Path

import uvicorn

HERE = Path(__file__).resolve().parent
OWNER = "56ec46c1-8aa1-467d-a4c9-7a76a7248153"  # pranavrbhalerao@gmail.com (beta approved, $50 cap)
PID_FILE = HERE / "project_id.txt"
EVENTS = HERE / "clarify_events.jsonl"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                    handlers=[logging.FileHandler(HERE / "backend.log"), logging.StreamHandler(sys.stdout)])
log = logging.getLogger("launcher")

from app.main import app  # noqa: E402
from app import beta  # noqa: E402
from app.auth import CurrentUser  # noqa: E402
from app.db import engine  # noqa: E402
from app.routes import projects  # noqa: E402
from sqlmodel import Session  # noqa: E402


async def launch(server: uvicorn.Server) -> None:
    while not server.started:
        await asyncio.sleep(0.5)
    if PID_FILE.exists():
        log.info("project already launched: %s (not relaunching)", PID_FILE.read_text().strip())
        return
    user = CurrentUser(id=OWNER, email="pranavrbhalerao@gmail.com")
    beta.require_allowance(beta.require_approved(user))  # the route dependencies, called explicitly
    with Session(engine) as s:
        project = projects.create_project(projects.ProjectCreate(autonomous=True), session=s, user=user)
        pid = project.id
    PID_FILE.write_text(pid + "\n")
    log.info("created project %s (autonomous)", pid)
    prompt = (HERE / "research_prompt.md").read_text(encoding="utf-8")
    with Session(engine) as s:
        resp = projects.post_turn(pid, projects.TurnCreate(kind="text", content=prompt), session=s, user=user)
    with EVENTS.open("a", encoding="utf-8") as f:
        async for ev in resp.body_iterator:  # the SSE stream the UI would read: clarify runs here
            f.write(json.dumps(ev, default=str) + "\n")
            f.flush()
            log.info("clarify event: %s", ev.get("event"))
    log.info("clarify stream finished; autonomous pipeline continues server-side")


async def main() -> None:
    server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info"))
    await asyncio.gather(server.serve(), launch(server))


asyncio.run(main())
