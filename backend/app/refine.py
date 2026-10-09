"""Scientific review and refinement: the loop around the existing pipeline.

report → [review] independent judge (agents/judge.py) → decide:
  approved | unresolved | budget exhausted | review failed  → finish (stage "complete")
  integrity gates failed → deterministic repair (no judge or planner call)
  blocking issues        → [repair] the Planning Agent chooses root-cause fixes; code applies
                           them: plan revision, blueprint delta with carry-over of unchanged
                           finished tasks, task re-runs with protocol changes (dependents
                           follow), manuscript directives
→ execution (only what was invalidated) → report → review (a fresh judge) → …

State lives in Project.review (compact) plus Run rows and files under
backend/data/projects/<id>/review/. Every step is a Run; `step` says which one the loop is
on, so a crash, restart or failure is resumed from there. Model outputs are saved before any
side effect, and side effects are idempotent, so resuming never pays twice.
"""

import asyncio
import copy
import hashlib
import json
import logging
import re
from datetime import datetime, timezone

import anthropic
from pydantic import ValidationError
from sqlalchemy import func
from sqlmodel import Session, select

from . import beta, jobs, pipeline
from .agents import blueprint as blueprint_agent
from .agents import judge
from .agents import plan as plan_agent
from .config import settings
from .db import GpuUsage, Project, Run, TaskState, Usage, engine
from .execution import orchestrator
from .execution.sandbox import gpu_runner
from .integrity import _under
from .jobs import RunHandle
from .llm import TRANSIENT_ERRORS

log = logging.getLogger("openscientist.refine")

ACTIVE = ("reviewing", "repairing", "attention")
FINAL = ("approved", "unresolved", "budget_exhausted", "stopped")
REPAIRS = ("repair", "repair_gates")
STAGES = ("plan", "blueprint", "execution", "report")
ORIGIN_STAGE = {"plan": "plan", "blueprint": "blueprint", "execution": "execution", "analysis": "execution",
                "report": "report", "literature": "report"}
UNFINISHED = ("failed", "blocked", "human", "pending", "cancelled", "running")
WATCH_INTERVAL = 10.0  # seconds between checks of a live repair execution
STALL_SECONDS = 120.0  # a finished step with nothing started after it for this long has stalled
_watchers: dict[str, asyncio.Task] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── Config and state ───────────────────────────────────────────────────────


def config(project: Project) -> dict:
    cfg = (project.settings or {}).get("refinement") or {}
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "max_rounds": int(cfg.get("max_rounds", settings.refinement_max_rounds)),
        "max_usd": float(cfg.get("max_usd", settings.refinement_max_usd)),
        "verify": bool(cfg.get("verify", True)),
    }


def default_settings() -> dict:
    """Stamped on new projects (routes.create_project)."""
    return {"enabled": settings.refinement_default}


def state(project_id: str) -> dict:
    with Session(engine) as s:
        project = s.get(Project, project_id)
        return copy.deepcopy(project.review or {}) if project else {}


def update(project_id: str, **fields) -> dict:
    """Merge fields into Project.review (copied and reassigned: JSON columns do not track
    in-place mutation)."""
    with Session(engine) as s:
        project = s.get(Project, project_id)
        review = {**copy.deepcopy(project.review or {}), **fields}
        project.review = review
        project.updated_at = _now()
        s.add(project)
        s.commit()
        return copy.deepcopy(review)


def _update_iteration(project_id: str, n: int, **fields) -> None:
    st = state(project_id)
    iterations = st.get("iterations", [])
    for it in iterations:
        if it["n"] == n:
            it.update(fields)
    update(project_id, iterations=iterations)


def enabled(project_id: str) -> bool:
    with Session(engine) as s:
        project = s.get(Project, project_id)
        return bool(project) and config(project)["enabled"]


def repairing(project_id: str) -> bool:
    return state(project_id).get("status") in ("repairing", "attention")


def view(project_id: str) -> dict:
    """The review state with an effective status: a step whose Run failed, was cancelled or
    was interrupted by a restart shows as review_failed / attention, ready to resume."""
    st = state(project_id)
    status, step = st.get("status"), st.get("step")
    if status in ("reviewing", "repairing") and step:
        kind = {"review": "review", "repair": "repair", "execute": "execute", "report": "report"}[step]
        if not jobs.is_running(project_id, kind):
            with Session(engine) as s:
                run = s.exec(select(Run).where(Run.project_id == project_id, Run.kind == kind)
                             .order_by(Run.started_at.desc())).first()
            if run and run.status == "error":
                st["status"] = "review_failed" if step == "review" else "attention"
                st["attention"] = f"{kind} run failed: {run.error}"
            elif run and run.status == "done" and run.error:
                st["status"], st["attention"] = "attention", run.error
            elif run and run.status == "done" and run.finished_at and not any(
                    jobs.is_running(project_id, k) for k in ("review", "repair", "execute", "report")) and \
                    (_now() - _aware(run.finished_at)).total_seconds() > STALL_SECONDS:
                st["status"] = "attention"  # e.g. the server stopped between two steps
                st["attention"] = f"The review loop stopped after the {kind} step; resume to continue."
    st["spent_usd"] = round(spent(project_id, st["started_at"]), 4) if st.get("started_at") else 0.0
    st["live"] = {k: jobs.is_running(project_id, k) for k in ("review", "repair", "execute", "report")}
    return st


def spent(project_id: str, since: str) -> float:
    """LLM + GPU spend of the project since `since` (ISO time): the refinement's own spend."""
    t = datetime.fromisoformat(since)
    with Session(engine) as s:
        llm_cost = s.exec(select(func.coalesce(func.sum(Usage.cost), 0.0))
                          .where(Usage.project_id == project_id, Usage.created_at >= t)).one()
        gpu_cost = s.exec(select(func.coalesce(func.sum(GpuUsage.cost), 0.0))
                          .where(GpuUsage.project_id == project_id, GpuUsage.created_at >= t)).one()
    return float(llm_cost) + float(gpu_cost)


def _run_cost(run_id: str | None) -> float:
    if not run_id:
        return 0.0
    with Session(engine) as s:
        return float(s.exec(select(func.coalesce(func.sum(Usage.cost), 0.0)).where(Usage.run_id == run_id)).one())


def begin_session(project_id: str) -> dict:
    prev = state(project_id)
    _restore_budget(project_id, prev)  # a session ended early must not leave the execution budgets capped
    with Session(engine) as s:
        project = s.get(Project, project_id)
        cfg = config(project)
        plan = project.plan
    n = prev.get("iteration", 0)
    return update(
        project_id,
        enabled=True, status="reviewing", step="review", stale=False, attention=None,
        session=prev.get("session", 0) + 1, iteration=n, session_first_iteration=n + 1,
        max_rounds=cfg["max_rounds"], max_usd=cfg["max_usd"], verify=cfg["verify"],
        started_at=_now().isoformat(), budget_override=None,
        preregistration=prev.get("preregistration") or judge.preregistration_of(plan),
        tracks=prev.get("tracks", {}), iterations=prev.get("iterations", []),
        directives=prev.get("directives", {}), gate_directives=[], outcome=None,
    )


# ── Pipeline hooks ─────────────────────────────────────────────────────────


def will_review(project_id: str) -> bool:
    """Whether after_report(project_id) will hand this report to the independent-review loop,
    without after_report's side effects. report.py uses this to decide whether IT needs to run
    its own fallback claims audit: a report the review loop is about to check should not also
    pay for a duplicate one, but a report whose review is finished, disabled or never started
    must never go unchecked. Keep this in sync with after_report's branches below."""
    st = state(project_id)
    status = st.get("status")
    if status in FINAL:
        return False
    if status in ACTIVE or status == "review_failed":
        return True
    return enabled(project_id)


def after_report(project_id: str) -> bool:
    """Called when a report finishes. Returns True if refinement took over."""
    st = state(project_id)
    status = st.get("status")
    if status in FINAL:
        update(project_id, stale=True)  # the paper changed after the review finished
        return False
    if status in ACTIVE or status == "review_failed":
        start_review(project_id)
        return True
    if enabled(project_id):
        begin_session(project_id)
        start_review(project_id)
        return True
    return False


def _finished(project_id: str) -> tuple[bool, str, list[str]]:
    with Session(engine) as s:
        project = s.get(Project, project_id)
        states = list(s.exec(select(TaskState).where(
            TaskState.blueprint_run_id == (project.blueprint or {}).get("run_id"))))
        stage = project.stage
    unfinished = [f"{st.task_id} [{st.status}]" for st in states if st.status not in ("done", "skipped")]
    return bool(states) and not unfinished, stage, unfinished


def after_execution(project_id: str) -> bool:
    """Called when an execution run returns. Returns True if refinement handled it."""
    st = state(project_id)
    if st.get("step") != "execute":
        return False
    if st.get("status") in FINAL:  # e.g. the watcher stopped the run at the budget
        pipeline._set_stage(project_id, "complete")
        update(project_id, step=None)
        return True
    if st.get("status") not in ("repairing", "attention"):
        return False
    finished, stage, unfinished = _finished(project_id)
    if finished and stage == "executed":
        start_report_step(project_id)
    else:
        update(project_id, status="attention",
               attention="Repair execution needs attention: " + (", ".join(unfinished[:8]) or f"stage {stage}"))
    return True


# ── Review ─────────────────────────────────────────────────────────────────


def _over_budget(project_id: str, st: dict) -> bool:
    return spent(project_id, st["started_at"]) >= st["max_usd"]


def start_review(project_id: str) -> Run | None:
    st = state(project_id)
    if not st.get("started_at"):
        st = begin_session(project_id)
    if beta.project_allowance(project_id) <= 0:
        finalize(project_id, "budget_exhausted", beta.LIMIT_MESSAGE)
        return None
    if _over_budget(project_id, st):
        finalize(project_id, "budget_exhausted", f"The refinement budget (${st['max_usd']:.2f}) is used up.")
        return None
    update(project_id, status="reviewing", step="review", attention=None)
    pipeline._set_stage(project_id, "reviewing")
    return jobs.start(project_id, "review", _review_job, then=_after_review)


def _previous_mistakes(project_id: str, n: int) -> dict | None:
    path = judge.review_dir(project_id, n) / "mistakes.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")) if n > 0 and path.is_file() else None
    except (OSError, json.JSONDecodeError):
        return None


async def _review_job(project_id: str, h: RunHandle) -> dict:
    st = state(project_id)
    n = st.get("iteration", 0) + 1
    update(project_id, gate_directives=[])
    previous = _previous_mistakes(project_id, n - 1)
    bundle = None
    try:
        mistakes, bundle = await judge.review(project_id, h, n, previous=previous, verify=st.get("verify", True))
    except judge.ReviewFailed as exc:
        mistakes = _failed(project_id, n, str(exc))
    except beta.BetaLimitReached:
        mistakes = {**_failed(project_id, n, beta.LIMIT_MESSAGE), "budget_limit": True}
    except TRANSIENT_ERRORS as exc:
        mistakes = _failed(project_id, n, f"Bedrock unavailable: {type(exc).__name__}: {exc}")
    except anthropic.APIError as exc:
        # Any other Bedrock/API error (e.g. a permanent 4xx) that judge.review() did not already
        # turn into ReviewFailed: treat it the same way rather than letting it crash the job.
        # An uncaught exception here would only mark the Run as errored, leaving
        # Project.review.status stuck at "reviewing" forever for anything that reads it
        # directly (e.g. the guard that blocks other project actions during an active review).
        mistakes = _failed(project_id, n, f"Bedrock error: {type(exc).__name__}: {exc}")
    tracks = st.get("tracks", {})
    if mistakes.get("valid") and mistakes.get("judged"):
        last = next((it for it in reversed(st.get("iterations", [])) if it.get("changed")), None)
        tracks = track_issues(tracks, mistakes["issues"], n, set((last or {}).get("changed", [])))
    st = {**st, "tracks": tracks}
    decision, reason = decide(st, mistakes, spent(project_id, st["started_at"]))
    mistakes.update(decision=decision, decision_reason=reason, cost_usd=round(_run_cost(h.run_id), 4))
    judge.write_iteration_files(project_id, n, mistakes, bundle)
    blocking = [i for i in mistakes.get("issues", []) if i.get("blocking")]
    record = {
        "n": n, "session": st.get("session", 1), "review_run_id": h.run_id, "verdict": mistakes.get("verdict"),
        "judged": mistakes.get("judged", False), "decision": decision, "reason": reason,
        "blocking": {sev: sum(1 for i in blocking if i["severity"] == sev) for sev in ("FATAL", "MAJOR")},
        "open_concerns": sum(1 for i in mistakes.get("issues", []) if i.get("open_concern")),
        "issues": [{k: i.get(k) for k in ("id", "track_id", "severity", "category", "title", "blocking",
                                          "open_concern", "verification", "grounding", "tracking")}
                   for i in mistakes.get("issues", [])][:30],
        "cost_usd": mistakes["cost_usd"],
    }
    update(project_id, iteration=n, tracks=tracks, iterations=[*st.get("iterations", []), record])
    write_history(project_id)
    h.counts(fatal=record["blocking"]["FATAL"], major=record["blocking"]["MAJOR"],
             issues=len(mistakes.get("issues", [])))
    h.note(f"Review {n}: {mistakes.get('verdict') or 'not judged'} → {decision}: {reason}")
    return {"iteration": n, "decision": decision, "reason": reason, "verdict": mistakes.get("verdict"),
            "blocking": record["blocking"], "valid": mistakes.get("valid")}


def _failed(project_id: str, n: int, error: str) -> dict:
    return {"schema": "openscientist.mistakes/v1", "project_id": project_id, "iteration": n, "valid": False,
            "judged": False, "error": error[:2000], "issues": [], "created_at": _now().isoformat()}


def _latest_result(project_id: str, kind: str) -> dict:
    with Session(engine) as s:
        run = s.exec(select(Run).where(Run.project_id == project_id, Run.kind == kind)
                     .order_by(Run.started_at.desc())).first()
        return (run.result or {}) if run else {}


async def _after_review(project_id: str) -> None:
    result = _latest_result(project_id, "review")
    decision, reason = result.get("decision"), result.get("reason", "")
    if decision in ("approved", "unresolved", "budget_exhausted"):
        finalize(project_id, decision, reason)
    elif decision == "review_failed":
        update(project_id, status="review_failed", attention=reason)
    elif decision == "repair_gates":
        start_gate_repair(project_id)
    elif decision == "repair":
        start_repair(project_id)


# ── Decision and tracking (pure) ───────────────────────────────────────────


def _score(blocking: dict) -> int:
    return 3 * blocking.get("FATAL", 0) + blocking.get("MAJOR", 0)


def decide(st: dict, mistakes: dict, spent_usd: float) -> tuple[str, str]:
    if mistakes.get("budget_limit"):
        return "budget_exhausted", beta.LIMIT_MESSAGE
    if not mistakes.get("valid"):
        return "review_failed", mistakes.get("error") or "The review could not be completed."
    first = st.get("session_first_iteration", 1)
    session = [it for it in st.get("iterations", []) if it["n"] >= first]
    rounds = sum(1 for it in session if it.get("decision") in REPAIRS)
    max_rounds, max_usd = st.get("max_rounds", settings.refinement_max_rounds), st.get("max_usd", 0.0)
    if not mistakes.get("judged"):
        gates = ", ".join(sorted({i.get("gate", "") for i in mistakes.get("issues", [])}))
        if rounds >= max_rounds:
            return "unresolved", f"Integrity gates ({gates}) still fail after {rounds} repair rounds."
        if spent_usd >= max_usd:
            return "budget_exhausted", f"The refinement budget (${max_usd:.2f}) is used up."
        return "repair_gates", f"Integrity gates failed ({gates}); the manuscript is rebuilt before review."
    blocking = [i for i in mistakes["issues"] if i.get("blocking")]
    if not blocking:
        if mistakes.get("verification") == "failed" and any(
                i.get("severity") in judge.BLOCKING_SEVERITIES for i in mistakes["issues"]):
            # Serious claims could not be checked: a failure never turns into approval.
            return "review_failed", "Serious claims could not be verified (the check failed); resume to retry."
        if not mistakes.get("verdict_consistent", True):
            return "unresolved", ("The reviewer's verdict contradicts its own findings in two independent reviews; "
                                  "a human decision is needed.")
        if mistakes.get("verdict") in ("accept", "minor_revision"):
            return "approved", "No blocking issues remain; the reviewer accepted the study."
        return "unresolved", ("The reviewer rejected the study without issues that could be verified; "
                              "a human decision is needed.")
    counts = {sev: sum(1 for i in blocking if i["severity"] == sev) for sev in ("FATAL", "MAJOR")}
    if rounds >= max_rounds:
        return "unresolved", f"{len(blocking)} blocking issues remain after {rounds} repair rounds."
    if spent_usd >= max_usd:
        return "budget_exhausted", f"The refinement budget (${max_usd:.2f}) is used up with blocking issues left."
    tracks = st.get("tracks", {})
    for tid, t in tracks.items():
        if t.get("severity") == "FATAL" and t.get("status") == "open" and t.get("open_streak", 0) >= 3:
            return "unresolved", f"A fatal issue ({tid}: {t['title']}) persisted through two repair attempts."
    # No convergence: two repair rounds without fewer blocking issues and without resolving any
    # (fixing one problem and then finding a different one is progress, not oscillation).
    n = mistakes.get("iteration", 0)
    scores = [_score(it.get("blocking", {})) for it in session if it.get("judged")] + [_score(counts)]
    progress = any(t.get("resolved_at") in (n - 1, n) for t in tracks.values())
    if len(scores) >= 3 and scores[-1] >= scores[-2] >= scores[-3] and not progress:
        return "unresolved", "Two repair rounds in a row neither reduced nor resolved the blocking issues."
    return "repair", f"{counts['FATAL']} fatal and {counts['MAJOR']} major issues to repair."


_STOP = {"the", "and", "for", "with", "not", "are", "was", "from", "that", "this", "into", "than", "does", "uses"}


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) >= 3 and w not in _STOP}


def _refs(issue: dict) -> set[str]:
    return {x.strip().lower().rstrip("/") for x in [*issue.get("affected", []), *issue.get("invalidates", [])] if x}


def _matches(issue: dict, track: dict) -> bool:
    if issue["category"] != track["category"]:
        return False
    if _refs(issue) & set(track.get("refs", [])):
        return True
    a, b = _tokens(issue["title"]), set(track.get("tokens", []))
    return bool(a and b) and len(a & b) / len(a | b) >= 0.5


def track_issues(tracks: dict, issues: list[dict], n: int, changed: set[str]) -> dict:
    """Match this review's FATAL/MAJOR issues to earlier tracks (annotating each issue with
    track_id and tracking status) and update the tracks. Open tracks not seen again are resolved."""
    tracks = copy.deepcopy(tracks)
    seen: set[str] = set()
    changed = {c.lower() for c in changed}
    for issue in issues:
        if issue["severity"] not in judge.BLOCKING_SEVERITIES:
            continue
        candidates = sorted(tracks.items(), key=lambda kv: kv[1].get("status") != "open")
        tid = next((k for k, t in candidates if k not in seen and _matches(issue, t)), None)
        status = "concern" if issue.get("open_concern") else "open" if issue.get("blocking") else "refuted"
        if tid is None:
            tid = f"T-{len(tracks) + 1:03d}"
            label = "regression" if changed and _refs(issue) & changed else "new"
            tracks[tid] = {"title": issue["title"], "category": issue["category"], "severity": issue["severity"],
                           "first_seen": n, "fix_attempts": 0, "disputed": False, "open_streak": 0,
                           "refs": sorted(_refs(issue)), "tokens": sorted(_tokens(issue["title"])), "seen": []}
        else:
            prior = tracks[tid]["status"]
            label = "resurfaced" if prior in ("resolved", "disclosed") else "persisting"
        t = tracks[tid]
        if label == "resurfaced":
            t["resolved_at"] = None  # it was not really resolved
        t.update(status=status, last_seen=n, severity=issue["severity"],
                 open_streak=(t.get("open_streak", 0) + 1) if status == "open" else 0,
                 refs=sorted(set(t.get("refs", [])) | _refs(issue)), seen=[*t.get("seen", []), n])
        issue["track_id"] = tid
        issue["tracking"] = {"status": label, "previous_ids": t.get("issue_ids", [])}
        t["issue_ids"] = [*t.get("issue_ids", []), issue["id"]]
        seen.add(tid)
    for tid, t in tracks.items():
        if tid not in seen and t.get("status") in ("open", "concern"):
            disclosed = t["status"] == "concern" or t.get("last_disposition") in ("disclose", "escalate")
            t.update(status="disclosed" if disclosed else "resolved", resolved_at=n, open_streak=0)
    return tracks


# ── Deterministic repair for failed integrity gates ────────────────────────

GATE_DIRECTIVES = {
    "H1": "The PDF must be rebuilt: compile paper/paper.tex with tectonic and fix every LaTeX error until "
          "paper/paper.pdf is produced by this run.",
    "H2": "Cite only keys present in paper/references.bib; remove or replace these unknown keys: {detail}",
    "H3": "Include only figure files that exist in the workspace. {detail}",
    "H5": "The research results changed after the previous draft: rewrite every number, table and claim from "
          "the current result files.",
    "H4": "Do not create, edit or delete any file outside paper/. Research files are regenerated only by "
          "re-running their tasks.",
}


def start_gate_repair(project_id: str) -> None:
    st = state(project_id)
    n = st["iteration"]
    mistakes = _previous_mistakes(project_id, n) or {}
    directives, rerun, orphaned = [], [], []
    _, mp, _ = _bp(project_id)
    for i in mistakes.get("issues", []):
        directives.append(GATE_DIRECTIVES[i["gate"]].format(detail=i["description"]))
        if i["gate"] == "H4":
            for path in i.get("invalidates", []):
                owners = [t["id"] for t in mp.get("tasks", []) if _under(path, {o["path"] for o in t["outputs"]})]
                rerun += owners
                orphaned += [] if owners else [path]
    if orphaned:  # nothing can regenerate them: the evidence itself is in doubt
        finalize(project_id, "unresolved", "The report stage changed research files that no task regenerates ("
                 + ", ".join(orphaned[:10]) + "); restore them by hand, then review again.")
        return
    update(project_id, status="repairing", gate_directives=sorted(set(directives)))
    changes = [{"task_id": t, "change": "Regenerate this task's outputs by re-running the code that produces them; "
                                        "they were modified outside the task."} for t in dict.fromkeys(rerun)]
    try:
        _release_stale_running(project_id)
        # Unfinished tasks are only set aside when a re-execution follows.
        skipped = skip_unselected(project_id, {c["task_id"] for c in changes}, set()) if changes else []
        apply_task_changes(project_id, changes)
    except ValueError as exc:
        update(project_id, status="attention", attention=str(exc))
        return
    _update_iteration(project_id, n, level="execution" if changes else "report", rerun_tasks=list(dict.fromkeys(rerun)),
                      skipped_unselected=skipped, changed=sorted(set(rerun)))
    if changes:  # only regenerated outputs need an execution; other unfinished tasks are left as they are
        start_repair_execution(project_id)
    else:
        start_report_step(project_id)


# ── Planner repair ─────────────────────────────────────────────────────────


def start_repair(project_id: str) -> Run | None:
    if beta.project_allowance(project_id) <= 0:
        finalize(project_id, "budget_exhausted", beta.LIMIT_MESSAGE)
        return None
    update(project_id, status="repairing", step="repair", attention=None)
    pipeline._set_stage(project_id, "reviewing")
    return jobs.start(project_id, "repair", _repair_job, then=_after_repair)


def _bp(project_id: str) -> tuple[Run, dict, dict[str, TaskState]]:
    with Session(engine) as s:
        project = s.get(Project, project_id)
        run = s.get(Run, project.blueprint["run_id"])
        states = {st.task_id: st for st in s.exec(select(TaskState).where(TaskState.blueprint_run_id == run.id))}
    return run, run.result["master_plan"], states


def repair_context(project_id: str, st: dict, mistakes: dict) -> str:
    with Session(engine) as s:
        project = s.get(Project, project_id)
        brief, gap, amendments = project.brief or {}, project.chosen_gap or {}, (project.settings or {}).get("amendments", [])
        plan = plan_agent.current_plan(project)
    _, mp, states = _bp(project_id)
    blocking = [i for i in mistakes["issues"] if i.get("blocking")]
    concerns = [i for i in mistakes["issues"] if i.get("open_concern")]

    def issue_text(i: dict) -> str:
        ev = "\n".join(f"    - [{e['source']} {e['locator']}] \"{e['quote'][:400]}\" — {e['observation'][:300]}"
                       for e in i.get("evidence", []))
        return (f"- {i['id']} (track {i.get('track_id')}, {i.get('tracking', {}).get('status', 'new')}) "
                f"{i['severity']} {i['category']}, origin {i['origin']}: {i['title']}\n"
                f"  {i['description']}\n  Why it matters: {i['why_it_matters']}\n"
                f"  Reviewer's corrective action: {i['corrective_action']}\n"
                f"  Affected: {', '.join(i.get('affected', []))}; invalidates: {', '.join(i.get('invalidates', []))}\n"
                f"  Evidence:\n{ev or '    (absence of: ' + ', '.join(i.get('absence_terms', [])) + ')'}")

    history = []
    for tid, t in st.get("tracks", {}).items():
        if len(t.get("seen", [])) > 1 or t.get("status") not in ("open", "concern"):
            history.append(f"- {tid} \"{t['title']}\" ({t['category']}): seen in reviews {t.get('seen')}, now "
                           f"{t['status']}; fix attempts {t.get('fix_attempts', 0)}; last disposition "
                           f"{t.get('last_disposition') or 'none'}{'; disputed before' if t.get('disputed') else ''}"
                           f"{'; last action: ' + t['last_action'] if t.get('last_action') else ''}")
    tasks = "\n".join(
        f"- {t['id']} [{states[t['id']].status if t['id'] in states else 'not started'}] {t['title']}: "
        f"{t['objective']} (depends on {', '.join(t['depends_on']) or 'nothing'}; outputs "
        f"{', '.join(o['path'] for o in t['outputs'])})" for t in mp["tasks"])
    directives = "\n".join(f"- {k}: {d['text']}" for k, d in st.get("directives", {}).items()) or "(none)"
    # This review's own record (decision "repair"/"repair_gates") is already appended to
    # st["iterations"] by the time this runs, so `rounds` already counts the round about to
    # happen — it is that round's number, not a count of rounds still to come before it.
    rounds = sum(1 for it in st.get("iterations", []) if it["n"] >= st.get("session_first_iteration", 1)
                 and it.get("decision") in REPAIRS)
    remaining = max(0.0, st["max_usd"] - spent(project_id, st["started_at"]))
    return (
        f"ORIGINAL RESEARCH OBJECTIVE (never change it):\nQuestion: {brief.get('core_question')}\n"
        f"Summary: {brief.get('summary')}\nChosen gap: {gap.get('question')} — hypothesis: {gap.get('hypothesis')}\n\n"
        f"PRE-REGISTERED PLAN:\n{json.dumps(st.get('preregistration'), ensure_ascii=False)}\n\n"
        f"CURRENT PLAN:\n{json.dumps({k: plan.get(k) for k in (*judge.PREREG_FIELDS, 'methods', 'datasets')}, ensure_ascii=False)}\n\n"
        f"PROTOCOL AMENDMENTS SO FAR:\n" + ("\n".join(f"- ({a['task']}) {a['text']}" for a in amendments) or "(none)")
        + f"\n\nBLUEPRINT TASKS:\n{tasks}\n\nREVIEW {mistakes['iteration']} (verdict {mistakes.get('verdict')}): "
        f"{mistakes.get('summary')}\n\nBLOCKING ISSUES (decide each):\n" + "\n".join(issue_text(i) for i in blocking)
        + "\n\nOPEN CONCERNS (must be disclosed in the manuscript):\n"
        + ("\n".join(issue_text(i) for i in concerns) or "(none)")
        + f"\n\nISSUE HISTORY:\n" + ("\n".join(history) or "(first review)")
        + f"\n\nCURRENT MANUSCRIPT DIRECTIVES (withdraw any that no longer apply):\n{directives}\n\n"
        f"LIMITS: repair round {rounds} of {st['max_rounds']}; about ${remaining:.2f} of the refinement budget left."
    )


def validate_repair(rp: plan_agent.RepairPlan, mistakes: dict, st: dict, mp: dict,
                    states: dict[str, TaskState]) -> list[str]:
    errors: list[str] = []
    issues = {i["id"]: i for i in mistakes["issues"]}
    blocking = {i["id"] for i in mistakes["issues"] if i.get("blocking")}
    concerns = {i["id"] for i in mistakes["issues"] if i.get("open_concern")}
    tasks = {t["id"] for t in mp["tasks"]}
    decided = [d.issue_id for d in rp.decisions]
    for iid in sorted(blocking - set(decided)):
        errors.append(f"No decision for blocking issue {iid}.")
    for iid in sorted({d for d in decided if decided.count(d) > 1}):
        errors.append(f"Issue {iid} has more than one decision.")
    for iid in sorted(set(decided) - blocking - concerns):
        errors.append(f"Unknown issue id {iid}.")
    for tc in rp.task_changes:
        if tc.task_id not in tasks:
            errors.append(f"task_changes names unknown task {tc.task_id}.")
    for tid in rp.rerun_failed_tasks:
        if tid not in tasks:
            errors.append(f"rerun_failed_tasks names unknown task {tid}.")
    def has_directive(issue_id: str) -> bool:
        return any(issue_id in x.issue_ids for x in rp.report_directives)

    for d in rp.decisions:
        issue = issues.get(d.issue_id)
        if issue is None:
            continue
        track = st.get("tracks", {}).get(issue.get("track_id") or "", {})
        if d.disposition == "fix":
            origin = ORIGIN_STAGE[issue["origin"]]
            if STAGES.index(d.root_cause) > STAGES.index(origin):
                errors.append(f"{d.issue_id} originates at the {origin} stage; it cannot be fixed at the later "
                              f"{d.root_cause} stage (fix the cause, or disclose it).")
            cites = any(d.issue_id in tc.issue_ids for tc in rp.task_changes)
            need = {
                "plan": bool(rp.plan_revision.strip()) and (bool(rp.blueprint_changes.strip()) or bool(rp.task_changes)),
                "blueprint": bool(rp.blueprint_changes.strip()),
                "execution": cites or bool(rp.blueprint_changes.strip()),
                "report": has_directive(d.issue_id),
            }[d.root_cause]
            if not need:
                errors.append(f"{d.issue_id}: a {d.root_cause}-stage fix needs "
                              + {"plan": "plan_revision plus blueprint_changes or task_changes",
                                 "blueprint": "blueprint_changes", "execution": "a task_change citing it",
                                 "report": "a report directive citing it"}[d.root_cause] + ".")
        elif d.disposition == "dispute":
            if not d.rationale.strip():
                errors.append(f"{d.issue_id}: a dispute needs an evidence-based rationale.")
            if track.get("disputed") or issue.get("tracking", {}).get("status") == "resurfaced":
                errors.append(f"{d.issue_id} was raised again after an earlier dispute or fix: fix, disclose or "
                              "escalate it.")
        elif not has_directive(d.issue_id):
            errors.append(f"{d.issue_id}: {d.disposition} needs a report directive citing it that discloses the "
                          "limitation.")
    for iid in sorted(concerns - set(decided)):
        if not has_directive(iid):
            errors.append(f"Open concern {iid} must be disclosed by a report directive citing it.")
    return errors


def _no_action(rp: plan_agent.RepairPlan) -> bool:
    return (all(d.disposition == "dispute" for d in rp.decisions) and not rp.task_changes
            and not rp.plan_revision.strip() and not rp.blueprint_changes.strip() and not rp.report_directives)


def _save(path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _load(path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except (OSError, json.JSONDecodeError):
        return None


async def _repair_job(project_id: str, h: RunHandle) -> dict:
    st = state(project_id)
    n = st["iteration"]
    mistakes = _previous_mistakes(project_id, n)
    if not mistakes:
        return {"outcome": "attention", "error": f"Review {n} has no mistakes.json to repair from."}
    out = judge.review_dir(project_id, n)
    _update_iteration(project_id, n, repair_run_id=h.run_id)
    bp_run, mp, states = _bp(project_id)
    try:
        # 1 · The Planning Agent's decision (saved before anything changes; reused on resume)
        try:
            rp = plan_agent.RepairPlan.model_validate(_load(out / "repair_plan.json") or {})
            h.note("Reusing the saved repair plan")
        except ValidationError:  # none saved yet (or unreadable): plan the repair
            rp = None
        if rp is None:
            h.phase("planning", "The Planning Agent is choosing root-cause fixes")
            context = repair_context(project_id, st, mistakes)
            rp = await plan_agent.draft_repair(context)
            errors = validate_repair(rp, mistakes, st, mp, states)
            if errors:
                h.note(f"Repair plan rejected ({errors[0][:120]}); asking once more")
                rp = await plan_agent.draft_repair(context, errors)
                errors = validate_repair(rp, mistakes, st, mp, states)
                if errors:
                    return {"outcome": "attention", "error": "The Planning Agent did not produce a valid repair plan: "
                            + "; ".join(errors[:5])}
            _save(out / "repair_plan.json", rp.model_dump())
        if _no_action(rp):
            return {"outcome": "unresolved", "reason": "The Planning Agent disputes every blocking issue; a human "
                                                       "decision is needed."}

        # 2 · Structural changes (model calls first, results saved before committing)
        plan_run_id, objective_changes = None, []
        revision = _load(out / "plan_revision.json")
        if rp.plan_revision.strip() and not revision:
            with Session(engine) as s:
                prev = plan_agent.current_plan(s.get(Project, project_id))
            h.phase("replanning", "Revising the research plan")
            plan, objective_changes = await plan_agent.revise_for_repair(prev, rp.plan_revision, h)
            revision = {"plan": plan, "objective_changes": objective_changes, "committed_run": None}
            _save(out / "plan_revision.json", revision)
        delta = _load(out / "blueprint_delta.json")
        if (rp.blueprint_changes.strip() or revision) and not delta:
            instruction = rp.blueprint_changes.strip() or "Align the blueprint with the revised research plan."
            if revision:
                instruction += ("\n\nThe research plan was revised: " + rp.plan_revision.strip()
                                + "\nRevised plan:\n" + json.dumps(revision["plan"], ensure_ascii=False)[:20000])
            new_mp, warnings, raw = await blueprint_agent.draft_delta(project_id, instruction, h)
            delta = {"master_plan": new_mp, "warnings": warnings, "delta": raw, "instruction": instruction,
                     "from_blueprint_run": bp_run.id, "committed_run": None}
            _save(out / "blueprint_delta.json", delta)
    except beta.BetaLimitReached:
        return {"outcome": "budget_exhausted", "reason": beta.LIMIT_MESSAGE}
    except (RuntimeError, anthropic.APIError) as exc:
        # anthropic.APIError covers TRANSIENT_ERRORS and permanent (e.g. 4xx) failures alike:
        # either way the repair cannot proceed, and "attention" (resumable) must be set here so
        # the status is not left stuck at "repairing" for anything that reads it directly.
        return {"outcome": "attention", "error": f"Repair planning failed: {type(exc).__name__}: {exc}"[:1500]}

    if delta:  # task changes must name tasks of the amended blueprint
        known = {t["id"] for t in delta["master_plan"]["tasks"]}
        missing = sorted(({tc.task_id for tc in rp.task_changes} | set(rp.rerun_failed_tasks)) - known)
        if missing:
            for name, saved in (("repair_plan.json", None), ("plan_revision.json", revision),
                                ("blueprint_delta.json", delta)):
                if not (saved or {}).get("committed_run"):
                    (out / name).unlink(missing_ok=True)  # resume plans the repair again
            return {"outcome": "attention", "error": "The repair plan re-runs tasks its own blueprint amendment "
                    f"removes ({', '.join(missing)}); resume to plan the repair again."}

    # 3 · Commit (idempotent: each step records that it was applied)
    try:
        result = _commit(project_id, n, rp, mistakes, revision, delta, out)
    except ValueError as exc:
        return {"outcome": "attention", "error": str(exc)}
    h.counts(rerun=len(result["rerun_tasks"]), carried=len(result["carried_over"]))
    h.note(f"Repair level {result['level']}: re-running {', '.join(result['rerun_tasks']) or 'no tasks'}")
    return result


def _commit(project_id: str, n: int, rp: plan_agent.RepairPlan, mistakes: dict, revision: dict | None,
            delta: dict | None, out) -> dict:
    level, plan_run_id, bp_run_id, carried, invalidated = "report", None, None, [], set()
    _release_stale_running(project_id)
    if revision:
        level = "plan"
        if not revision.get("committed_run"):
            run = plan_agent.save_plan_run(project_id, revision["plan"], rp.plan_revision)
            plan_agent.approve(project_id)
            revision["committed_run"] = run.id
            _save(out / "plan_revision.json", revision)
        plan_run_id = revision["committed_run"]
    old_run, old_mp, old_states = _bp(project_id)
    unfinished_before = {t for t, s in old_states.items() if s.status in UNFINISHED}
    reasons = {t: f"{s.status}: {s.note or s.status}" for t, s in old_states.items()}
    if delta:
        level = "plan" if revision else "blueprint"
        if not delta.get("committed_run"):
            run = blueprint_agent.save_blueprint_run(project_id, delta["master_plan"], delta["warnings"],
                                                     delta["instruction"], plan_run_id)
            delta["committed_run"] = run.id
            _save(out / "blueprint_delta.json", delta)
        bp_run_id = delta["committed_run"]
        source = delta["from_blueprint_run"]
        with Session(engine) as s:
            src = s.get(Run, source)
        src_mp = src.result["master_plan"]
        carried, invalidated = carry_over(project_id, source, bp_run_id, src_mp, delta["master_plan"])
        orchestrator.prepare_states(project_id, bp_run_id, delta["master_plan"])
        if _current_bp_id(project_id) != bp_run_id:  # rows exist before the pointer moves
            blueprint_agent.approve(project_id)
        with Session(engine) as s:
            src_states = {st.task_id: st for st in s.exec(select(TaskState).where(TaskState.blueprint_run_id == source))}
        unfinished_before = {t for t, s in src_states.items() if s.status in UNFINISHED}
        reasons = {t: f"{s.status}: {s.note or s.status}" for t, s in src_states.items()}
    pipeline._set_stage(project_id, "reviewing")
    selected = set(rp.rerun_failed_tasks) | {tc.task_id for tc in rp.task_changes} | invalidated
    skipped = skip_unselected(project_id, selected, unfinished_before, reasons)
    _requeue(project_id, set(rp.rerun_failed_tasks))
    changes = [tc.model_dump() for tc in rp.task_changes]
    apply_task_changes(project_id, changes)
    if changes or rp.rerun_failed_tasks:
        level = level if level in ("plan", "blueprint") else "execution"
    _add_directives(project_id, n, rp, mistakes)
    rerun = sorted(t for t, s in _states(project_id).items() if s.status not in ("done", "skipped"))
    _, mp, _ = _bp(project_id)
    changed = sorted(set(rerun) | {o["path"] for t in mp["tasks"] if t["id"] in rerun for o in t["outputs"]})
    _update_tracks_after_repair(project_id, rp, mistakes, changes)
    _update_iteration(project_id, n, level=level, plan_run_id=plan_run_id,
                      blueprint_run_id=bp_run_id, rerun_tasks=rerun, carried_over=carried, skipped_unselected=skipped,
                      objective_changes=(revision or {}).get("objective_changes", []), changed=changed)
    return {"outcome": "execute" if rerun else "report", "level": level, "rerun_tasks": rerun,
            "carried_over": carried, "skipped": skipped, "plan_run_id": plan_run_id, "blueprint_run_id": bp_run_id}


def _current_bp_id(project_id: str) -> str | None:
    with Session(engine) as s:
        return (s.get(Project, project_id).blueprint or {}).get("run_id")


def _states(project_id: str) -> dict[str, TaskState]:
    return _bp(project_id)[2]


def _pending(project_id: str) -> bool:
    """Anything not done or skipped still needs execution (prepare_states re-queues running,
    cancelled, blocked and failed tasks; the scheduler re-asks for human ones)."""
    return any(s.status not in ("done", "skipped") for s in _states(project_id).values())


def _release_stale_running(project_id: str) -> None:
    """Task rows a crashed or restarted execution left 'running' (only Run rows are marked
    interrupted) are released when no execution is live, so request_changes can reset them."""
    if jobs.is_running(project_id, "execute"):
        return
    bp = _current_bp_id(project_id)
    with Session(engine) as s:
        for st in s.exec(select(TaskState).where(TaskState.blueprint_run_id == bp, TaskState.status == "running")):
            st.status, st.note = "cancelled", "Interrupted (no execution was running)"
            s.add(st)
        s.commit()


def _requeue(project_id: str, task_ids: set[str]) -> None:
    """Unfinished tasks the planner wants retried (failed, skipped, cancelled, blocked, human)
    become pending, keeping their attempt count so retries escalate."""
    if not task_ids:
        return
    states = _states(project_id)
    with Session(engine) as s:
        for tid in task_ids:
            st = states.get(tid)
            if st is not None and st.status not in ("done", "running", "pending"):
                row = s.get(TaskState, st.id)
                row.status = "pending"
                s.add(row)
        s.commit()


def _update_tracks_after_repair(project_id: str, rp: plan_agent.RepairPlan, mistakes: dict,
                                changes: list[dict]) -> None:
    st = state(project_id)
    tracks = st.get("tracks", {})
    by_issue = {i["id"]: i.get("track_id") for i in mistakes["issues"]}
    for d in rp.decisions:
        tid = by_issue.get(d.issue_id)
        if not tid or tid not in tracks:
            continue
        t = tracks[tid]
        t["last_disposition"] = d.disposition
        t["needs_human"] = t.get("needs_human") or d.disposition == "escalate"
        if d.disposition == "dispute":
            t["disputed"] = True
        if d.disposition == "fix":
            t["fix_attempts"] = t.get("fix_attempts", 0) + 1
            acts = [f"re-run {c['task_id']}: {c['change'][:160]}" for c in changes if d.issue_id in c["issue_ids"]]
            if rp.plan_revision.strip() and d.root_cause == "plan":
                acts.append("plan revised: " + rp.plan_revision[:160])
            if rp.blueprint_changes.strip() and d.root_cause in ("plan", "blueprint"):
                acts.append("blueprint amended: " + rp.blueprint_changes[:160])
            if d.root_cause == "report":
                acts.append("manuscript directive")
            t["last_action"] = "; ".join(acts)[:400]
    update(project_id, tracks=tracks)


def _cited_notes(project_id: str, text: str) -> str:
    """Notes of the papers a directive names by citation key (the writer otherwise sees only titles)."""
    from .agents.report import _references

    refs, _ = _references(project_id)
    keys = [k for k in refs if re.search(rf"\b{re.escape(k)}\b", text)]
    notes = []
    for k in keys[:5]:
        p = refs[k]
        n = p.notes or {}
        notes.append(f"[{k}] {p.title} ({p.year}): {(p.abstract or p.tldr or '')[:600]} "
                     f"Contribution: {n.get('contribution', '')} Findings: {' | '.join(n.get('key_findings', [])[:3])}")
    return ("\n  What the cited papers actually report:\n  " + "\n  ".join(notes)) if notes else ""


def _add_directives(project_id: str, n: int, rp: plan_agent.RepairPlan, mistakes: dict) -> None:
    st = state(project_id)
    directives = {k: v for k, v in st.get("directives", {}).items() if k not in set(rp.withdraw_directives)}
    by_issue = {i["id"]: i.get("track_id") for i in mistakes["issues"]}
    for k, d in enumerate(rp.report_directives, start=1):
        key = f"D{n}-{k}"
        if key in directives:
            continue
        directives[key] = {"text": d.text + _cited_notes(project_id, d.text), "issues": d.issue_ids,
                           "tracks": sorted({by_issue[i] for i in d.issue_ids if by_issue.get(i)}), "iteration": n}
    update(project_id, directives=directives)


async def _after_repair(project_id: str) -> None:
    result = _latest_result(project_id, "repair")
    outcome = result.get("outcome")
    if outcome == "execute":
        start_repair_execution(project_id)
    elif outcome == "report":
        start_report_step(project_id)
    elif outcome in ("unresolved", "budget_exhausted"):
        finalize(project_id, outcome, result.get("reason", ""))
    else:
        update(project_id, status="attention", attention=result.get("error") or "Repair needs attention.")


# ── Carry-over, skipping, task changes ─────────────────────────────────────


def task_hash(task: dict, mp: dict) -> str:
    """Identity of what a task does: its spec (minus estimates and retry counts), its agent and
    the dataset specs it reads (minus URL check results)."""
    t = {k: v for k, v in task.items() if k not in ("max_cost_usd", "retries")}
    t["compute"] = {"kind": (task.get("compute") or {}).get("kind")}
    agent = next((a for a in mp.get("agents", []) if a["id"] == task.get("agent")), None)
    refs = set(task.get("resources", [])) | {i["source"].split(":", 1)[1] for i in task.get("inputs", [])
                                             if i["source"].startswith("dataset:")}
    datasets = [{k: v for k, v in d.items() if k != "verified"} for d in mp.get("datasets", []) if d["id"] in refs]
    blob = json.dumps({"task": t, "agent": agent, "datasets": datasets}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def dependents(tasks: list[dict], roots: set[str]) -> set[str]:
    out, frontier = set(roots), list(roots)
    while frontier:
        cur = frontier.pop()
        for t in tasks:
            if cur in t.get("depends_on", []) and t["id"] not in out:
                out.add(t["id"])
                frontier.append(t["id"])
    return out


def invalidated_tasks(old_mp: dict, new_mp: dict) -> set[str]:
    old = {t["id"]: task_hash(t, old_mp) for t in old_mp["tasks"]}
    changed = {t["id"] for t in new_mp["tasks"] if old.get(t["id"]) != task_hash(t, new_mp)}
    return dependents(new_mp["tasks"], changed)


COPY_FIELDS = ("agent", "status", "attempts", "cost", "summary", "artifacts", "checks", "issues", "events", "note",
               "feedback", "started_at", "finished_at")


def carry_over(project_id: str, old_bp: str, new_bp: str, old_mp: dict, new_mp: dict) -> tuple[list[str], set[str]]:
    """Copy the finished states of unchanged tasks to the new blueprint run (their outputs are
    already in the shared workspace). Idempotent: rows the new run already worked on are kept."""
    invalid = invalidated_tasks(old_mp, new_mp)
    carried = []
    with Session(engine) as s:
        old = {st.task_id: st for st in s.exec(select(TaskState).where(TaskState.blueprint_run_id == old_bp))}
        new = {st.task_id: st for st in s.exec(select(TaskState).where(TaskState.blueprint_run_id == new_bp))}
        for t in new_mp["tasks"]:
            tid, src = t["id"], old.get(t["id"])
            if tid in invalid or src is None or src.status not in ("done", "skipped"):
                continue
            row = new.get(tid)
            if row is not None and not (row.status == "pending" and row.attempts == 0 and not row.events):
                continue
            row = row or TaskState(project_id=project_id, blueprint_run_id=new_bp, task_id=tid, agent=src.agent)
            for f in COPY_FIELDS:
                setattr(row, f, copy.deepcopy(getattr(src, f)))
            row.note = f"carried over from blueprint run {old_bp}" + (f"; {src.note}" if src.note else "")
            s.add(row)
            carried.append(tid)
        s.commit()
    return carried, invalid


def skip_unselected(project_id: str, selected: set[str], unfinished_before: set[str],
                    reasons: dict[str, str] | None = None) -> list[str]:
    """Tasks that were unfinished when the paper was written and that the repair does not re-run
    are recorded as skipped (with the original reason), so starting execution does not silently
    retry them. Dependents of selected tasks are never skipped: they must re-run."""
    run, mp, states = _bp(project_id)
    keep = dependents(mp["tasks"], selected)
    unfinished = unfinished_before or {t for t, s in states.items() if s.status in UNFINISHED}
    skipped = []
    with Session(engine) as s:
        for tid in sorted(unfinished - keep):
            st = s.get(TaskState, states[tid].id) if tid in states else None
            if st is None or st.status in ("done", "skipped", "running"):
                continue
            reason = (reasons or {}).get(tid) or f"{st.status}: {st.note or st.status}"
            st.status, st.note = "skipped", f"Not re-run by the scientific review repair (was {reason})"[:2000]
            s.add(st)
            skipped.append(tid)
        s.commit()
    return skipped


def apply_task_changes(project_id: str, changes: list[dict]) -> None:
    """orchestrator.request_changes for each change (target + dependents reset, amendment recorded).
    Idempotent: a target already pending with the same feedback is not changed again."""
    for c in changes:
        change = judge._REVIEW_IDS.sub("", c["change"]).strip()  # review ids never reach the agents
        states = _states(project_id)
        st = states.get(c["task_id"])
        if st is None:
            raise ValueError(f"Unknown task {c['task_id']}")
        if st.status == "pending" and st.feedback == change:
            continue
        if st.status == "skipped":
            with Session(engine) as s:
                row = s.get(TaskState, st.id)
                row.status = "pending"
                s.add(row)
                s.commit()
        orchestrator.request_changes(project_id, c["task_id"], change)


# ── Execution and report steps ─────────────────────────────────────────────


def start_repair_execution(project_id: str) -> Run | None:
    st = state(project_id)
    remaining = st["max_usd"] - spent(project_id, st["started_at"])
    if remaining <= 0:
        finalize(project_id, "budget_exhausted", f"The refinement budget (${st['max_usd']:.2f}) is used up.")
        return None
    # The orchestrator pauses at settings.budget.llm_usd and GPU jobs refuse to plan past
    # settings.gpu_budget_usd (both read fresh): cap this execution at the refinement allowance.
    # The originals are restored when the loop ends; the watcher stops at the combined cap.
    runner = gpu_runner()
    with Session(engine) as s:
        project = s.get(Project, project_id)
        cfg = dict(project.settings or {})
        budget = dict(cfg.get("budget") or {})
        override = st.get("budget_override") or {}
        llm_cap = round(orchestrator.spent(project_id) + remaining, 4)
        gpu_cap = round(runner.gpu_spent(project_id) + remaining, 4)
        override = {
            "llm": {"original": (override.get("llm") or {}).get("original", budget.get("llm_usd", 15.0)), "set": llm_cap},
            "gpu": {"original": (override.get("gpu") or {}).get("original", cfg.get("gpu_budget_usd")), "set": gpu_cap},
        }
        budget["llm_usd"] = llm_cap
        cfg["budget"] = budget
        cfg["gpu_budget_usd"] = gpu_cap
        project.settings = cfg
        s.add(project)
        s.commit()
    update(project_id, status="repairing", step="execute", attention=None, budget_override=override)
    run = pipeline.start_execution(project_id)  # starts the watcher (ensure_watcher)
    _update_iteration(project_id, st["iteration"], execute_run_id=run.id)
    return run


def ensure_watcher(project_id: str) -> None:
    """Called whenever an execution starts (pipeline.start_execution): repair executions, including
    ones the user resumes from the execution view, are watched for budget and human pauses."""
    st = state(project_id)
    if st.get("status") in ("repairing", "attention") and st.get("step") == "execute" and project_id not in _watchers:
        _watchers[project_id] = asyncio.get_running_loop().create_task(_watch_execution(project_id))


async def _watch_execution(project_id: str) -> None:
    """Budget, beta-limit and human pauses never return from the orchestrator by themselves:
    stop at the refinement budget, and flag pauses that need a person."""
    try:
        while True:
            await asyncio.sleep(WATCH_INTERVAL)
            if not jobs.is_running(project_id, "execute"):
                return
            st = state(project_id)
            if st.get("status") not in ("repairing", "attention") or st.get("step") != "execute":
                return
            ctl = orchestrator.control(project_id)
            reason = (ctl.reason if ctl else None) or ""
            over = spent(project_id, st["started_at"]) >= st["max_usd"]  # LLM and GPU together
            if over or reason.startswith(("budget:", "beta_limit_reached")):
                finalize(project_id, "budget_exhausted",
                         f"Stopped during repair execution: {reason or 'the refinement budget is used up'}. The paper "
                         "shown is the last reviewed one; the workspace may hold partial repairs.")
                if ctl:
                    ctl.cancelled = True
                    ctl.resume()
                return
            if reason.startswith(("human", "checkpoint")) and st["status"] != "attention":
                update(project_id, status="attention", attention=f"Execution paused: {reason}")
            elif not reason and st["status"] == "attention" and (st.get("attention") or "").startswith("Execution paused"):
                update(project_id, status="repairing", attention=None)
    except Exception:  # never let the watcher take the loop down
        log.exception("refinement watcher for %s failed", project_id)
    finally:
        _watchers.pop(project_id, None)


def start_report_step(project_id: str) -> Run:
    st = state(project_id)
    update(project_id, status="repairing", step="report", attention=None)
    run = pipeline.start_report(project_id)
    _update_iteration(project_id, st["iteration"], report_run_id=run.id)
    return run


# ── Finish, resume, stop, start ────────────────────────────────────────────


def _restore_budget(project_id: str, st: dict) -> None:
    """Put back the execution budgets a repair execution capped, unless the user changed them since."""
    override = st.get("budget_override") or {}
    if not override:
        return
    with Session(engine) as s:
        project = s.get(Project, project_id)
        cfg = dict(project.settings or {})
        budget = dict(cfg.get("budget") or {})
        llm, gpu = override.get("llm") or {}, override.get("gpu") or {}
        if llm and budget.get("llm_usd") == llm.get("set"):
            budget["llm_usd"] = llm["original"]
            cfg["budget"] = budget
        if gpu and cfg.get("gpu_budget_usd") == gpu.get("set"):
            if gpu.get("original") is None:
                cfg.pop("gpu_budget_usd", None)
            else:
                cfg["gpu_budget_usd"] = gpu["original"]
        project.settings = cfg
        s.add(project)
        s.commit()


def finalize(project_id: str, status: str, reason: str) -> dict:
    st = state(project_id)
    _restore_budget(project_id, st)
    tracks = st.get("tracks", {})
    outcome = {
        "status": status, "reason": reason, "at": _now().isoformat(), "iteration": st.get("iteration"),
        "unresolved": [{"track": k, "title": t["title"], "severity": t["severity"]} for k, t in tracks.items()
                       if t.get("status") == "open"],
        "open_concerns": [{"track": k, "title": t["title"]} for k, t in tracks.items() if t.get("status") == "concern"],
        "needs_human": [{"track": k, "title": t["title"]} for k, t in tracks.items() if t.get("needs_human")],
        "resolved_by": {s: sum(1 for t in tracks.values() if t.get("status") == s)
                        for s in ("resolved", "disclosed", "refuted")},
    }
    # A repair execution still stopping keeps step "execute": after_execution completes the stage.
    executing = jobs.is_running(project_id, "execute") and st.get("step") == "execute"
    update(project_id, status=status, step="execute" if executing else None, outcome=outcome,
           budget_override=None, attention=None)
    if not executing:
        pipeline._set_stage(project_id, "complete")
    write_history(project_id)
    return outcome


def resume(project_id: str) -> str:
    st = view(project_id)
    status, step = st.get("status"), st.get("step")
    if status in FINAL or not status:
        raise ValueError("No scientific review to resume; start a new one")
    if any(st["live"][k] for k in ("review", "repair", "report")):
        raise ValueError("A review step is already running")
    if st["live"]["execute"]:
        ctl = orchestrator.control(project_id)
        if ctl:
            ctl.resume()
        return "execution resumed"
    if step == "review" or status == "review_failed":
        start_review(project_id)  # unchanged evidence reuses the last valid review at no cost
    elif step == "repair":
        start_repair(project_id)
    elif step == "execute":
        _release_stale_running(project_id)
        if _pending(project_id):
            start_repair_execution(project_id)
        else:
            start_report_step(project_id)
    elif step == "report":
        it = next((i for i in reversed(st.get("iterations", [])) if i.get("report_run_id")), None)
        with Session(engine) as s:
            run = s.get(Run, it["report_run_id"]) if it else None
        if run is not None and run.status == "done":  # the rewrite finished; only its review is missing
            start_review(project_id)
        else:
            start_report_step(project_id)
    else:
        start_review(project_id)
    return step or "review"


def stop(project_id: str) -> dict:
    st = state(project_id)
    for kind in ("review", "repair"):
        jobs.cancel(project_id, kind)
    rewriting = st.get("step") == "report" and jobs.cancel(project_id, "report")
    if st.get("step") == "execute" and (ctl := orchestrator.control(project_id)):
        ctl.cancelled = True
        ctl.resume()
    outcome = finalize(project_id, "stopped", "Stopped by you.")
    if rewriting:  # the paper may be half rewritten: it is no longer the reviewed version
        update(project_id, stale=True)
    return outcome


def start(project_id: str) -> Run | None:
    """Opt a project in and start a new review session of its current paper."""
    with Session(engine) as s:
        project = s.get(Project, project_id)
        report = s.exec(select(Run).where(Run.project_id == project_id, Run.kind == "report")
                        .order_by(Run.started_at.desc())).first()
        if not report or report.status != "done":
            raise ValueError("Write the report first")
        cfg = dict(project.settings or {})
        cfg["refinement"] = {**(cfg.get("refinement") or {}), "enabled": True}
        project.settings = cfg
        s.add(project)
        s.commit()
    if state(project_id).get("status") in ACTIVE and any(jobs.is_running(project_id, k) for k in
                                                         ("review", "repair", "execute", "report")):
        raise ValueError("A scientific review is already in progress")
    begin_session(project_id)
    return start_review(project_id)


# ── History files ──────────────────────────────────────────────────────────

LIMITATION = ("Approval means an independent model reviewer (Claude Sonnet 4.6, the same model family that "
              "wrote the study) found no blocking scientific problems in the paper and its evidence, and the "
              "platform's integrity checks passed. It is a quality gate, not a guarantee of correctness.")


def write_history(project_id: str) -> None:
    st = state(project_id)
    out = judge.review_dir(project_id)
    out.mkdir(parents=True, exist_ok=True)
    rows = ["| Review | Verdict | Decision | Fatal | Major | Repair level | Re-run tasks | Cost |",
            "|---|---|---|---|---|---|---|---|"]
    for it in st.get("iterations", []):
        rows.append(f"| {it['n']} | {it.get('verdict') or '—'} | {it['decision']} | {it['blocking'].get('FATAL', 0)} | "
                    f"{it['blocking'].get('MAJOR', 0)} | {it.get('level', '—')} | "
                    f"{', '.join(it.get('rerun_tasks', [])) or '—'} | ${it.get('cost_usd', 0):.2f} |")
    tracks = [f"- {k} [{t['status']}] {t['severity']} {t['category']}: {t['title']} (seen in reviews "
              f"{', '.join(map(str, t.get('seen', [])))})" for k, t in st.get("tracks", {}).items()]
    (out / "HISTORY.md").write_text("# Scientific review history\n\n" + "\n".join(rows) + "\n\n## Issues\n\n"
                                    + ("\n".join(tracks) or "(none)") + "\n", encoding="utf-8")
    o = st.get("outcome") or {}
    lines = [f"# Scientific review: {o.get('status') or st.get('status')}", "", o.get("reason", ""), "", LIMITATION, ""]
    if o.get("unresolved"):
        lines += ["## Unresolved blocking issues", *[f"- {u['track']} ({u['severity']}): {u['title']}" for u in
                                                   o["unresolved"]], ""]
    if o.get("open_concerns"):
        lines += ["## Open concerns (disclosed)", *[f"- {u['track']}: {u['title']}" for u in o["open_concerns"]], ""]
    if o.get("needs_human"):
        lines += ["## Needs a human decision", *[f"- {u['track']}: {u['title']}" for u in o["needs_human"]], ""]
    (out / "REVIEW.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
