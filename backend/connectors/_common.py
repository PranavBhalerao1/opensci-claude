"""HTTP helpers shared by every connector, ready-made or forged."""

import asyncio
import json
import logging
import os
from typing import Any

import httpx

# One line per request is noise on an MCP server's stderr.
logging.getLogger("httpx").setLevel(logging.WARNING)

USER_AGENT = "OpenScientist-Connectors/0.1 (+https://www.theopenscientist.com)"
TIMEOUT = httpx.Timeout(60.0, connect=15.0)
RETRIES = 3
MAX_CHARS = 20_000  # keep tool results small enough for a model's context


async def request(method: str, url: str, *, params: dict | None = None, json_body: Any = None,
                  headers: dict | None = None, text: bool = False) -> Any:
    """One HTTP call. Returns parsed JSON (or text), raising a readable error on failure."""
    params = {k: v for k, v in (params or {}).items() if v is not None}
    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT, **(headers or {})},
                                 follow_redirects=True) as http:
        for attempt in range(RETRIES + 1):
            resp = await http.request(method, url, params=params, json=json_body)
            # Public databases rate-limit bursts (Ensembl: 15/s, NCBI: 3/s): wait and retry.
            if resp.status_code not in (429, 500, 502, 503, 504) or attempt == RETRIES:
                break
            await asyncio.sleep(float(resp.headers.get("retry-after") or 0) or 1.5 * (attempt + 1))
    if resp.status_code >= 400:
        raise RuntimeError(f"{method} {resp.url} → HTTP {resp.status_code}: {resp.text[:400]}")
    if text:
        return resp.text
    try:
        return resp.json()
    except json.JSONDecodeError:
        return resp.text


def auth_headers(header: str | None, env_var: str | None, prefix: str = "") -> dict:
    """A credential header read from the environment, so keys never live in connector code."""
    if not header or not env_var:
        return {}
    value = os.environ.get(env_var)
    if not value:
        raise RuntimeError(f"Set {env_var} to use this connector.")
    return {header: f"{prefix}{value}"}


def clip(value: Any) -> Any:
    """Truncate an oversized result, keeping it valid to return."""
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    if len(s) <= MAX_CHARS:
        return value
    return s[:MAX_CHARS] + f"\n… [{len(s) - MAX_CHARS:,} more characters truncated]"
