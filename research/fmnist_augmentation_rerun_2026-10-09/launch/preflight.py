"""Read-only preflight for the rerun: no writes to the DB, no sandbox or GPU session created.

Checks: Supabase Postgres reachable and schema matches the app's models (the columns init_db()
would add are reported, not added); owner's beta approval/allowance; E2B API key valid (lists
running sandboxes); blueprint feasibility code present. Colab is checked separately with
`python -m app.execution.colab_runner check` (no session, no compute units).
"""
import asyncio, json
from sqlalchemy import inspect, text
from sqlmodel import SQLModel

from app.config import settings
from app.db import engine
from app import beta

OWNER = "56ec46c1-8aa1-467d-a4c9-7a76a7248153"
out = {}

url = engine.url
out["db"] = f"{url.get_backend_name()}://{url.host}:{url.port}/{url.database}"
with engine.connect() as c:
    out["db_version"] = c.execute(text("select version()")).scalar().split(",")[0]
insp = inspect(engine)
tables = set(insp.get_table_names())
missing_tables, missing_cols = [], []
for t in SQLModel.metadata.sorted_tables:
    if t.name not in tables:
        missing_tables.append(t.name)
        continue
    have = {c["name"] for c in insp.get_columns(t.name)}
    missing_cols += [f"{t.name}.{c.name}" for c in t.columns if c.name not in have]
out["model_tables"] = len(SQLModel.metadata.sorted_tables)
out["missing_tables"] = missing_tables
out["missing_columns"] = missing_cols

b = beta.get_beta_user(OWNER)
out["owner_beta"] = {"approved": bool(b and b.approved), "cap_usd": b.cap_usd if b else None,
                     "spent_usd": round(beta.get_user_spend(OWNER), 4),
                     "remaining_usd": round(beta.get_user_remaining(OWNER), 4)}

from e2b import AsyncSandbox
async def e2b():
    paginator = AsyncSandbox.list(api_key=settings.e2b_api_key)
    items = await paginator.next_items()
    return [{"id": s.sandbox_id, "template": s.template_id, "meta": s.metadata, "started": str(s.started_at)} for s in items]
out["e2b_template"] = settings.e2b_template
out["e2b_running_sandboxes"] = asyncio.run(e2b())

from app.agents import blueprint
from app import llm
out["blueprint_feasibility"] = {n: hasattr(blueprint, n) for n in
                                ("feasibility_errors", "review_feasibility", "lost_requirements", "_checked")}
out["blueprint_repair_rounds"] = blueprint.REPAIR_ROUNDS
out["llm_long_max_tokens"] = llm.LONG_MAX_TOKENS
out["models"] = {k: getattr(settings, k) for k in ("model_reasoning", "model_standard", "model_bulk", "model_judge")}
out["colab_credentials_file_set"] = bool(settings.colab_credentials_file)
print(json.dumps(out, indent=1, default=str))
