"""Stage 2 · Literature review.

search (Semantic Scholar, OpenAlex fallback) → merge & pre-rank → screen (bulk
model) → optional citation hop (deep) → extract notes (standard model, cached
globally) → fetch references for the citation graph → overview.
"""

import asyncio
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Literal

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlmodel import Session, delete, select

from ..config import settings
from ..db import Paper, Project, ProjectPaper, SearchCache, engine
from ..jobs import RunHandle
from ..llm import parse
from ..sources import openalex, semantic_scholar
from ..sources.common import PaperRecord, norm_doi, norm_title

SEARCH_CACHE_TTL = timedelta(days=7)
SCREEN_BATCH = 25
LLM_CONCURRENCY = 8
ABSTRACT_CHARS = 1500


# ── Schemas ────────────────────────────────────────────────────────────────


class Screened(BaseModel):
    i: int = Field(description="Index of the paper in the list")
    relevance: int = Field(description="0 unrelated, 1 tangential, 2 relevant, 3 central")
    reason: str = Field(description="Max 15 words")


class ScreenBatch(BaseModel):
    results: list[Screened]


class PaperNotes(BaseModel):
    contribution: str = Field(description="The paper's main contribution, one sentence")
    problem: str = Field(description="Problem or question addressed, one sentence")
    study_type: Literal["empirical", "method", "dataset", "benchmark", "theory", "review", "other"]
    methods: list[str] = Field(description="Canonical short names of methods/models used or proposed")
    datasets: list[str] = Field(description="Canonical names of datasets or data sources")
    tasks: list[str] = Field(description="Tasks or phenomena studied, short noun phrases")
    metrics: list[str]
    key_findings: list[str] = Field(description="1-3 findings, with numbers if the text gives them")
    limitations: list[str] = Field(description="Stated or clearly evident limitations; [] if none")


class Theme(BaseModel):
    name: str
    description: str = Field(description="2-3 sentences")
    papers: list[int] = Field(description="Indices of papers in this theme")


class Overview(BaseModel):
    summary: str = Field(description="State of the field in 2 short paragraphs of markdown, plain language")
    themes: list[Theme] = Field(description="3-7 themes")
    common_methods: list[str]
    common_datasets: list[str]
    open_problems: list[str] = Field(description="Recurring limitations or unanswered questions, 3-8 items")


SCREEN_INSTRUCTIONS = """\
You screen papers for a literature review. Rate each paper's relevance to the
research brief: 3 = directly addresses the core question or its key methods/data;
2 = clearly useful background, methods or data; 1 = tangential; 0 = unrelated.
Rate every paper in the list exactly once."""

EXTRACT_INSTRUCTIONS = """\
Extract structured notes from this paper's title and abstract. Only use what the
text supports; never invent numbers. Use short canonical names (e.g. "ESM-2",
"random forest", "ProteinGym") so notes from different papers can be linked."""

OVERVIEW_INSTRUCTIONS = """\
You write the literature overview for a research project, for a smart non-expert.
Group the papers into themes, and surface recurring limitations and open problems
— they are where research gaps hide. Refer to papers only by their [index]."""


# ── Helpers ────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _merge(into: PaperRecord, other: PaperRecord) -> None:
    for f in ("abstract", "tldr", "year", "venue", "doi", "arxiv_id", "s2_id", "openalex_id", "url", "pdf_url"):
        if not getattr(into, f) and getattr(other, f):
            setattr(into, f, getattr(other, f))
    if other.abstract and len(other.abstract) > len(into.abstract or ""):
        into.abstract = other.abstract
    into.citation_count = max(into.citation_count, other.citation_count)
    if not into.authors:
        into.authors = other.authors


class Pool:
    """Deduplicates records from many queries/sources and accumulates rank scores."""

    def __init__(self) -> None:
        self.records: list[PaperRecord] = []
        self.scores: list[float] = []
        self._keys: dict[str, int] = {}

    @staticmethod
    def _keys_for(r: PaperRecord) -> list[str]:
        keys = [f"t:{norm_title(r.title)}"]
        if d := norm_doi(r.doi):
            keys.append(f"doi:{d}")
        if r.s2_id:
            keys.append(f"s2:{r.s2_id}")
        if r.arxiv_id:
            keys.append(f"arxiv:{r.arxiv_id.lower()}")
        return keys

    def add(self, r: PaperRecord, score: float) -> int:
        keys = self._keys_for(r)
        idx = next((self._keys[k] for k in keys if k in self._keys), None)
        if idx is None:
            idx = len(self.records)
            self.records.append(r)
            self.scores.append(0.0)
        else:
            _merge(self.records[idx], r)
        self.scores[idx] += score
        for k in self._keys_for(self.records[idx]):
            self._keys[k] = idx
        return idx

    def prescore(self, idx: int) -> float:
        r = self.records[idx]
        return self.scores[idx] + 0.004 * math.log1p(r.citation_count)


def _upsert(session: Session, r: PaperRecord) -> Paper:
    """Find the cached Paper for a record (any shared identifier) or create it."""
    doi = norm_doi(r.doi)
    conds = [Paper.norm_title == norm_title(r.title)]
    if doi:
        conds.append(Paper.doi == doi)
    if r.s2_id:
        conds.append(Paper.s2_id == r.s2_id)
    paper = session.exec(select(Paper).where(or_(*conds))).first()
    if paper is None:
        paper = Paper(title=r.title, norm_title=norm_title(r.title))
    for f in ("abstract", "tldr", "year", "venue", "arxiv_id", "s2_id", "openalex_id", "url", "pdf_url"):
        if getattr(r, f) and not getattr(paper, f):
            setattr(paper, f, getattr(r, f))
    if r.abstract and len(r.abstract) > len(paper.abstract or ""):
        paper.abstract = r.abstract
    paper.doi = paper.doi or doi
    paper.authors = paper.authors or r.authors
    paper.citation_count = max(paper.citation_count, r.citation_count)
    paper.updated_at = _now()
    session.add(paper)
    return paper


def _record_from_paper(p: Paper) -> PaperRecord:
    return PaperRecord(
        title=p.title, abstract=p.abstract, year=p.year, venue=p.venue, authors=p.authors,
        citation_count=p.citation_count, doi=p.doi, arxiv_id=p.arxiv_id, s2_id=p.s2_id,
        openalex_id=p.openalex_id, tldr=p.tldr, url=p.url, pdf_url=p.pdf_url, source="cache",
    )


async def cached_search(client, source: str, query: str, limit: int) -> list[PaperRecord]:
    key = f"{source}:{norm_title(query)}:{limit}"
    with Session(engine) as s:
        hit = s.get(SearchCache, key)
        if hit and hit.fetched_at.replace(tzinfo=timezone.utc) > _now() - SEARCH_CACHE_TTL:
            papers = {p.id: p for p in s.exec(select(Paper).where(Paper.id.in_(hit.paper_ids)))}
            return [_record_from_paper(papers[i]) for i in hit.paper_ids if i in papers]

    mod = semantic_scholar if source == "s2" else openalex
    records = await mod.search(client, query, limit)
    with Session(engine) as s:
        ids = [_upsert(s, r).id for r in records]
        s.merge(SearchCache(key=key, paper_ids=ids, fetched_at=_now()))
        s.commit()
    return records


def _paper_line(i: int, r: PaperRecord) -> str:
    text = (r.abstract or r.tldr or "").strip().replace("\n", " ")[:ABSTRACT_CHARS]
    return f"[{i}] {r.title} ({r.year or 'n.d.'})\n{text or '(no abstract)'}"


def brief_context(brief: dict) -> str:
    return (
        f"Core question: {brief['core_question']}\n"
        f"Summary: {brief['summary']}\n"
        f"In scope: {'; '.join(brief['scope_in'])}\n"
        f"Out of scope: {'; '.join(brief['scope_out'])}"
    )


async def _gather_limited(coros, limit: int):
    sem = asyncio.Semaphore(limit)

    async def one(c):
        async with sem:
            return await c

    return await asyncio.gather(*(one(c) for c in coros), return_exceptions=True)


async def _screen(brief: dict, records: list[tuple[int, PaperRecord]]) -> dict[int, Screened]:
    """Screen (pool_idx, record) pairs in batches; returns pool_idx -> result."""
    batches = [records[i : i + SCREEN_BATCH] for i in range(0, len(records), SCREEN_BATCH)]

    async def run(batch):
        listing = "\n\n".join(_paper_line(j, r) for j, (_, r) in enumerate(batch))
        out = await parse(
            model=settings.model_bulk,
            instructions=SCREEN_INSTRUCTIONS,
            messages=[{"role": "user", "content": f"{brief_context(brief)}\n\nPapers:\n\n{listing}"}],
            schema=ScreenBatch,
            reasoning_effort="low",
        )
        return {batch[x.i][0]: x for x in out.results if 0 <= x.i < len(batch)}

    merged: dict[int, Screened] = {}
    for res in await _gather_limited([run(b) for b in batches], LLM_CONCURRENCY):
        if isinstance(res, dict):
            merged.update(res)
    return merged


async def _extract(paper: Paper) -> PaperNotes:
    text = f"Title: {paper.title}\nYear: {paper.year}\nVenue: {paper.venue}\n\nAbstract:\n{paper.abstract or paper.tldr}"
    return await parse(
        model=settings.model_standard,
        instructions=EXTRACT_INSTRUCTIONS,
        messages=[{"role": "user", "content": text}],
        schema=PaperNotes,
        reasoning_effort="low",
    )


def cite(text: str, papers: list[Paper]) -> str:
    """Turn the model's [3, 7] index references into readable (Author Year) citations."""

    def short(i: int) -> str | None:
        if not 0 <= i < len(papers):
            return None
        p = papers[i]
        surname = p.authors[0].split()[-1] if p.authors else p.title.split()[0]
        return f"{surname}{' et al.' if len(p.authors) > 1 else ''} {p.year or 'n.d.'}"

    def repl(m: re.Match) -> str:
        cites = [c for n in re.findall(r"\d+", m.group(1)) if (c := short(int(n)))]
        return f"({'; '.join(cites)})" if cites else ""

    return re.sub(r"\s?\[(\d+(?:\s*[,–-]\s*\d+)*)\]", lambda m: " " + repl(m) if repl(m) else "", text).strip()


# ── Job ────────────────────────────────────────────────────────────────────


async def run(project_id: str, h: RunHandle) -> dict:
    with Session(engine) as s:
        project = s.get(Project, project_id)
        brief, cfg = project.brief, project.settings
        s.exec(delete(ProjectPaper).where(ProjectPaper.project_id == project_id))
        s.commit()
    if not brief:
        raise RuntimeError("No research brief")

    target = int(cfg.get("max_papers", 100))
    hops = int(cfg.get("citation_hops", 0))
    per_query = 25 if target <= 30 else 50 if target <= 100 else 100
    queries = list(dict.fromkeys(brief["search_keywords"]))[:15]

    pool = Pool()
    async with httpx.AsyncClient(timeout=40) as client:
        # 1 · Search
        h.phase("searching", f"Searching {len(queries)} queries on Semantic Scholar")
        failed: list[str] = []
        for n, q in enumerate(queries, 1):
            try:
                results = await cached_search(client, "s2", q, per_query)
            except Exception as exc:
                h.note(f"Semantic Scholar failed for “{q}” ({type(exc).__name__}); will try OpenAlex")
                failed.append(q)
                continue
            for rank, r in enumerate(results):
                pool.add(r, 1 / (60 + rank))
            h.counts(queries_done=n, queries_total=len(queries), found=len(pool.records))

        oa_queries = failed if not settings.openalex_api_key else queries
        if oa_queries:
            h.note(f"Searching OpenAlex for {len(oa_queries)} queries")
            for q in oa_queries:
                try:
                    for rank, r in enumerate(await cached_search(client, "openalex", q, per_query)):
                        pool.add(r, 1 / (60 + rank))
                except Exception as exc:
                    h.note(f"OpenAlex failed for “{q}” ({type(exc).__name__})")
            h.counts(found=len(pool.records))
        if not pool.records:
            raise RuntimeError("No papers found — both literature sources failed")

        # 2 · Pre-rank and screen
        readable = [i for i, r in enumerate(pool.records) if r.abstract or r.tldr]
        candidates = sorted(readable, key=pool.prescore, reverse=True)[: min(3 * target, 450)]
        h.phase("screening", f"Found {len(pool.records)} unique papers; screening the top {len(candidates)}")
        h.counts(candidates=len(candidates))
        screened = await _screen(brief, [(i, pool.records[i]) for i in candidates])
        h.counts(screened=len(screened))
        origin = {i: "search" for i in candidates}

        # 3 · Citation hop (deep)
        if hops > 0:
            seeds = sorted(
                (i for i, x in screened.items() if x.relevance >= 3 and pool.records[i].s2_id),
                key=pool.prescore,
                reverse=True,
            )[:8]
            h.phase("expanding", f"Following citations of {len(seeds)} central papers")
            before = len(pool.records)
            for i in seeds:
                try:
                    for r in await semantic_scholar.neighbours(client, pool.records[i].s2_id, 40):
                        pool.add(r, 0.5 / 60)
                except Exception as exc:
                    h.note(f"Citation lookup failed ({type(exc).__name__})")
            new = [i for i in range(before, len(pool.records)) if pool.records[i].abstract]
            h.note(f"Citation hop added {len(new)} new candidates")
            more = await _screen(brief, [(i, pool.records[i]) for i in new])
            screened.update(more)
            origin.update({i: "citation" for i in new})
            h.counts(found=len(pool.records), candidates=len(origin), screened=len(screened))

        ranked = sorted(screened, key=lambda i: (screened[i].relevance, pool.prescore(i)), reverse=True)
        included = [i for i in ranked if screened[i].relevance >= 2][:target]
        h.note(f"{len(included)} papers passed screening")
        h.counts(included=len(included))

        # Persist project papers
        with Session(engine) as s:
            pid_of: dict[int, str] = {}
            for i in origin:
                paper = _upsert(s, pool.records[i])
                pid_of[i] = paper.id
                x = screened.get(i)
                s.add(
                    ProjectPaper(
                        project_id=project_id,
                        paper_id=paper.id,
                        origin=origin[i],
                        score=pool.prescore(i),
                        relevance=x.relevance if x else None,
                        reason=x.reason if x else None,
                        included=i in included,
                    )
                )
            s.commit()
        included_ids = list(dict.fromkeys(pid_of[i] for i in included))

        # 4 · Extract notes (cached across projects)
        with Session(engine) as s:
            todo = list(s.exec(select(Paper).where(Paper.id.in_(included_ids), Paper.notes.is_(None))))
        cached = len(included_ids) - len(todo)
        h.phase("reading", f"Reading {len(todo)} papers" + (f" ({cached} already in the knowledge base)" if cached else ""))
        h.counts(extracted=cached)
        done = cached

        async def extract_one(paper: Paper) -> None:
            nonlocal done
            notes = await _extract(paper)
            with Session(engine) as s:
                p = s.get(Paper, paper.id)
                p.notes = notes.model_dump()
                s.add(p)
                s.commit()
            done += 1
            if done % 5 == 0 or done == len(included_ids):
                h.counts(extracted=done)

        failures = [r for r in await _gather_limited([extract_one(p) for p in todo], LLM_CONCURRENCY) if r]
        h.counts(extracted=done)
        if failures:
            h.note(f"{len(failures)} papers could not be read")

        # 5 · Citation edges for the graph
        with Session(engine) as s:
            need = [p.s2_id for p in s.exec(select(Paper).where(Paper.id.in_(included_ids))) if p.s2_id and p.references is None]
        if need:
            h.phase("linking", f"Linking citations between {len(need)} papers")
            try:
                refs = await semantic_scholar.reference_ids(client, need)
                with Session(engine) as s:
                    for p in s.exec(select(Paper).where(Paper.s2_id.in_(list(refs)))):
                        p.references = refs[p.s2_id]
                        s.add(p)
                    s.commit()
            except Exception as exc:
                h.note(f"Citation linking failed ({type(exc).__name__}); graph will show concepts only")

    # 6 · Overview
    h.phase("synthesising", "Writing the literature overview")
    with Session(engine) as s:
        rows = s.exec(
            select(ProjectPaper, Paper)
            .join(Paper, Paper.id == ProjectPaper.paper_id)
            .where(ProjectPaper.project_id == project_id, ProjectPaper.included)
            .order_by(ProjectPaper.relevance.desc(), ProjectPaper.score.desc())
        ).all()
    top = [(pp, p) for pp, p in rows if p.notes][:80]
    listing = "\n".join(
        f"[{n}] {p.title} ({p.year}) — {p.notes['contribution']} Methods: {', '.join(p.notes['methods'][:4])}. "
        f"Limitations: {'; '.join(p.notes['limitations'][:2]) or 'none stated'}"
        for n, (_, p) in enumerate(top)
    )
    overview = await parse(
        model=settings.model_standard,
        instructions=OVERVIEW_INSTRUCTIONS,
        messages=[{"role": "user", "content": f"{brief_context(brief)}\n\nPapers:\n{listing}"}],
        schema=Overview,
        reasoning_effort="medium",
    )
    result = overview.model_dump()
    cited = [p for _, p in top]
    result["summary"] = cite(result["summary"], cited)
    result["open_problems"] = [cite(o, cited) for o in result["open_problems"]]
    for theme in result["themes"]:
        theme["description"] = cite(theme["description"], cited)
        theme["paper_ids"] = [top[i][1].id for i in theme.pop("papers") if 0 <= i < len(top)]
    h.note("Literature review complete")
    return {"overview": result}
