"""Connector Forge: build a new MCP connector for any HTTP API or experimentation server.

Give it an OpenAPI spec URL, or the API's base URL and a few endpoints, and it writes a complete
MCP server to connectors/generated/<name>.py — one tool per endpoint, with typed parameters and
credentials read from the environment — then imports it, checks every tool registers, and records
it in connectors/generated/registry.json. A forged connector runs like the ready-made ones:

    uv run --group connectors python -m connectors.generated.<name>

The forge is itself an MCP server (`python -m connectors.forge`), so an agent connected to it can
create, inspect and call connectors on its own. It also has a CLI:

    uv run --group connectors python -m connectors.forge openapi <name> <spec-url> [--max-tools N]
    uv run --group connectors python -m connectors.forge list
    uv run --group connectors python -m connectors.forge call <connector> <tool> '<json args>'

Code is generated from the structured spec only (names are sanitised, text is embedded as
literals), so a spec can never inject code into a connector.
"""

import argparse
import asyncio
import importlib
import importlib.util
import json
import keyword
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from mcp.server.mcpserver import MCPServer

from . import SERVERS
from ._common import request

GENERATED = Path(__file__).resolve().parent / "generated"
REGISTRY = GENERATED / "registry.json"
METHODS = ("get", "post", "put", "patch", "delete")
TYPES = {"string": "str", "integer": "int", "number": "float", "boolean": "bool", "array": "list", "object": "dict"}


# ── Specs ───────────────────────────────────────────────────────────────────


@dataclass
class Param:
    name: str
    location: str  # "path" or "query"
    type: str = "string"
    required: bool = False
    description: str = ""


@dataclass
class Endpoint:
    name: str
    method: str
    path: str
    description: str = ""
    params: list[Param] | None = None
    body: bool = False  # accepts a JSON body


def _ident(text: str, taken: set[str] | None = None) -> str:
    """A safe, unique Python identifier for `text`."""
    s = re.sub(r"[^0-9a-zA-Z_]+", "_", re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)).strip("_").lower() or "x"
    if s[0].isdigit() or keyword.iskeyword(s):
        s = f"p_{s}"
    if taken is not None:
        base, n = s, 2
        while s in taken:
            s, n = f"{base}_{n}", n + 1
        taken.add(s)
    return s


def endpoints_from_openapi(spec: dict, max_tools: int = 30, include: str | None = None) -> tuple[str, list[Endpoint]]:
    """The base URL and endpoints of an OpenAPI 3 / Swagger 2 document (first `max_tools`)."""
    if spec.get("servers"):
        base = spec["servers"][0].get("url", "")
    else:  # Swagger 2
        scheme = (spec.get("schemes") or ["https"])[0]
        host = spec.get("host")
        # No host: the API lives where the spec does (resolved by forge_openapi).
        base = f"{scheme}://{host}{spec.get('basePath', '')}" if host else spec.get("basePath") or ""
    out: list[Endpoint] = []
    # operationIds often repeat across sections (several "getByAccession"s): prefix those with the
    # path's first segment, so each tool's name says what it reads.
    # (Generators often number the repeats themselves: getByAccession, getByAccession_1, …)
    stem = lambda op_id: re.sub(r"_\d+$", "", op_id or "")  # noqa: E731
    ids = [stem(op.get("operationId")) for ops in (spec.get("paths") or {}).values() if isinstance(ops, dict)
           for m, op in ops.items() if m in METHODS and isinstance(op, dict)]
    for path, ops in (spec.get("paths") or {}).items():
        shared = ops.get("parameters", []) if isinstance(ops, dict) else []
        for method in METHODS:
            op = ops.get(method) if isinstance(ops, dict) else None
            if not op or (include and include.lower() not in f"{path} {op.get('summary', '')} {' '.join(op.get('tags', []))}".lower()):
                continue
            params = []
            for p in [*shared, *op.get("parameters", [])]:
                if "$ref" in p or p.get("in") not in ("path", "query"):
                    continue
                schema = p.get("schema") or p
                params.append(Param(p["name"], p["in"], schema.get("type", "string"), bool(p.get("required") or p["in"] == "path"),
                                    (p.get("description") or "")[:200]))
            name = op.get("operationId") or f"{method}_{path}"
            if op.get("operationId") and ids.count(stem(name)) > 1:
                section = next((seg for seg in path.split("/") if seg and not seg.startswith("{")), "")
                name = f"{section}_{stem(name)}"
            desc = (op.get("summary") or op.get("description") or f"{method.upper()} {path}").strip().split("\n")[0][:300]
            body = method in ("post", "put", "patch") and bool(op.get("requestBody") or any(p.get("in") == "body" for p in op.get("parameters", [])))
            out.append(Endpoint(name, method, path, desc, params, body))
            if len(out) >= max_tools:
                return base, out
    return base, out


# ── Code generation ─────────────────────────────────────────────────────────


def _tool_source(ep: Endpoint, taken: set[str]) -> str:
    fn = _ident(ep.name, taken)
    names: set[str] = {"body"}
    required, optional, path_map, query = [], [], {}, []
    for p in ep.params or []:
        ident = _ident(p.name, names)
        annotation = TYPES.get(p.type, "str")
        if p.location == "path":
            path_map[p.name] = ident
        else:
            query.append((p.name, ident))
        if p.required:
            required.append(f"{ident}: {annotation}")
        else:
            optional.append(f"{ident}: {annotation} | None = None")
    # Every {placeholder} in the path becomes a required argument: matched to its declared parameter
    # even when spelt differently ({plate_id} vs "plate-id"), or added when the spec forgot it.
    by_ident = {_ident(raw): ident for raw, ident in path_map.items()}

    def fill(m: re.Match) -> str:
        key = _ident(m.group(1))
        if key not in by_ident:
            by_ident[key] = _ident(m.group(1), names)
            required.append(f"{by_ident[key]}: str")
        return "{_q(" + by_ident[key] + ")}"

    path = re.sub(r"\{([^{}]+)\}", fill, ep.path)
    if ep.body:
        optional.append("body: dict | None = None")
    path = path.replace("\\", "\\\\").replace('"', '\\"')
    doc = ep.description or f"{ep.method.upper()} {ep.path}"
    param_docs = [f"{p.name}: {p.description}" for p in ep.params or [] if p.description]
    if param_docs:
        doc += "\n\n" + "\n".join(param_docs)
    params = "{" + ", ".join(f"{json.dumps(raw)}: {ident}" for raw, ident in query) + "}"
    return (
        f"@server.tool()\n"
        f"async def {fn}({', '.join(required + optional)}) -> Any:\n"
        f"    {json.dumps(doc)}\n"
        f"    return clip(await request({json.dumps(ep.method.upper())}, BASE + f\"{path}\", params={params},\n"
        f"                              json_body={'body' if ep.body else 'None'}, headers=_auth()))\n"
    )


def render(name: str, base_url: str, endpoints: list[Endpoint], description: str = "",
           auth_header: str | None = None, auth_env: str | None = None, auth_prefix: str = "") -> str:
    """The full source of an MCP server for these endpoints."""
    taken: set[str] = set()
    tools = "\n\n".join(_tool_source(ep, taken) for ep in endpoints)
    return (
        f'"""{name}: forged by the OpenScientist Connector Forge on {datetime.now(timezone.utc):%Y-%m-%d}.\n\n'
        f"{description.replace(chr(34) * 3, '')}\n\nBase URL: {base_url}\n"
        + (f"Credentials: set {auth_env}.\n" if auth_env else "")
        + '"""\n\n'
        "from typing import Any\nfrom urllib.parse import quote\n\n"
        "from mcp.server.mcpserver import MCPServer\n\n"
        "from connectors._common import auth_headers, clip, request\n\n"
        f"BASE = {json.dumps(base_url.rstrip('/'))}\n"
        f"server = MCPServer({json.dumps(name)}, instructions={json.dumps(description or name)})\n\n\n"
        "def _q(value: Any) -> str:\n    return quote(str(value), safe=\"\")\n\n\n"
        f"def _auth() -> dict:\n    return auth_headers({auth_header!r}, {auth_env!r}, {auth_prefix!r})\n\n\n"
        f"{tools}\n\n"
        'if __name__ == "__main__":\n    server.run()\n'
    )


# ── Registry ────────────────────────────────────────────────────────────────


def _registry() -> dict:
    return json.loads(REGISTRY.read_text()) if REGISTRY.is_file() else {}


_LOADED: dict[tuple[str, int], Any] = {}


def _module(connector: str):
    """The connector's module: a ready-made one, or a forged one in generated/."""
    if connector in SERVERS:
        return importlib.import_module(f"connectors.{connector}")
    path = GENERATED / f"{_ident(connector)}.py"
    if not path.is_file():
        raise ValueError(f"No connector named {connector!r}. Known: {', '.join(list_all())}")
    key = (str(path), path.stat().st_mtime_ns)
    if key not in _LOADED:  # loaded once per version of the file
        spec = importlib.util.spec_from_file_location(f"connectors.generated.{_ident(connector)}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _LOADED[key] = module
    return _LOADED[key]


def list_all() -> list[str]:
    return [*SERVERS, *_registry()]


async def tools_of(connector: str) -> list[dict]:
    server = _module(connector).server
    return [{"name": t.name, "description": (t.description or "").split("\n")[0], "input": t.input_schema.get("properties", {})}
            for t in await server.list_tools()]


async def forge(name: str, base_url: str, endpoints: list[Endpoint], description: str = "", source: str = "endpoints",
                auth_header: str | None = None, auth_env: str | None = None, auth_prefix: str = "") -> dict:
    """Write, load and register a connector. Returns its name, path and tools."""
    ident = _ident(name)
    if ident in SERVERS:
        raise ValueError(f"{ident!r} is a ready-made connector; choose another name.")
    if not endpoints:
        raise ValueError("No endpoints to build tools from.")
    code = render(ident, base_url, endpoints, description, auth_header, auth_env, auth_prefix)
    compile(code, f"{ident}.py", "exec")  # never write a connector that does not parse
    GENERATED.mkdir(exist_ok=True)
    path = GENERATED / f"{ident}.py"
    path.write_text(code, encoding="utf-8", newline="")
    tools = await tools_of(ident)  # imports it: every tool must register
    registry = _registry()
    registry[ident] = {"description": description, "base_url": base_url, "source": source, "tools": len(tools),
                       "credential": auth_env, "forged_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    REGISTRY.write_text(json.dumps(registry, indent=2), encoding="utf-8", newline="")
    return {"connector": ident, "path": str(path.relative_to(GENERATED.parent.parent)), "tools": tools}


async def forge_openapi(name: str, spec_url: str, description: str = "", max_tools: int = 30, include: str | None = None,
                        auth_header: str | None = None, auth_env: str | None = None, auth_prefix: str = "") -> dict:
    spec = await request("GET", spec_url)
    if isinstance(spec, str):
        try:
            import yaml  # optional: only for YAML specs
        except ImportError as exc:
            raise RuntimeError("This spec is YAML; install pyyaml or give a JSON spec URL.") from exc
        spec = yaml.safe_load(spec)
    base, endpoints = endpoints_from_openapi(spec, max_tools, include)
    # A relative server URL resolves against the spec's own URL; none at all means the API
    # lives next to its spec (https://host/api/openapi.json → https://host/api).
    base = urljoin(spec_url, base) if base else spec_url.rsplit("/", 1)[0]
    info = spec.get("info", {})
    about = re.sub(r"<[^>]+>", "", info.get("description") or "").strip()[:300]
    return await forge(name, base, endpoints, description or info.get("title", "") + (f" — {about}" if about else ""),
                       f"openapi:{spec_url}", auth_header, auth_env, auth_prefix)


async def call(connector: str, tool: str, args: dict) -> Any:
    """Call one tool of a connector directly, as an MCP client would; returns its result as data."""
    result = await _module(connector).server.call_tool(tool, args)
    if getattr(result, "is_error", False):
        raise RuntimeError(" ".join(getattr(c, "text", "") for c in result.content) or f"{tool} failed")
    if getattr(result, "structured_content", None):
        return result.structured_content.get("result", result.structured_content)
    parts = []
    for c in getattr(result, "content", []):
        text = getattr(c, "text", "")
        try:
            parts.append(json.loads(text))
        except (json.JSONDecodeError, TypeError):
            parts.append(text)
    return parts[0] if len(parts) == 1 else parts


# ── The forge as an MCP server ──────────────────────────────────────────────

server = MCPServer(
    "connector-forge",
    instructions="Create MCP connectors for any HTTP API or experimentation server, then inspect and call them.",
)


@server.tool()
async def list_connectors() -> dict:
    """Every available connector: the ready-made scientific databases and those forged so far."""
    return {"ready_made": SERVERS, "forged": _registry()}


@server.tool()
async def inspect_connector(connector: str) -> list[dict]:
    """The tools a connector provides, with their parameters."""
    return await tools_of(connector)


@server.tool()
async def forge_connector_from_openapi(name: str, spec_url: str, description: str = "", max_tools: int = 30,
                                       only_matching: str | None = None, credential_env_var: str | None = None,
                                       credential_header: str | None = None, credential_prefix: str = "") -> dict:
    """Build a connector from an OpenAPI/Swagger spec URL: one tool per operation (up to max_tools; optionally only
    those whose path, summary or tag mentions `only_matching`). For APIs needing a key, name the env var and header."""
    return await forge_openapi(name, spec_url, description, max_tools, only_matching, credential_header, credential_env_var, credential_prefix)


@server.tool()
async def forge_connector(name: str, base_url: str, endpoints: list[dict], description: str = "",
                          credential_env_var: str | None = None, credential_header: str | None = None, credential_prefix: str = "") -> dict:
    """Build a connector from a base URL and endpoints, for APIs without a spec (lab instruments, internal servers).
    Each endpoint: {"name", "method", "path" (with {placeholders}), "description",
    "params": [{"name", "in": "path"|"query", "type", "required", "description"}], "body": bool}."""
    eps = [Endpoint(e["name"], e.get("method", "get").lower(), e["path"], e.get("description", ""),
                    [Param(p["name"], p.get("in", "query"), p.get("type", "string"), bool(p.get("required")), p.get("description", ""))
                     for p in e.get("params", [])], bool(e.get("body"))) for e in endpoints]
    return await forge(name, base_url, eps, description, "endpoints", credential_header, credential_env_var, credential_prefix)


@server.tool()
async def call_connector(connector: str, tool: str, arguments: dict | None = None) -> Any:
    """Call a tool on any connector, ready-made or forged, and return its result."""
    return await call(connector, tool, arguments or {})


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m connectors.forge", description="OpenScientist Connector Forge")
    sub = ap.add_subparsers(dest="cmd")
    o = sub.add_parser("openapi", help="forge a connector from an OpenAPI spec URL")
    o.add_argument("name")
    o.add_argument("spec_url")
    o.add_argument("--max-tools", type=int, default=30)
    o.add_argument("--only", default=None, help="keep operations mentioning this word")
    sub.add_parser("list", help="list connectors")
    t = sub.add_parser("tools", help="list a connector's tools")
    t.add_argument("connector")
    c = sub.add_parser("call", help="call a connector's tool")
    c.add_argument("connector")
    c.add_argument("tool")
    c.add_argument("args", nargs="?", default="{}")
    a = ap.parse_args(argv)
    if a.cmd is None:
        server.run()  # no command: serve the forge over MCP (stdio)
        return
    if a.cmd == "openapi":
        out = asyncio.run(forge_openapi(a.name, a.spec_url, max_tools=a.max_tools, include=a.only))
    elif a.cmd == "list":
        out = {"ready_made": SERVERS, "forged": _registry()}
    elif a.cmd == "tools":
        out = asyncio.run(tools_of(a.connector))
    else:
        out = asyncio.run(call(a.connector, a.tool, json.loads(a.args)))
    json.dump(out, sys.stdout, indent=2, default=str, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
