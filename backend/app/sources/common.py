import asyncio
import re
import time
from dataclasses import dataclass, field

import httpx


@dataclass
class PaperRecord:
    """A paper as returned by any source, before merging."""

    title: str
    abstract: str | None = None
    year: int | None = None
    venue: str | None = None
    authors: list[str] = field(default_factory=list)
    citation_count: int = 0
    doi: str | None = None
    arxiv_id: str | None = None
    s2_id: str | None = None
    openalex_id: str | None = None
    tldr: str | None = None
    url: str | None = None
    pdf_url: str | None = None
    source: str = ""


def norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def norm_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip().lower()) or None


class RateLimiter:
    """Spaces calls at least `interval` seconds apart across all tasks."""

    def __init__(self, interval: float):
        self.interval = interval
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def wait(self) -> None:
        async with self._lock:
            delay = self._last + self.interval - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._last = time.monotonic()


async def request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    limiter: RateLimiter,
    retries: int = 6,
    **kwargs,
):
    """HTTP call with rate limiting and exponential backoff on 429/5xx."""
    backoff = 1.5
    for attempt in range(retries):
        await limiter.wait()
        try:
            resp = await client.request(method, url, **kwargs)
        except httpx.TransportError:
            if attempt == retries - 1:
                raise
        else:
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code not in (429, 500, 502, 503, 504) or attempt == retries - 1:
                resp.raise_for_status()
            retry_after = resp.headers.get("retry-after")
            if retry_after and retry_after.isdigit():
                backoff = max(backoff, float(retry_after))
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 20)
    raise RuntimeError(f"Gave up on {url}")
