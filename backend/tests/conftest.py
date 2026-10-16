"""Keeps the regression suite offline: it must never touch whatever Postgres
database happens to be configured in the repo's .env for the real dev server.
Must run before anything imports app.config/app.db, so the override happens at
collection time, before test modules are imported."""

import os
import tempfile
from pathlib import Path

_tmp_db = Path(tempfile.mkdtemp(prefix="openscientist-tests-")) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"
# Offline: no E2B sandbox can be created unless the real integration test is requested.
if os.environ.get("E2B_INTEGRATION") != "1":
    os.environ["E2B_API_KEY"] = ""
# Same for Colab: without credentials the runner is unconfigured, so no GPU session or startup
# reaper can reach Google whatever the repo's .env holds (tests fake the CLI where they need one).
if os.environ.get("COLAB_INTEGRATION") != "1":
    os.environ["COLAB_CREDENTIALS_FILE"] = ""
# Offline: no Bedrock or Tavily call can authenticate unless the live test is requested
# (the repo's .env holds real keys, and pydantic-settings would read them).
if os.environ.get("BEDROCK_INTEGRATION") != "1":
    os.environ["AWS_REGION"] = "us-east-1"
    os.environ["AWS_ACCESS_KEY_ID"] = "test-key-not-used"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test-key-not-used"
    os.environ.pop("AWS_SESSION_TOKEN", None)
    os.environ["TAVILY_API_KEY"] = ""
    os.environ.pop("BEDROCK_MODEL_ID", None)
    for _tier in ("MODEL_REASONING", "MODEL_STANDARD", "MODEL_BULK", "MODEL_JUDGE"):
        os.environ.pop(_tier, None)

from app.db import init_db  # noqa: E402 (must follow the os.environ overrides above)

init_db()


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _task_retries(monkeypatch):
    """Offline: a failed task's retry advice comes from a stub, not a model. Most scenarios are
    about one retry, so tasks get the blueprint's own retry count unless a test raises it."""
    from app.execution import orchestrator

    async def advise(task, problems, report, events, history, policy):
        return orchestrator.Advice(diagnosis="stub diagnosis", fix=["stub fix"])

    monkeypatch.setattr(orchestrator, "_advise", advise)
    monkeypatch.setattr(orchestrator.settings, "task_max_attempts", 2)
    monkeypatch.setattr(orchestrator, "FENCE_RETRY", (0, 0))
