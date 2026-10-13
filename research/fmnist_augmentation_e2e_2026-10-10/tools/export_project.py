"""Read-only export of this run's OpenScientist project from the database and workspace.

Adapted from research/fmnist_augmentation_rerun_2026-10-09/tools/export_project.py: the project id
comes from launch/project_id.txt, and it refuses to overwrite an earlier export. Nothing is written
to the DB, the workspace or backend/data; everything goes under this run's folder.

Usage: export_project.py [SUBDIR]. With SUBDIR (e.g. halt_snapshot) the export goes to that
subfolder of the run folder instead of the run folder itself, and the large training data and
checkpoints are listed (name, size) rather than copied.
"""
import json, shutil, sys
from pathlib import Path
from sqlalchemy import text
from app.db import engine
from app.execution.sandbox import WORKSPACES
from app.agents.plan import EXPORT_DIR

RUN = Path(__file__).resolve().parents[1]
PID = (RUN / "launch" / "project_id.txt").read_text().strip()
SNAPSHOT = len(sys.argv) > 1
OUT = RUN / sys.argv[1] if SNAPSHOT else RUN
OUT.mkdir(exist_ok=True)
db = OUT / "db_export"
assert not db.exists() and not (OUT / "workspace_copy").exists() and not (OUT / "plan_exports").exists(), \
    "refusing to overwrite an earlier export"
db.mkdir()


def dump(name, obj):
    (db / name).write_text(json.dumps(obj, indent=2, default=str, ensure_ascii=False), encoding="utf-8")


def rows(c, sql, **kw):
    r = c.execute(text(sql), {"p": PID, **kw})
    return [dict(m) for m in r.mappings()]


with engine.connect() as c:
    proj = rows(c, "select * from projects where id=:p")[0]
    dump("project.json", proj)
    for k in ("brief", "chosen_gap", "plan", "blueprint", "settings", "review"):
        dump(f"project_{k}.json", proj.get(k))
    dump("messages.json", rows(c, "select * from messages where project_id=:p order by created_at"))
    runs = rows(c, "select * from runs where project_id=:p order by started_at")
    dump("runs_all.json", runs)
    rd = db / "runs"; rd.mkdir()
    for i, r in enumerate(runs):
        (rd / f"{i:02d}_{r['kind']}_{r['status']}_{r['id']}.json").write_text(
            json.dumps(r, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    ts = rows(c, "select * from task_states where project_id=:p order by task_id")
    dump("task_states.json", ts)
    td = db / "task_traces"; td.mkdir()
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
    print("project", PID, "runs", len(runs), "tasks", len(ts), "usage rows", len(usage), "gpu rows", len(gpu),
          "papers", len(papers), "included", sum(1 for p in papers if p["included"]))

# Plan exports (vague_research_plan.json, master_plan.json, context.json, review/)
shutil.copytree(EXPORT_DIR / PID, OUT / "plan_exports", symlinks=True)
# Full copy of the project workspace (incl. .logs agent logs); the original stays in place.
BIG = ("data/FashionMNIST", "data/fashion_mnist", "data/checkpoints")
if SNAPSHOT:
    src = WORKSPACES / PID
    listing = [f"{p.relative_to(src)}\t{p.stat().st_size}" for b in BIG for p in sorted((src / b).rglob("*"))
               if p.is_file()]
    (OUT / "large_files_not_copied.tsv").write_text("path\tbytes\n" + "\n".join(listing) + "\n", encoding="utf-8")
    shutil.copytree(src, OUT / "workspace_copy", symlinks=True,
                    ignore=lambda d, names: [n for n in names if str((Path(d) / n).relative_to(src)) in BIG])
else:
    shutil.copytree(WORKSPACES / PID, OUT / "workspace_copy", symlinks=True)
print("plan exports source:", EXPORT_DIR / PID)
print("workspace source:", WORKSPACES / PID)
