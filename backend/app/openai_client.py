"""OpenAI as the model provider, behind the Messages-API surface the rest of the backend uses.

llm.py and execution/agent.py speak the Anthropic Messages API (system + messages with text,
tool_use and tool_result blocks, tools with input_schema, output_config for effort and JSON
schema). When LLM_PROVIDER=openai, `OpenAIMessagesClient` stands in for the Bedrock client: it
translates each request to the OpenAI Responses API (the endpoint that allows function tools
together with reasoning) and the reply back into Messages-shaped objects (content blocks,
stop_reason, usage), and raises the anthropic SDK's own exception types, so every caller's retry
and error handling works unchanged.

Nothing is stored on OpenAI's side (store=false): a tool loop's reasoning goes back to the model
as the encrypted reasoning items the API returns, carried in the transcript as ReasoningBlocks.
"""

import asyncio
import json
import logging
import random
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from types import SimpleNamespace

import anthropic
import httpx
import httpx2

from .config import settings

log = logging.getLogger("openscientist.openai")

URL = "https://api.openai.com/v1/responses"
RETRIES = 4  # attempts beyond the first, for rate limits, 5xx and dropped connections
EFFORTS = ["low", "medium", "high"]


# ── Messages-shaped response objects ────────────────────────────────────────


@dataclass
class TextBlock:
    text: str
    type: str = "text"

    def model_dump(self, **_) -> dict:
        return {"type": "text", "text": self.text}


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict
    type: str = "tool_use"

    def model_dump(self, **_) -> dict:
        return {"type": "tool_use", "id": self.id, "name": self.name, "input": self.input}


@dataclass
class ReasoningBlock:
    """An OpenAI reasoning item, passed back verbatim on the next turn of a tool loop."""
    item: dict
    type: str = "thinking"

    def model_dump(self, **_) -> dict:
        return {"type": "thinking", "openai_item": self.item}


@dataclass
class Usage:
    input_tokens: int = 0  # uncached input, as Claude reports it
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class Message:
    content: list = field(default_factory=list)
    stop_reason: str = "end_turn"
    usage: Usage = field(default_factory=Usage)
    model: str = ""


# ── Request translation ─────────────────────────────────────────────────────


def _get(block, key, default=None):
    return block.get(key, default) if isinstance(block, dict) else getattr(block, key, default)


def _result_text(content) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(_get(b, "text", "") for b in content or [] if _get(b, "type") == "text")


def _input(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        role, content = m["role"], m.get("content")
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue
        texts: list[str] = []

        def flush():
            if texts:
                out.append({"role": role, "content": "\n".join(texts)})
                texts.clear()

        for b in content or []:
            kind = _get(b, "type")
            if kind == "text":
                texts.append(_get(b, "text", ""))
            elif kind == "thinking":
                item = _get(b, "item") or _get(b, "openai_item")
                if item:
                    flush()
                    out.append(item)
            elif kind == "tool_use":
                flush()
                out.append({"type": "function_call", "call_id": _get(b, "id"), "name": _get(b, "name"),
                            "arguments": json.dumps(_get(b, "input") or {}, ensure_ascii=False)})
            elif kind == "tool_result":
                flush()
                text = _result_text(_get(b, "content"))
                out.append({"type": "function_call_output", "call_id": _get(b, "tool_use_id"),
                            "output": f"[error] {text}" if _get(b, "is_error") else text})
            # redacted_thinking and other Claude-only blocks have no counterpart and are dropped
        flush()
    return out


def _tools(tools: list[dict] | None) -> list[dict] | None:
    if not tools:
        return None
    return [{"type": "function", "name": t["name"], "description": t.get("description", ""),
             "parameters": t.get("input_schema") or {"type": "object"}, "strict": False}
            for t in tools]


def _tool_choice(choice: dict | None):
    kind = (choice or {}).get("type")
    if kind == "any":
        return "required"
    if kind == "tool":
        return {"type": "function", "name": choice["name"]}
    return kind  # "auto", "none" or None


def _body(model: str, max_tokens: int, system: str | None = None, messages: list[dict] | None = None,
          tools: list[dict] | None = None, tool_choice: dict | None = None, output_config: dict | None = None,
          **_ignored) -> dict:
    effort = (output_config or {}).get("effort") or "medium"
    effort = max(effort if effort in EFFORTS else "medium", settings.openai_min_effort, key=EFFORTS.index)
    body: dict = {
        "model": model,
        "input": _input(messages or []),
        "max_output_tokens": min(max(max_tokens * 2, settings.openai_min_output_tokens), settings.openai_max_output_tokens),
        "reasoning": {"effort": effort},
        "store": False,
        "include": ["reasoning.encrypted_content"],
    }
    if system:
        body["instructions"] = system
    fmt = (output_config or {}).get("format")
    if fmt and fmt.get("type") == "json_schema":
        body["text"] = {"format": {"type": "json_schema", "name": "answer", "schema": fmt["schema"], "strict": False}}
    if (t := _tools(tools)) is not None:
        body["tools"] = t
        if (c := _tool_choice(tool_choice)) is not None:
            body["tool_choice"] = c
    return body


def _message(data: dict, model: str) -> Message:
    content: list = []
    refused = False
    for item in data.get("output") or []:
        kind = item.get("type")
        if kind == "reasoning":
            content.append(ReasoningBlock({k: v for k, v in item.items() if k != "status"}))
        elif kind == "message":
            for part in item.get("content") or []:
                if part.get("type") == "output_text" and part.get("text"):
                    content.append(TextBlock(part["text"]))
                elif part.get("type") == "refusal":
                    refused = True
        elif kind == "function_call":
            try:
                args = json.loads(item.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            content.append(ToolUseBlock(item["call_id"], item["name"], args if isinstance(args, dict) else {}))
    if refused:
        stop = "refusal"
    elif data.get("status") == "incomplete" and (data.get("incomplete_details") or {}).get("reason") == "max_output_tokens":
        stop = "max_tokens"
    elif data.get("status") == "incomplete":
        stop = "refusal"  # content filter
    elif any(b.type == "tool_use" for b in content):
        stop = "tool_use"
    else:
        stop = "end_turn"
    return Message(content, stop, _usage(data.get("usage")), model)


def _usage(u: dict | None) -> Usage:
    u = u or {}
    cached = (u.get("input_tokens_details") or {}).get("cached_tokens") or 0
    return Usage(input_tokens=(u.get("input_tokens") or 0) - cached, output_tokens=u.get("output_tokens") or 0,
                 cache_read_input_tokens=cached)


# ── Errors: raised as the anthropic SDK's own types ─────────────────────────

_STATUS = {400: anthropic.BadRequestError, 401: anthropic.AuthenticationError, 403: anthropic.PermissionDeniedError,
           404: anthropic.NotFoundError, 409: anthropic.ConflictError, 413: anthropic.RequestTooLargeError,
           422: anthropic.UnprocessableEntityError, 429: anthropic.RateLimitError,
           500: anthropic.InternalServerError, 503: anthropic.ServiceUnavailableError}


def _status_error(status: int, text: str) -> anthropic.APIStatusError:
    try:
        body = json.loads(text)
    except json.JSONDecodeError:
        body = {"error": {"message": text}}
    message = ((body.get("error") or {}).get("message") if isinstance(body, dict) else None) or text
    response = httpx2.Response(status, request=httpx2.Request("POST", URL), text=text)
    cls = _STATUS.get(status) or (anthropic.InternalServerError if status >= 500 else anthropic.APIStatusError)
    return cls(f"{status}: {message}", response=response, body=body)


def _connection_error(exc: Exception) -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(message=f"{type(exc).__name__}: {exc}", request=httpx2.Request("POST", URL))


def _retryable(status: int) -> bool:
    return status == 429 or status >= 500


def _backoff(attempt: int, retry_after: str | None = None) -> float:
    try:
        if retry_after:
            return min(float(retry_after), 30.0)
    except ValueError:
        pass
    return min(2 ** attempt + random.random(), 30.0)


# ── The client ──────────────────────────────────────────────────────────────


class _Stream:
    """`async with client.messages.stream(...)`: text deltas, then the final message."""

    def __init__(self, owner: "OpenAIMessagesClient", kw: dict):
        self._owner, self._kw = owner, kw
        self._final: Message | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def text_stream(self) -> AsyncIterator[str]:
        return self._deltas()

    async def _deltas(self) -> AsyncIterator[str]:
        body = {**_body(**self._kw), "stream": True}
        try:
            async with self._owner.http.stream("POST", URL, headers=self._owner.headers, json=body) as resp:
                if resp.status_code != 200:
                    raise _status_error(resp.status_code, (await resp.aread()).decode(errors="replace"))
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    event = json.loads(line[5:].strip() or "{}")
                    kind = event.get("type")
                    if kind == "response.output_text.delta" and event.get("delta"):
                        yield event["delta"]
                    elif kind in ("response.completed", "response.incomplete"):
                        self._final = _message(event.get("response") or {}, self._kw.get("model", ""))
                    elif kind in ("error", "response.failed"):
                        err = event.get("error") or (event.get("response") or {}).get("error") or {}
                        raise anthropic.APIConnectionError(message=f"stream failed: {err}",
                                                           request=httpx2.Request("POST", URL))
        except httpx.TransportError as exc:
            raise _connection_error(exc) from exc

    async def get_final_message(self) -> Message:
        if self._final is None:
            async for _ in self._deltas():  # nobody consumed the stream: drain it
                pass
        return self._final or Message(model=self._kw.get("model", ""))


class _Messages:
    def __init__(self, owner: "OpenAIMessagesClient"):
        self._owner = owner

    async def create(self, **kw) -> Message:
        body = _body(**kw)
        for attempt in range(RETRIES + 1):
            try:
                resp = await self._owner.http.post(URL, headers=self._owner.headers, json=body)
            except httpx.TransportError as exc:
                if attempt < RETRIES:
                    await asyncio.sleep(_backoff(attempt))
                    continue
                raise _connection_error(exc) from exc
            if resp.status_code == 200:
                return _message(resp.json(), kw.get("model", ""))
            if _retryable(resp.status_code) and attempt < RETRIES:
                log.warning("openai %s (attempt %d/%d); retrying", resp.status_code, attempt + 1, RETRIES + 1)
                await asyncio.sleep(_backoff(attempt, resp.headers.get("retry-after")))
                continue
            raise _status_error(resp.status_code, resp.text)
        raise AssertionError("unreachable")

    def stream(self, **kw) -> _Stream:
        return _Stream(self._owner, kw)


class OpenAIMessagesClient:
    def __init__(self, api_key: str | None, timeout: float = 900.0):
        if not api_key:
            log.error("LLM_PROVIDER=openai but OPENAI_API_KEY is not set; every model call will fail")
        self.headers = {"Authorization": f"Bearer {api_key or ''}"}
        self._timeout = httpx.Timeout(timeout, connect=30.0)
        self._clients: dict[int, httpx.AsyncClient] = {}
        self.messages = _Messages(self)
        self.beta = SimpleNamespace(messages=self.messages)

    @property
    def http(self) -> httpx.AsyncClient:
        """One HTTP client per event loop: a pooled connection cannot outlive the loop it was made on."""
        loop = id(asyncio.get_running_loop())
        if loop not in self._clients:
            self._clients[loop] = httpx.AsyncClient(timeout=self._timeout)
        return self._clients[loop]
