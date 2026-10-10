"""Operator budget guard (user rule: pause for approval if total spend is projected to exceed $15).
Read-only on the DB. If the 3rd review decides on another repair round, or total spend reaches
$14.50 while the loop is still active, sends SIGINT to the backend (a resumable pause: runs are
marked interrupted at the next startup and the review's Resume continues from the saved step).
Exits without acting if the review loop finishes."""
import os, signal, subprocess, time
from datetime import datetime, timezone
from sqlmodel import Session, func, select
from app.db import GpuUsage, Project, Run, Usage, engine

PID, CAP, LOG = "6d8c3c93c209", 14.50, os.path.join(os.path.dirname(__file__), "budget_guard.log")
def say(m):
    line = f"{datetime.now(timezone.utc):%H:%M:%S}Z {m}"; print(line, flush=True)
    open(LOG, "a").write(line + "\n")
say("armed")
while True:
    with Session(engine) as s:
        p = s.get(Project, PID)
        status = (p.review or {}).get("status")
        reviews = list(s.exec(select(Run).where(Run.project_id == PID, Run.kind == "review").order_by(Run.started_at)))
        spend = float(s.exec(select(func.coalesce(func.sum(Usage.cost), 0.0)).where(Usage.project_id == PID)).one()) + \
                float(s.exec(select(func.coalesce(func.sum(GpuUsage.cost), 0.0)).where(GpuUsage.project_id == PID)).one())
    if status in ("approved", "unresolved", "budget_exhausted", "stopped", "review_failed") or p.stage == "complete":
        say(f"review loop finished: status={status} stage={p.stage} spend=${spend:.2f}; guard exits without acting"); break
    third_wants_repair = False  # session 2: the user authorized resuming to the end; only the spend cap applies
    if third_wants_repair or spend >= CAP:
        why = "3rd review requested another repair round" if third_wants_repair else f"spend ${spend:.2f} >= ${CAP:.2f}"
        subprocess.run(["pkill", "-INT", "-f", "fmnist_augmentation_rerun_2026-10-09/launch/launcher_resume_review.py"])
        say(f"PAUSED (SIGINT to backend): {why}; spend=${spend:.2f} status={status}"); break
    time.sleep(10)
