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
# Offline: no Bedrock or Tavily call can authenticate unless the live test is requested
# (the repo's .env holds real keys, and pydantic-settings would read them).
if os.environ.get("BEDROCK_INTEGRATION") != "1":
    os.environ["AWS_REGION"] = "us-east-1"
    os.environ["AWS_ACCESS_KEY_ID"] = "test-key-not-used"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test-key-not-used"
    os.environ.pop("AWS_SESSION_TOKEN", None)
    os.environ["TAVILY_API_KEY"] = ""
    os.environ.pop("BEDROCK_MODEL_ID", None)
    for _tier in ("MODEL_REASONING", "MODEL_STANDARD", "MODEL_BULK"):
        os.environ.pop(_tier, None)

from app.db import init_db  # noqa: E402 (must follow the os.environ overrides above)

init_db()
