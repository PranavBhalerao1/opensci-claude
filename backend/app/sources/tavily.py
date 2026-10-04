"""Tavily web search: the backend of the agents' web_search tool."""

import httpx

from ..config import settings
from .common import RateLimiter, request_json

URL = "https://api.tavily.com/search"
MAX_RESULTS = 5
_limiter = RateLimiter(0.1)


async def search(client: httpx.AsyncClient, query: str, limit: int = MAX_RESULTS) -> list[dict]:
    """Top web results for a query as {title, url, content} (content is a page snippet)."""
    if not settings.tavily_api_key:
        raise RuntimeError("Web search is not configured (no TAVILY_API_KEY)")
    data = await request_json(
        client, "POST", URL, limiter=_limiter, timeout=60,
        headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
        json={"query": query, "max_results": limit},
    )
    return [{"title": r.get("title"), "url": r.get("url"), "content": r.get("content")}
            for r in data.get("results") or []]
