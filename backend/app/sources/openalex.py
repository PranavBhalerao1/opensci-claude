import httpx

from ..config import settings
from .common import PaperRecord, RateLimiter, request_json

BASE = "https://api.openalex.org"
SELECT = "id,doi,title,publication_year,cited_by_count,abstract_inverted_index,primary_location,ids,authorships"
_limiter = RateLimiter(0.15)


def _abstract(inverted: dict | None) -> str | None:
    if not inverted:
        return None
    positions = sorted((i, word) for word, idxs in inverted.items() for i in idxs)
    return " ".join(w for _, w in positions) or None


def _record(d: dict) -> PaperRecord | None:
    if not d.get("title"):
        return None
    loc = d.get("primary_location") or {}
    ids = d.get("ids") or {}
    arxiv = None
    if "arxiv" in (ids.get("arxiv") or ""):
        arxiv = ids["arxiv"].rsplit("/", 1)[-1]
    return PaperRecord(
        title=d["title"],
        abstract=_abstract(d.get("abstract_inverted_index")),
        year=d.get("publication_year"),
        venue=((loc.get("source") or {}).get("display_name")),
        authors=[a["author"]["display_name"] for a in d.get("authorships") or [] if a.get("author")][:12],
        citation_count=d.get("cited_by_count") or 0,
        doi=d.get("doi"),
        arxiv_id=arxiv,
        openalex_id=d["id"].rsplit("/", 1)[-1],
        url=loc.get("landing_page_url") or d.get("doi"),
        pdf_url=loc.get("pdf_url"),
        source="openalex",
    )


async def search(client: httpx.AsyncClient, query: str, limit: int = 50) -> list[PaperRecord]:
    params = {
        "filter": f"title_and_abstract.search:{query.replace(',', ' ')}",
        "per_page": min(limit, 100),
        "select": SELECT,
    }
    if settings.openalex_api_key:
        params["api_key"] = settings.openalex_api_key
    data = await request_json(client, "GET", f"{BASE}/works", limiter=_limiter, params=params)
    return [r for d in data.get("results") or [] if (r := _record(d))]
