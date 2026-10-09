"""Build (and optionally run) one independent scientific review for an existing project.

The configured database is only read: the project's rows (project, runs, task states, its
included papers) are copied with plain SELECTs into a throwaway SQLite snapshot, and the review
runs against that snapshot and the project's real workspace (read-only). Nothing in the source
database or the workspace changes, whatever its schema version.

Default (offline): runs the integrity gates and builds the judge's evidence bundle, prints what
the judge would see (sources, sizes, figures, omissions, integrity facts, a cost estimate) and
writes bundle.md. Any model call fails loudly.

--call: makes the real review (one judge call, plus the verification call when FATAL/MAJOR
issues are claimed, plus at most one retry each) after checking a pessimistic cost estimate
against --max-usd, and writes mistakes.json. Token usage is recorded in the snapshot only and
printed.

    cd backend && PYTHONPATH=. python scripts/judge_dry_run.py <project_id> [--from-export] [--call]
        [--max-usd 2] [--out DIR]

--from-export rebuilds a finished project whose database rows are gone from its plan exports
(backend/data/projects/<id>/) and its workspace.
"""

import argparse
import asyncio
import json
import sys
import tempfile
import uuid
from pathlib import Path

from app import config

SOURCE_URL = config.settings.database_url
SNAPSHOT = Path(tempfile.mkdtemp(prefix="judge-dry-run-")) / "snapshot.db"
config.settings.database_url = f"sqlite:///{SNAPSHOT}"  # before app.db creates its engine

from sqlalchemy import create_engine, func, text  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app import integrity, llm  # noqa: E402
from app.agents import judge  # noqa: E402
from app.config import SONNET_4_6, settings  # noqa: E402
from app.db import Paper, Project, ProjectPaper, Run, TaskState, Usage, _engine_url, engine, init_db  # noqa: E402

PROJECT_COLUMNS = ("id", "title", "stage", "autonomous", "settings", "brief", "chosen_gap", "plan", "blueprint",
                   "created_at", "updated_at")


class _NoLLM:
    def __getattr__(self, name):
        raise RuntimeError("model call attempted in offline mode (use --call)")


class _Handle:
    """Prints progress instead of writing a Run row."""

    def phase(self, phase: str, text: str | None = None) -> None:
        print(f"[{phase}] {text or ''}")

    def note(self, text: str) -> None:
        print(f"  · {text}")

    def counts(self, **counts) -> None:
        pass


def _rows(conn, sql: str, **params) -> list[dict]:
    return [dict(r._mapping) for r in conn.execute(text(sql), params)]


def snapshot(pid: str) -> None:
    """Copy one project's rows from the source database into the SQLite snapshot (read-only)."""
    src = create_engine(_engine_url(SOURCE_URL))
    with src.connect() as conn:
        project = _rows(conn, f"SELECT {', '.join(PROJECT_COLUMNS)} FROM projects WHERE id = :pid", pid=pid)
        if not project:
            sys.exit(f"No project {pid}")
        runs = _rows(conn, "SELECT * FROM runs WHERE project_id = :pid", pid=pid)
        states = _rows(conn, "SELECT * FROM task_states WHERE project_id = :pid", pid=pid)
        links = _rows(conn, "SELECT * FROM project_papers WHERE project_id = :pid AND included", pid=pid)
        papers = _rows(conn, "SELECT p.* FROM papers p JOIN project_papers pp ON pp.paper_id = p.id "
                             "WHERE pp.project_id = :pid AND pp.included", pid=pid)
    src.dispose()
    init_db()
    with Session(engine) as s:
        s.add(Project(**project[0], user_id=None))  # no owner: no beta cap in the snapshot
        for model, rows in ((Run, runs), (TaskState, states), (Paper, papers), (ProjectPaper, links)):
            fields = set(model.model_fields)
            for r in rows:
                s.add(model(**{k: v for k, v in r.items() if k in fields and k != "user_id"}))
        s.commit()
    print(f"Snapshot of {pid}: {len(runs)} runs, {len(states)} task states, {len(papers)} papers → {SNAPSHOT}")


def snapshot_from_export(pid: str) -> None:
    """Rebuild a snapshot from the plan exports (backend/data/projects/<id>/) and the workspace,
    for finished projects whose database rows no longer exist. Task statuses are inferred from
    which declared outputs exist, and the report run's start from the paper's file times."""
    from datetime import datetime, timezone

    from app.agents.plan import EXPORT_DIR
    from app.execution.sandbox import sandbox_for
    from app.sources.common import norm_title

    exp = EXPORT_DIR / pid
    try:
        ctx = json.loads((exp / "context.json").read_text(encoding="utf-8"))
        plan = json.loads((exp / "vague_research_plan.json").read_text(encoding="utf-8"))
        mp = json.loads((exp / "master_plan.json").read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        sys.exit(f"No exports for {pid}: {exc}")
    root = sandbox_for(pid).root
    paper = root / "paper"
    if not (paper / "paper.tex").is_file():
        sys.exit(f"No manuscript in {root}")
    times = [p.stat().st_mtime for p in (paper / "paper.tex", paper / "paper.pdf") if p.is_file()]
    started = datetime.fromtimestamp(min(times) - 60, timezone.utc)
    init_db()
    with Session(engine) as s:
        meta = ctx["project"]
        s.add(Project(id=pid, title=meta["title"], stage="complete", autonomous=meta.get("autonomous", False),
                      settings=meta.get("settings") or {}, brief=ctx["brief"], chosen_gap=ctx["gaps"]["chosen"],
                      plan={**plan, "run_id": "export-plan"}, blueprint={"run_id": "export-bp"}))
        s.add(Run(id="export-bp", project_id=pid, kind="blueprint", status="done", result={
            "master_plan": {k: v for k, v in mp.items() if k not in ("schema", "warnings", "budget")},
            "warnings": mp.get("warnings", []), "budget": mp.get("budget", {})}))
        s.add(Run(project_id=pid, kind="report", status="done", started_at=started, finished_at=started, result={}))
        for t in mp["tasks"]:
            done = all((root / o["path"]).exists() for o in t["outputs"])
            s.add(TaskState(project_id=pid, blueprint_run_id="export-bp", task_id=t["id"], agent=t["agent"],
                            status="done" if done else "failed", attempts=1))
        for p in ctx["literature"]["papers"]:
            s.add(Paper(id=p["id"], title=p["title"], norm_title=norm_title(p["title"]), year=p.get("year"),
                        venue=p.get("venue"), authors=p.get("authors") or [], doi=p.get("doi"), url=p.get("url"),
                        pdf_url=p.get("pdf_url"), citation_count=p.get("citation_count") or 0, notes=p.get("notes")))
            s.add(ProjectPaper(project_id=pid, paper_id=p["id"], relevance=p.get("relevance"), included=True))
        s.commit()
    print(f"Snapshot of {pid} rebuilt from exports (task statuses inferred from outputs present) → {SNAPSHOT}")


def estimate_usd(bundle: judge.Bundle) -> tuple[float, float]:
    """(expected, worst case): judge + verify with ~12k output tokens each; worst case adds a
    retry of each and spends the full output budget every time."""
    chars = sum(len(b["text"]) for b in bundle.blocks if b["type"] == "text")
    tokens_in = chars / 3.2 + 1700 * len(bundle.visuals) + 4000
    p_in, _, p_out = settings.model_prices.get(settings.model_judge, settings.model_prices[SONNET_4_6])
    return 2 * (tokens_in * p_in + 12_000 * p_out) / 1e6, 4 * (tokens_in * p_in + llm.MAX_TOKENS * p_out) / 1e6


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("project_id")
    ap.add_argument("--call", action="store_true", help="make the real (billed) review")
    ap.add_argument("--max-usd", type=float, default=2.0)
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--from-export", action="store_true",
                    help="rebuild the project from backend/data/projects/<id>/ exports instead of the database")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252
    pid = args.project_id
    out = args.out or Path(f"judge_dry_run_{pid}")
    out.mkdir(parents=True, exist_ok=True)
    if not args.call:
        llm.client = _NoLLM()
    snapshot_from_export(pid) if args.from_export else snapshot(pid)

    gates = integrity.check(pid)
    print(f"Integrity: {'passed' if gates['passed'] else 'FAILED'}")
    for g in gates["hard_failures"]:
        print(f"  HARD {g['gate']} {g['severity']}: {g['title']} — {g['detail'][:160]}")
    for f in gates["facts"]:
        print(f"  fact: {f[:200]}")
    bundle = judge.build_bundle(pid, gates)
    (out / "bundle.md").write_text("".join(bundle.markdown), encoding="utf-8")
    print(f"\nBundle sha256 {bundle.sha256[:16]}…  sources: {len(bundle.sources)}  visuals: {len(bundle.visuals)}")
    for s in bundle.sources.values():
        print(f"  {s.id:<60} {len(s.text):>8,} chars{' (truncated)' if s.truncated else ''}")
    for v in bundle.visuals:
        print(f"  {v['id']:<60} {v['bytes']:>8,} bytes {v['media_type']}")
    for o in bundle.omitted:
        print(f"  omitted {o['path']}: {o['reason']}")
    if bundle.numeric:
        print(f"Numeric cross-check: {bundle.numeric['unmatched_total']} of {bundle.numeric['checked']} unmatched")
    expected, worst = estimate_usd(bundle)
    print(f"\nReview cost estimate: ~${expected:.2f} expected, ${worst:.2f} worst case; bundle.md written to {out}")
    if not args.call:
        return
    if not gates["passed"]:
        sys.exit("Integrity gates failed: the review would not call the judge.")
    if worst > args.max_usd:
        sys.exit(f"Refusing: worst case ${worst:.2f} exceeds --max-usd {args.max_usd:.2f}")

    run_id = f"judge-dry-run-{uuid.uuid4().hex[:8]}"
    llm.current_project.set(pid)
    llm.current_run.set(run_id)
    real_parse = judge.parse

    async def capped_parse(**kw):  # a hard cap at run time, not just the up-front estimate
        with Session(engine) as s:
            so_far = float(s.exec(select(func.coalesce(func.sum(Usage.cost), 0.0)).where(Usage.run_id == run_id)).one())
        if so_far + estimate_usd(bundle)[1] / 4 > args.max_usd:
            raise RuntimeError(f"Stopping: another call could exceed --max-usd (spent ${so_far:.4f})")
        return await real_parse(**kw)

    judge.parse = capped_parse
    try:
        mistakes, _ = asyncio.run(judge.review(pid, _Handle(), iteration=0, verify=not args.no_verify))
    finally:
        with Session(engine) as s:
            spent = float(s.exec(select(func.coalesce(func.sum(Usage.cost), 0.0)).where(Usage.run_id == run_id)).one())
            calls = len(s.exec(select(Usage.id).where(Usage.run_id == run_id)).all())
        print(f"\nModel calls: {calls}, recorded cost ${spent:.4f}")
    (out / "mistakes.json").write_text(json.dumps(mistakes, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"Verdict: {mistakes.get('verdict')}  grammar mode: {mistakes.get('grammar_mode')}  "
          f"verification: {mistakes.get('verification')}")
    for i in mistakes.get("issues", []):
        flag = "BLOCKING" if i.get("blocking") else ("open concern" if i.get("open_concern") else "")
        print(f"  {i['id']} {i['severity']:<5} {i['category']:<20} {i['grounding']:<20} "
              f"{i.get('verification', ''):<10} {flag:<12} {i['title'][:80]}")


if __name__ == "__main__":
    main()
