import httpx

from ..config import settings
from .common import PaperRecord, RateLimiter, request_json

BASE = "https://api.semanticscholar.org/graph/v1"
FIELDS = "paperId,externalIds,title,abstract,year,venue,citationCount,authors,tldr,openAccessPdf,url"
# The references/citations endpoints reject tldr and openAccessPdf.
EDGE_FIELDS = "paperId,externalIds,title,abstract,year,venue,citationCount,authors,url"
# Keyed access is 1 request/second; shared keyless access is far stricter.
_limiter = RateLimiter(1.1 if settings.semantic_scholar_api_key else 3.0)


def _headers() -> dict:
    return {"x-api-key": settings.semantic_scholar_api_key} if settings.semantic_scholar_api_key else {}


def _record(d: dict) -> PaperRecord | None:
    if not d or not d.get("title"):
        return None
    ext = d.get("externalIds") or {}
    return PaperRecord(
        title=d["title"],
        abstract=d.get("abstract"),
        year=d.get("year"),
        venue=d.get("venue") or None,
        authors=[a["name"] for a in d.get("authors") or [] if a.get("name")][:12],
        citation_count=d.get("citationCount") or 0,
        doi=ext.get("DOI"),
        arxiv_id=ext.get("ArXiv"),
        s2_id=d.get("paperId"),
        tldr=(d.get("tldr") or {}).get("text"),
        url=d.get("url"),
        pdf_url=(d.get("openAccessPdf") or {}).get("url") or None,
        source="semantic_scholar",
    )


async def search(client: httpx.AsyncClient, query: str, limit: int = 50) -> list[PaperRecord]:
    data = await request_json(
        client,
        "GET",
        f"{BASE}/paper/search",
        limiter=_limiter,
        params={"query": query, "limit": min(limit, 100), "fields": FIELDS},
        headers=_headers(),
    )
    return [r for d in data.get("data") or [] if (r := _record(d))]


async def neighbours(client: httpx.AsyncClient, paper_id: str, limit: int = 40) -> list[PaperRecord]:
    """Papers this one cites plus papers citing it (one hop)."""
    out: list[PaperRecord] = []
    for edge, key in (("references", "citedPaper"), ("citations", "citingPaper")):
        data = await request_json(
            client,
            "GET",
            f"{BASE}/paper/{paper_id}/{edge}",
            limiter=_limiter,
            params={"limit": limit, "fields": EDGE_FIELDS},
            headers=_headers(),
        )
        out += [r for d in data.get("data") or [] if (r := _record(d.get(key)))]
    return out


async def reference_ids(client: httpx.AsyncClient, paper_ids: list[str]) -> dict[str, list[str]]:
    """paperId -> ids of the papers it references, via the batch endpoint."""
    result: dict[str, list[str]] = {}
    for i in range(0, len(paper_ids), 100):
        chunk = paper_ids[i : i + 100]
        data = await request_json(
            client,
            "POST",
            f"{BASE}/paper/batch",
            limiter=_limiter,
            params={"fields": "references.paperId"},
            json={"ids": chunk},
            headers=_headers(),
        )
        for pid, d in zip(chunk, data):
            if d:
                result[pid] = [r["paperId"] for r in d.get("references") or [] if r.get("paperId")]
    return result
