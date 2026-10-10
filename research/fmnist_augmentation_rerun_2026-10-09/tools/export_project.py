"""Read-only export of OpenScientist project 6d8c3c93c209 from the database and workspace."""
import json, shutil, sys
from pathlib import Path
from sqlalchemy import text
from app.db import engine
from app.execution.sandbox import WORKSPACES
from app.agents.plan import EXPORT_DIR

PID = "6d8c3c93c209"
OUT = Path(__file__).resolve().parents[1]
db = OUT / "db_export"; db.mkdir(exist_ok=True)

def dump(name, obj):
    (db / name).write_text(json.dumps(obj, indent=2, default=str, ensure_ascii=False), encoding="utf-8")

def rows(c, sql, **kw):
    r = c.execute(text(sql), {"p": PID, **kw})
    return [dict(m) for m in r.mappings()]

with engine.connect() as c:
    proj = rows(c, "select * from projects where id=:p")[0]
    dump("project.json", proj)
    for k in ("brief", "chosen_gap", "plan", "blueprint", "settings"):
        dump(f"project_{k}.json", proj.get(k))
    dump("messages.json", rows(c, "select * from messages where project_id=:p order by created_at"))
    runs = rows(c, "select * from runs where project_id=:p order by started_at")
    dump("runs_all.json", runs)
    rd = db / "runs"; rd.mkdir(exist_ok=True)
    for i, r in enumerate(runs):
        (rd / f"{i:02d}_{r['kind']}_{r['status']}_{r['id']}.json").write_text(
            json.dumps(r, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    ts = rows(c, "select * from task_states where project_id=:p order by task_id")
    dump("task_states.json", ts)
    td = db / "task_traces"; td.mkdir(exist_ok=True)
    for t in ts:
        (td / f"{t['task_id']}_{t['status']}.json").write_text(
            json.dumps(t, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    usage = rows(c, "select * from usage where project_id=:p order by created_at")
    dump("usage.json", usage)
    gpu = rows(c, "select * from gpu_usage where project_id=:p order by created_at")
    dump("gpu_usage.json", gpu)
    papers = rows(c, """select pp.origin, pp.score, pp.relevance, pp.reason, pp.included, p.*
                        from project_papers pp join papers p on p.id = pp.paper_id
                        where pp.project_id=:p order by pp.included desc, pp.relevance desc nulls last""")
    dump("literature_papers.json", papers)
    print("runs", len(runs), "tasks", len(ts), "usage rows", len(usage), "gpu rows", len(gpu),
          "papers", len(papers), "included", sum(1 for p in papers if p["included"]))

# Plan exports (vague_research_plan.json, master_plan.json, context.json)
shutil.copytree(EXPORT_DIR / PID, OUT / "plan_exports", dirs_exist_ok=True)
# Full copy of the project workspace (incl. .logs agent logs); the original stays in place.
shutil.copytree(WORKSPACES / PID, OUT / "workspace_copy", dirs_exist_ok=True, symlinks=True)
print("workspace source:", WORKSPACES / PID)
