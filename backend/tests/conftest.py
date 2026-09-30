"""Keeps the regression suite offline: it must never touch whatever Postgres
database happens to be configured in the repo's .env for the real dev server.
Must run before anything imports app.config/app.db, so the override happens at
collection time, before test modules are imported."""

import os
import tempfile
from pathlib import Path

_tmp_db = Path(tempfile.mkdtemp(prefix="openscientist-tests-")) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-used")

from app.db import init_db  # noqa: E402 (must follow the os.environ overrides above)

init_db()
