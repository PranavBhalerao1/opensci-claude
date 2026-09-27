"""Stage 3 · Gap finding.

propose (flagship model, reads all notes) → novelty check per gap (targeted
searches + standard-model verdict) → score & rank. Guided users pick a gap;
autonomous mode takes the top one.
"""

import asyncio
import re
from typing import Literal

import httpx
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..config import settings
from ..db import Paper, Project, ProjectPaper, Run, engine
from ..jobs import RunHandle
from ..llm import parse
from ..sources.common import norm_title
from .literature import brief_context, cached_search, cite

NOVELTY_RESULTS = 12  # external papers shown to the novelty judge per gap
WEIGHTS = {"novelty": 0.3, "feasibility": 0.3, "impact": 0.25, "testability": 0.15}


# ── Schemas ────────────────────────────────────────────────────────────────


class Score(BaseModel):
    score: int = Field(description="1 (poor) to 5 (excellent)")
    why: str = Field(description="One sentence")


class Scores(BaseModel):
    novelty: Score
    feasibility: Score = Field(description="Given the brief's data, compute and expertise")
    impact: Score
    testability: Score


class CandidateGap(BaseModel):
    title: str = Field(description="Max 10 words")
    question: str = Field(description="The precise research question, one sentence")
    gap_type: Literal[
        "untested_combination",
        "conflicting_evidence",
        "untested_assumption",
        "missing_evaluation",
        "generalization",
        "methodological",
        "data",
    ]
    why_open: str = Field(description="2-4 sentences of evidence that this is open, citing papers as [index]")
    hypothesis: str
    approach: str = Field(description="2-4 sentences: how OpenScientist could test it computationally")
    data_needed: str
    compute_needed: str
    risks: list[str]
    supporting_papers: list[int] = Field(description="Indices of papers that motivate this gap")
    novelty_queries: list[str] = Field(
        description="3 short keyword search queries (3-6 words each, no punctuation) that would find prior work already doing this"
    )
    scores: Scores


class GapProposals(BaseModel):
    gaps: list[CandidateGap] = Field(description="5-6 distinct candidate gaps")


class ClosestWork(BaseModel):
    i: int = Field(description="Index of the paper in the prior-work list")
    overlap: str = Field(description="What it already covers, one sentence")


class NoveltyVerdict(BaseModel):
    status: Literal["novel", "partially_addressed", "already_done"]
    explanation: str = Field(description="1-2 sentences")
    closest: list[ClosestWork] = Field(description="Up to 3 most overlapping papers; [] if none overlap")
    novelty: int = Field(description="Revised novelty score 1-5 after seeing prior work")


PROPOSE_INSTRUCTIONS = """\
You are the gap-finding scientist of OpenScientist. From the literature notes,
identify research gaps worth an investigation that OpenScientist can execute
computationally (public data and scientific databases, simulations and modelling,
CAD/geometry, statistical analyses, ML, meta-analyses) within the brief's constraints.

A good gap is specific, supported by evidence in the notes (limitations, conflicts,
missing evaluations, untested combinations), testable with a clear outcome, and
publishable if it works. Avoid vague gaps ("more research is needed"). Make the
candidates genuinely different from each other. Score honestly: feasibility must
reflect the user's stated resources. Cite papers only by [index].
"""

NOVELTY_INSTRUCTIONS = """\
You check whether a proposed research gap has already been addressed. Compare the
gap with the prior-work list. "already_done" only if a paper clearly answers the
same question with comparable setup; "partially_addressed" if work overlaps but
leaves the core question open. Be skeptical but fair.
The explanation is shown to the user: name papers by a short title, never by
index, and do not mention "the list" or its contents being incomplete."""


# ── Helpers ────────────────────────────────────────────────────────────────


def _overall(scores: dict) -> float:
    return round(sum(scores[k]["score"] * w for k, w in WEIGHTS.items()), 2)


def _paper_digest(n: int, p: Paper) -> str:
    notes = p.notes or {}
    return (
        f"[{n}] {p.title} ({p.year}). {notes.get('contribution', '')} "
        f"Methods: {', '.join(notes.get('methods', [])[:5])}. Data: {', '.join(notes.get('datasets', [])[:3])}. "
        f"Findings: {' | '.join(notes.get('key_findings', [])[:2])}. "
        f"Limitations: {' | '.join(notes.get('limitations', [])[:3]) or 'none stated'}"
    )


async def _novelty(
    client: httpx.AsyncClient, gap: CandidateGap, known_titles: set[str]
) -> tuple[NoveltyVerdict, list[dict]]:
    """Search for prior work on the gap and have a model judge the overlap.

    Raises if every search fails, so a failed check is never reported as "novel".
    """
    seen: dict[str, dict] = {}
    queries = gap.novelty_queries[:3]
    failed = 0
    for n, q in enumerate(queries + [gap.title]):
        # The title is a fallback when the targeted queries surface too little.
        if n == len(queries) and len(seen) >= 5:
            break
        try:
            records = await cached_search(client, "s2", q, 20)
        except Exception:
            failed += 1
            continue
        for r in records[:8]:
            key = norm_title(r.title)
            if key not in seen and (r.abstract or r.tldr):
                seen[key] = {
                    "title": r.title,
                    "year": r.year,
                    "url": r.url,
                    "abstract": (r.abstract or r.tldr or "")[:900],
                    "in_review": key in known_titles,
                }
    if failed == len(queries) + 1:
        raise RuntimeError("all novelty searches failed")
    prior = list(seen.values())[:NOVELTY_RESULTS]
    if not prior:
        verdict = NoveltyVerdict(
            status="novel", explanation="Targeted searches returned no related papers.",
            closest=[], novelty=gap.scores.novelty.score,
        )
        return verdict, []

    listing = "\n\n".join(f"[{i}] {p['title']} ({p['year']})\n{p['abstract']}" for i, p in enumerate(prior))
    verdict = await parse(
        model=settings.model_standard,
        instructions=NOVELTY_INSTRUCTIONS,
        messages=[{
            "role": "user",
            "content": f"Proposed gap: {gap.question}\nHypothesis: {gap.hypothesis}\nApproach: {gap.approach}"
                       f"\n\nPrior work:\n\n{listing}",
        }],
        schema=NoveltyVerdict,
        reasoning_effort="medium",
    )
    closest = [
        {**{k: prior[c.i][k] for k in ("title", "year", "url", "in_review")}, "overlap": c.overlap}
        for c in verdict.closest
        if 0 <= c.i < len(prior)
    ]
    return verdict, closest


# ── Job ────────────────────────────────────────────────────────────────────


async def run(project_id: str, h: RunHandle, feedback: str | None = None) -> dict:
    with Session(engine) as s:
        project = s.get(Project, project_id)
        brief = project.brief
        lit_run = s.exec(
            select(Run)
            .where(Run.project_id == project_id, Run.kind == "literature", Run.status == "done")
            .order_by(Run.started_at.desc())
        ).first()
        rows = s.exec(
            select(ProjectPaper, Paper)
            .join(Paper, Paper.id == ProjectPaper.paper_id)
            .where(ProjectPaper.project_id == project_id, ProjectPaper.included)
            .order_by(ProjectPaper.relevance.desc(), ProjectPaper.score.desc())
        ).all()
    if not lit_run:
        raise RuntimeError("Run the literature review first")
    papers = [p for _, p in rows if p.notes]
    overview = lit_run.result["overview"]

    # 1 · Propose
    h.phase("proposing", f"Reading {len(papers)} papers' notes for gaps")
    context = (
        f"{brief_context(brief)}\nData: {brief['data_resources']}\nCompute: {brief['compute_resources']}\n"
        f"User expertise: {brief['user_expertise']}\nConstraints: {'; '.join(brief['constraints'])}\n\n"
        f"Themes: {'; '.join(t['name'] + ' — ' + t['description'] for t in overview['themes'])}\n"
        f"Open problems noted: {'; '.join(overview['open_problems'])}\n\n"
        "Papers:\n" + "\n".join(_paper_digest(n, p) for n, p in enumerate(papers))
    )
    if feedback:
        context += f"\n\nThe user reviewed an earlier set of gaps and asks: {feedback}"
    proposals = await parse(
        model=settings.model_reasoning,
        instructions=PROPOSE_INSTRUCTIONS,
        messages=[{"role": "user", "content": context}],
        schema=GapProposals,
        # Medium: the novelty check afterwards catches weak gaps; high doubled cost and time.
        reasoning_effort="medium",
    )
    gaps = proposals.gaps[:6]
    h.counts(proposed=len(gaps), checked=0)
    h.note(f"Proposed {len(gaps)} candidate gaps")

    # 2 · Novelty check
    h.phase("checking", "Searching for prior work that already answers each gap")
    known = {p.norm_title for p in papers}
    checked = 0

    async def check(gap: CandidateGap):
        nonlocal checked
        try:
            out = await _novelty(client, gap, known)
        except Exception as exc:
            h.note(f"Novelty check failed for “{gap.title}” ({type(exc).__name__})")
            out = None
        checked += 1
        h.counts(checked=checked)
        return out

    async with httpx.AsyncClient(timeout=40) as client:
        verdicts = await asyncio.gather(*(check(g) for g in gaps))

    # 3 · Score & rank
    h.phase("ranking", "Scoring and ranking")
    results = []
    for n, (gap, v) in enumerate(zip(gaps, verdicts)):
        g = gap.model_dump()
        g["id"] = f"g{n + 1}"
        g["why_open"] = cite(g["why_open"], papers)
        g["supporting_paper_ids"] = [papers[i].id for i in g.pop("supporting_papers") if 0 <= i < len(papers)]
        if v:
            verdict, closest = v
            verdict.explanation = re.sub(r"\s?\[\d+(?:\s*,\s*\d+)*\]", "", verdict.explanation).strip()
            g["scores"]["novelty"] = {"score": verdict.novelty, "why": verdict.explanation}
            g["novelty_check"] = {"status": verdict.status, "explanation": verdict.explanation, "closest": closest}
        else:
            g["novelty_check"] = {"status": "unchecked", "explanation": "Novelty check failed.", "closest": []}
        g["overall"] = _overall(g["scores"])
        if g["novelty_check"]["status"] == "already_done":
            g["overall"] = round(g["overall"] - 1.5, 2)
        results.append(g)
    results.sort(key=lambda g: g["overall"], reverse=True)
    recommended = next((g["id"] for g in results if g["novelty_check"]["status"] != "already_done"), results[0]["id"])
    h.note("Gap analysis complete")
    return {"gaps": results, "recommended": recommended, "feedback": feedback}


def choose(project_id: str, gap_id: str) -> Project:
    """Record the chosen gap from the latest gaps run and advance to Plan."""
    with Session(engine) as s:
        run = s.exec(
            select(Run)
            .where(Run.project_id == project_id, Run.kind == "gaps", Run.status == "done")
            .order_by(Run.started_at.desc())
        ).first()
        if not run:
            raise LookupError("No completed gap analysis")
        gap = next((g for g in run.result["gaps"] if g["id"] == gap_id), None)
        if gap is None:
            raise LookupError(f"Unknown gap {gap_id}")
        project = s.get(Project, project_id)
        project.chosen_gap = {**gap, "run_id": run.id}
        project.stage = "plan"
        s.add(project)
        s.commit()
        s.refresh(project)
        return project
