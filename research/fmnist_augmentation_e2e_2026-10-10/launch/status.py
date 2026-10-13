"""Read-only monitor: project stage, runs, task states and spend (LLM + GPU). No writes."""
import sys
from datetime import datetime, timezone
from pathlib import Path
from sqlmodel import Session, func, select
from app.db import GpuUsage, Project, Run, TaskState, Usage, engine

pid = sys.argv[1] if len(sys.argv) > 1 else (Path(__file__).parent / "project_id.txt").read_text().strip()
now = datetime.now(timezone.utc)
aware = lambda d: d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)
with Session(engine) as s:
    p = s.get(Project, pid)
    print(f"project {pid} stage={p.stage} title={p.title!r} review={'yes' if p.review else 'no'}  now={now:%H:%M:%S}Z")
    for r in s.exec(select(Run).where(Run.project_id == pid).order_by(Run.started_at)):
        end = aware(r.finished_at) or now
        print(f"  run {r.kind:10} {r.status:8} phase={r.phase[:40]:40} {r.started_at:%H:%M:%S}->"
              f"{r.finished_at.strftime('%H:%M:%S') if r.finished_at else '...':8} ({(end - aware(r.started_at)).total_seconds()/60:.1f}m)"
              + (f" ERR={r.error[:300]}" if r.error else ""))
        for line in (r.log or [])[-3:] if r.status == "running" else []:
            print(f"      log: {str(line)[:220]}")
    ts = list(s.exec(select(TaskState).where(TaskState.project_id == pid).order_by(TaskState.task_id)))
    if ts:
        print("  tasks: " + ", ".join(f"{t.task_id}={t.status}{'x'+str(t.attempts) if t.attempts > 1 else ''}" for t in ts))
        for t in ts:
            if t.status in ("failed", "running", "blocked") and t.note:
                print(f"    {t.task_id} [{t.status}] note: {t.note[:300]}")
    llm = s.exec(select(func.count(), func.coalesce(func.sum(Usage.cost), 0.0), func.coalesce(func.sum(Usage.input_tokens), 0),
                        func.coalesce(func.sum(Usage.output_tokens), 0)).where(Usage.project_id == pid)).one()
    gpu = s.exec(select(func.count(), func.coalesce(func.sum(GpuUsage.cost), 0.0), func.coalesce(func.sum(GpuUsage.seconds), 0.0))
                 .where(GpuUsage.project_id == pid)).one()
    print(f"  spend: LLM ${llm[1]:.2f} ({llm[0]} calls, {llm[2]:,} in / {llm[3]:,} out) | GPU ${gpu[1]:.2f} "
          f"({gpu[0]} rows, {gpu[2]/60:.1f} min) | TOTAL ${llm[1] + gpu[1]:.2f}")
