"""Tool registry: what agents can do, with JSON schemas for function calling.

Each tool declares the runtime capabilities it needs; the Blueprint Agent only
assigns tools the current sandbox can provide. `web_search` is OpenAI's hosted
tool; everything else runs here.
"""

import asyncio
import ipaddress
import json
import re
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

from ..sources.common import norm_title
from . import catalog
from .sandbox import MIN_FREE_BYTES, Sandbox

MAX_RESPONSE_CHARS = 12_000
MAX_DOWNLOAD_BYTES = 1024**3  # local disk is small; cloud runners can raise this


@dataclass
class ToolContext:
    project_id: str
    sandbox: Sandbox
    http: httpx.AsyncClient
    agent_name: str = "agent"
    cell: int = 0
    result: dict | None = None  # set by report_result
    # Set by request_credential when the user must supply a key; ends the agent's turn.
    credential_request: dict | None = None
    # Runs sub-agents in parallel; provided by the orchestrator (absent for sub-agents).
    spawn: Callable[[list[dict]], Awaitable[list[dict]]] | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    requires: tuple[str, ...]
    handler: Callable[[ToolContext, dict], Awaitable[str]] | None  # None for hosted tools

    def spec(self) -> dict:
        if self.handler is None:
            return {"type": self.name}
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "strict": False,
        }


def _obj(props: dict, required: list[str]) -> dict:
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


# ── Handlers ───────────────────────────────────────────────────────────────


async def _run_python(ctx: ToolContext, a: dict) -> str:
    ctx.cell += 1
    path = ctx.sandbox.path(f".scratch/cell_{ctx.cell:03d}.py")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(a["code"])
    timeout = min(int(a.get("timeout_seconds", 300)), 3600)
    res = await ctx.sandbox.run([str(ctx.sandbox.python), str(path)], timeout)
    return res.render()


async def _run_shell(ctx: ToolContext, a: dict) -> str:
    timeout = min(int(a.get("timeout_seconds", 120)), 3600)
    return (await ctx.sandbox.run(["/bin/bash", "-c", a["command"]], timeout)).render()


async def _write_file(ctx: ToolContext, a: dict) -> str:
    p = ctx.sandbox.path(a["path"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(a["content"])
    return f"Wrote {len(a['content'])} chars to {a['path']}"


async def _read_file(ctx: ToolContext, a: dict) -> str:
    p = ctx.sandbox.path(a["path"])
    if not p.is_file():
        return f"No such file: {a['path']}"
    text = p.read_text(errors="replace")
    limit = min(int(a.get("max_chars", 8000)), 40_000)
    return text[:limit] + (f"\n… [{len(text) - limit} more chars]" if len(text) > limit else "")


async def _list_files(ctx: ToolContext, a: dict) -> str:
    base = ctx.sandbox.path(a.get("path", "."))
    if not base.exists():
        return f"No such directory: {a.get('path', '.')}"
    rows = []
    for p in sorted(base.rglob("*")):
        rel = p.relative_to(ctx.sandbox.root)
        if any(part.startswith(".") for part in rel.parts):
            continue  # hide .venv, .scratch, .tmp
        if len(rel.parts) - len(base.relative_to(ctx.sandbox.root).parts) > int(a.get("depth", 3)):
            continue
        rows.append(f"{rel}{'/' if p.is_dir() else f'  ({p.stat().st_size:,} B)'}")
        if len(rows) >= 300:
            rows.append("… truncated")
            break
    return "\n".join(rows) or "(empty)"


async def _edit_file(ctx: ToolContext, a: dict) -> str:
    p = ctx.sandbox.path(a["path"])
    if not p.is_file():
        return f"No such file: {a['path']}"
    text = p.read_text()
    count = text.count(a["old"])
    if count != 1:
        return f"'old' must match exactly once; it matched {count} times. Include more surrounding context."
    p.write_text(text.replace(a["old"], a["new"], 1))
    return f"Edited {a['path']}"


async def _install(ctx: ToolContext, a: dict) -> str:
    return (await ctx.sandbox.install(list(a["packages"]))).render()


async def _install_conda(ctx: ToolContext, a: dict) -> str:
    res = await ctx.sandbox.install_conda(list(a["packages"]), list(a.get("channels") or ["conda-forge"]))
    return res.render() + ("\nBinaries are on PATH in run_shell/run_python/start_process." if res.exit_code == 0 else "")


async def _start_process(ctx: ToolContext, a: dict) -> str:
    return await ctx.sandbox.spawn(a["name"], a["command"])


async def _check_process(ctx: ToolContext, a: dict) -> str:
    return ctx.sandbox.status(a["name"], min(int(a.get("tail_lines", 30)), 200))


async def _stop_process(ctx: ToolContext, a: dict) -> str:
    return ctx.sandbox.stop(a["name"])


async def _wait(ctx: ToolContext, a: dict) -> str:
    seconds = max(1, min(int(a["seconds"]), 600))
    await asyncio.sleep(seconds)
    return f"Waited {seconds}s"


class _TextExtractor(HTMLParser):
    """Readable text from HTML: drops scripts/styles/nav chrome, keeps links and code."""

    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header"}
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "section", "article", "table"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")
        if tag == "a" and not self.skip:
            href = dict(attrs).get("href")
            if href and href.startswith("http"):
                self.parts.append(f" [{href}] ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


async def _read_webpage(ctx: ToolContext, a: dict) -> str:
    resp = await _request(ctx, "GET", a["url"], timeout=60)
    ctype = resp.headers.get("content-type", "")
    if "html" not in ctype:
        text = resp.text
    else:
        ex = _TextExtractor()
        ex.feed(resp.text)
        text = re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", "".join(ex.parts))).strip()
    limit = min(int(a.get("max_chars", 12000)), 40000)
    start = max(0, int(a.get("offset", 0)))
    chunk = text[start:start + limit]
    more = len(text) - start - len(chunk)
    return f"HTTP {resp.status_code} {resp.url}\n{chunk}" + (f"\n… [{more} more chars; call again with offset={start + limit}]" if more > 0 else "")


def _notes_path(ctx: ToolContext):
    return ctx.sandbox.path("team/NOTES.md")


async def _post_note(ctx: ToolContext, a: dict) -> str:
    p = _notes_path(ctx)
    p.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%H:%M")
    with p.open("a") as f:
        f.write(f"\n- [{stamp}] **{ctx.agent_name}**: {a['text'].strip()}\n")
    return "Posted to team/NOTES.md"


async def _read_notes(ctx: ToolContext, a: dict) -> str:
    p = _notes_path(ctx)
    return p.read_text()[-12000:] if p.exists() else "No team notes yet."


async def _request_credential(ctx: ToolContext, a: dict) -> str:
    name = a["env_var"].strip().upper()
    if not re.match(r"^[A-Z][A-Z0-9_]{1,63}$", name):
        return "env_var must look like SOME_API_KEY"
    if name in ctx.sandbox.secrets:
        return f"{name} is available as an environment variable in run_shell/run_python/start_process."
    ctx.credential_request = {"env_var": name, "service": a["service"], "reason": a["reason"],
                              "signup_url": a.get("signup_url")}
    return "The user has been asked for this credential. Stop now; the task resumes once it is provided."


async def _spawn_subagents(ctx: ToolContext, a: dict) -> str:
    if ctx.spawn is None:
        return "Sub-agents cannot spawn further sub-agents; do the work yourself."
    subtasks = list(a["subtasks"])[:8]
    if not subtasks:
        return "Give at least one subtask."
    results = await ctx.spawn(subtasks)
    return json.dumps(results, ensure_ascii=False)


def public_url(url: str) -> str:
    """Refuse non-HTTP(S) and private/loopback targets (protects this app and the LAN)."""
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("Only http(s) URLs are allowed")
    for info in socket.getaddrinfo(u.hostname, None):
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError(f"Refusing to contact a private address ({u.hostname})")
    return url


MAX_REDIRECTS = 5


async def _request(ctx: ToolContext, method: str, url: str, **kwargs) -> httpx.Response:
    """Follow redirects by hand so every hop passes the private-address check."""
    for _ in range(MAX_REDIRECTS + 1):
        resp = await ctx.http.request(method, public_url(url), follow_redirects=False, **kwargs)
        if not resp.is_redirect:
            return resp
        url = str(resp.next_request.url) if resp.next_request else resp.headers["location"]
        method, kwargs = "GET", {"timeout": kwargs.get("timeout", 60)}
    raise ValueError("Too many redirects")


async def _http_request(ctx: ToolContext, a: dict) -> str:
    resp = await _request(
        ctx,
        a.get("method", "GET").upper(),
        a["url"],
        params=a.get("params"),
        headers=a.get("headers"),
        json=a.get("json_body"),
        data=a.get("form_body"),
        timeout=60,
    )
    if save := a.get("save_to"):
        p = ctx.sandbox.path(save)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(resp.content)
        return f"HTTP {resp.status_code}; saved {len(resp.content):,} bytes to {save}"
    body = resp.text
    if len(body) > MAX_RESPONSE_CHARS:
        body = body[:MAX_RESPONSE_CHARS] + f"\n… [{len(body) - MAX_RESPONSE_CHARS} more chars; use save_to]"
    return f"HTTP {resp.status_code} {resp.headers.get('content-type', '')}\n{body}"


async def _download(ctx: ToolContext, a: dict) -> str:
    # Resolve redirects (each hop checked) before streaming the final URL.
    head = await _request(ctx, "HEAD", a["url"], timeout=60)
    url = public_url(str(head.url))
    dest = ctx.sandbox.path(a["path"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    async with ctx.http.stream("GET", url, follow_redirects=False, timeout=120) as resp:
        if resp.status_code != 200:
            return f"HTTP {resp.status_code}; nothing saved"
        declared = int(resp.headers.get("content-length") or 0)
        if declared > MAX_DOWNLOAD_BYTES or ctx.sandbox.free_bytes() - declared < MIN_FREE_BYTES:
            return f"Refused: {declared:,} bytes exceeds the local download or disk limit"
        with dest.open("wb") as f:
            async for chunk in resp.aiter_bytes(1 << 20):
                size += len(chunk)
                if size > MAX_DOWNLOAD_BYTES:
                    f.close()
                    dest.unlink(missing_ok=True)
                    return "Refused: download exceeded the 1 GB local limit"
                f.write(chunk)
    return f"Saved {size:,} bytes to {a['path']}"


async def _search_papers(ctx: ToolContext, a: dict) -> str:
    from ..agents.literature import cached_search  # avoid import cycle at module load

    records = await cached_search(ctx.http, "s2", a["query"], min(int(a.get("limit", 10)), 25))
    seen, rows = set(), []
    for r in records:
        if norm_title(r.title) in seen:
            continue
        seen.add(norm_title(r.title))
        rows.append({"title": r.title, "year": r.year, "venue": r.venue, "citations": r.citation_count,
                     "doi": r.doi, "url": r.url, "abstract": (r.abstract or r.tldr or "")[:600]})
    return json.dumps(rows, ensure_ascii=False)


async def _lookup_resources(ctx: ToolContext, a: dict) -> str:
    found = catalog.search(a["query"], int(a.get("limit", 6)))
    return json.dumps(found, ensure_ascii=False) if found else "No catalog match; try web_search."


async def _report_result(ctx: ToolContext, a: dict) -> str:
    missing = [p for p in a.get("artifacts", []) if not ctx.sandbox.path(p).exists()]
    if missing:
        return f"These artifacts do not exist yet: {', '.join(missing)}. Create them or remove them, then report again."
    ctx.result = a
    return "Result recorded."


# ── Registry ───────────────────────────────────────────────────────────────

_TIMEOUT = {"type": "integer", "description": "Seconds before the process is killed (default 300, max 3600)"}

TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool("run_python", "Run a Python script in the project workspace (cwd). Files persist between calls; "
             "print what you need to see. Use matplotlib with savefig for figures.",
             _obj({"code": {"type": "string"}, "timeout_seconds": _TIMEOUT}, ["code"]), ("python",), _run_python),
        Tool("run_shell", "Run a bash command in the project workspace.",
             _obj({"command": {"type": "string"}, "timeout_seconds": _TIMEOUT}, ["command"]), ("shell",), _run_shell),
        Tool("write_file", "Create or overwrite a text file in the workspace.",
             _obj({"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
             ("files",), _write_file),
        Tool("read_file", "Read a text file from the workspace.",
             _obj({"path": {"type": "string"}, "max_chars": {"type": "integer"}}, ["path"]), ("files",), _read_file),
        Tool("list_files", "List workspace files (hidden dirs excluded).",
             _obj({"path": {"type": "string"}, "depth": {"type": "integer"}}, []), ("files",), _list_files),
        Tool("edit_file", "Replace one exact snippet in a text file (for code edits without rewriting the file).",
             _obj({"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}},
                  ["path", "old", "new"]), ("files",), _edit_file),
        Tool("install_packages", "pip-install packages into the workspace environment, e.g. ['biopython', 'rdkit'].",
             _obj({"packages": {"type": "array", "items": {"type": "string"}}}, ["packages"]), ("python",), _install),
        Tool("install_conda_packages", "Install non-pip scientific software from conda-forge/bioconda (binaries and "
             "libraries, e.g. openbabel, autodock-vina, gromacs, blast, fenics). Slower; prefer pip when available.",
             _obj({"packages": {"type": "array", "items": {"type": "string"}},
                   "channels": {"type": "array", "items": {"type": "string",
                                "enum": ["conda-forge", "bioconda", "pytorch", "defaults"]}}}, ["packages"]),
             ("conda",), _install_conda),
        Tool("start_process", "Start a long-running command in the background (training, simulations, local "
             "servers). Returns immediately; poll with check_process.",
             _obj({"name": {"type": "string", "description": "Short id, e.g. train_baseline"},
                   "command": {"type": "string", "description": "bash command run in the workspace"}},
                  ["name", "command"]), ("background",), _start_process),
        Tool("check_process", "Status and recent log lines of a background process.",
             _obj({"name": {"type": "string"}, "tail_lines": {"type": "integer"}}, ["name"]),
             ("background",), _check_process),
        Tool("stop_process", "Stop a background process.", _obj({"name": {"type": "string"}}, ["name"]),
             ("background",), _stop_process),
        Tool("wait", "Pause for up to 600 s (while a background process or remote job runs).",
             _obj({"seconds": {"type": "integer"}}, ["seconds"]), (), _wait),
        Tool("read_webpage", "Fetch a web page (e.g. API documentation, a server's help page) as readable text. "
             "Use offset to page through long documents.",
             _obj({"url": {"type": "string"}, "max_chars": {"type": "integer"}, "offset": {"type": "integer"}},
                  ["url"]), ("internet",), _read_webpage),
        Tool("post_note", "Share a finding with the rest of the team (API quirks, data caveats, decisions).",
             _obj({"text": {"type": "string"}}, ["text"]), ("files",), _post_note),
        Tool("read_notes", "Read what other agents have shared.", _obj({}, []), ("files",), _read_notes),
        Tool("request_credential", "Ask the user for an API key or account token a service requires. The key "
             "becomes an environment variable. Use only after confirming the service truly needs one.",
             _obj({"env_var": {"type": "string", "description": "e.g. NCBI_API_KEY"},
                   "service": {"type": "string"}, "reason": {"type": "string"},
                   "signup_url": {"type": "string"}}, ["env_var", "service", "reason"]), (), _request_credential),
        Tool("spawn_subagents", "Run up to 8 sub-agents in parallel for independent pieces of your task "
             "(e.g. one training run per configuration, one docking run per ligand). Each gets your tools except "
             "this one, works in the same workspace, and returns its summary and artifacts.",
             _obj({"subtasks": {"type": "array", "items": _obj({
                 "name": {"type": "string"},
                 "instructions": {"type": "string", "description": "Complete, self-contained instructions"},
                 "outputs": {"type": "array", "items": {"type": "string"}},
             }, ["name", "instructions", "outputs"])}}, ["subtasks"]), (), _spawn_subagents),
        Tool("http_request", "Call any public HTTP API (scientific databases, data portals). "
             "Use save_to for large or binary responses.",
             _obj({
                 "method": {"type": "string", "enum": ["GET", "POST"]},
                 "url": {"type": "string"},
                 "params": {"type": "object"},
                 "headers": {"type": "object"},
                 "json_body": {"type": "object"},
                 "form_body": {"type": "object"},
                 "save_to": {"type": "string", "description": "Workspace path to save the body to"},
             }, ["url"]), ("internet",), _http_request),
        Tool("download_file", "Download a file (dataset, archive, PDF) into the workspace (≤1 GB locally).",
             _obj({"url": {"type": "string"}, "path": {"type": "string"}}, ["url", "path"]),
             ("internet",), _download),
        Tool("search_papers", "Search the scientific literature (Semantic Scholar).",
             _obj({"query": {"type": "string"}, "limit": {"type": "integer"}}, ["query"]),
             ("internet",), _search_papers),
        Tool("lookup_resources", "Hints from a small catalog of scientific APIs, data repositories and software "
             "(e.g. 'protein structure', 'building energy'). It is NOT exhaustive: use web_search and read_webpage "
             "to find and learn any other service or tool.",
             _obj({"query": {"type": "string"}, "limit": {"type": "integer"}}, ["query"]), (), _lookup_resources),
        Tool("web_search", "Search the web (hosted).", {}, ("internet",), None),
        Tool("report_result", "Finish the task: summarise what was done and list the artifacts produced.",
             _obj({
                 "status": {"type": "string", "enum": ["success", "partial", "failed"]},
                 "summary": {"type": "string"},
                 "artifacts": {"type": "array", "items": {"type": "string"}},
                 "metrics": {"type": "object"},
                 "issues": {"type": "array", "items": {"type": "string"}},
             }, ["status", "summary", "artifacts"]), (), _report_result),
    ]
}


def available(capabilities: set[str]) -> list[str]:
    return [name for name, t in TOOLS.items() if set(t.requires) <= capabilities]


def specs(names: list[str]) -> list[dict]:
    return [TOOLS[n].spec() for n in names if n in TOOLS]


def describe(capabilities: set[str]) -> str:
    """Tool list for prompts, marking tools the current runtime cannot provide."""
    return "\n".join(
        f"- {t.name}: {t.description}" + ("" if set(t.requires) <= capabilities else " (UNAVAILABLE on this runtime)")
        for t in TOOLS.values()
    )
