import json
from collections.abc import AsyncIterator
from contextvars import ContextVar

import anthropic
import httpx
from anthropic import AsyncAnthropicBedrock, transform_schema
from pydantic import BaseModel, ValidationError
from sqlmodel import Session

from .beta import check_project_allowance, owner_of
from .config import SONNET_4_6, settings
from .db import Usage, engine
from .sources import tavily

# Claude on Amazon Bedrock (InvokeModel). An explicit timeout lets long non-streaming
# calls run; without one the SDK refuses large max_tokens unless the call streams.
client = AsyncAnthropicBedrock(
    aws_region=settings.aws_region,
    aws_access_key=settings.aws_access_key_id,
    aws_secret_key=settings.aws_secret_access_key,
    aws_session_token=settings.aws_session_token,
    timeout=900.0,
)

MAX_TOKENS = 32_000  # per response, thinking included
CHAT_MAX_TOKENS = 16_000
# Effort ("low"/"medium") steers how much the model thinks, as reasoning effort did.
THINKING = {"type": "adaptive"}
SEARCH_ROUNDS = 8  # web_search rounds allowed inside one structured-output call

# Attribution for cost tracking; set by jobs and request handlers.
current_project: ContextVar[str | None] = ContextVar("current_project", default=None)
current_run: ContextVar[str | None] = ContextVar("current_run", default=None)


def cost_of(model: str, input_tokens: int, cached: int, output_tokens: int, web_searches: int = 0,
            cache_writes: int = 0) -> float:
    p_in, p_cached, p_out = settings.model_prices.get(model, settings.model_prices[SONNET_4_6])
    return (
        (input_tokens - cached) * p_in + cached * p_cached + output_tokens * p_out
        + cache_writes * p_in * 0.25  # prompt-cache writes cost 1.25x input
    ) / 1e6 + web_searches * settings.web_search_price


def record_usage(model: str, response) -> float:
    """Persist a response's token usage; returns its estimated cost in USD."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0.0
    # Claude reports uncached input separately from cache reads and writes.
    cached = getattr(usage, "cache_read_input_tokens", 0) or 0
    written = getattr(usage, "cache_creation_input_tokens", 0) or 0
    input_tokens = usage.input_tokens + cached + written
    # A search is billed on the response that requested it.
    searches = sum(1 for b in getattr(response, "content", []) or []
                   if b.type == "tool_use" and b.name == "web_search")
    cost = cost_of(model, input_tokens, cached, usage.output_tokens, searches, written)
    with Session(engine) as s:
        s.add(
            Usage(
                project_id=current_project.get(), user_id=owner_of(current_project.get()),
                run_id=current_run.get(), model=model,
                input_tokens=input_tokens, cached_tokens=cached, output_tokens=usage.output_tokens,
                web_searches=searches, cost=cost,
            )
        )
        s.commit()
    return cost


def _messages(messages: list[dict]) -> list[dict]:
    return [m for m in messages if m.get("content")]  # the API rejects empty turns


async def stream_text(
    *,
    model: str,
    instructions: str,
    messages: list[dict],
    reasoning_effort: str = "low",
) -> AsyncIterator[str]:
    """Stream text deltas (thinking is not streamed)."""
    try:
        async with client.messages.stream(
            model=model,
            max_tokens=CHAT_MAX_TOKENS,
            system=instructions,
            messages=_messages(messages),
            thinking=THINKING,
            output_config={"effort": reasoning_effort},
        ) as stream:
            async for text in stream.text_stream:
                yield text
            record_usage(model, await stream.get_final_message())
    except anthropic.APIError as exc:
        raise RuntimeError(str(exc) or "LLM stream error") from exc


async def _search(calls: list) -> list[dict]:
    """Run web_search tool calls; failures go back to the model, which can adapt."""
    results = []
    async with httpx.AsyncClient() as http:
        for call in calls:
            try:
                out, failed = json.dumps(await tavily.search(http, call.input["query"]), ensure_ascii=False), False
            except Exception as exc:
                out, failed = f"Tool error: {type(exc).__name__}: {exc}", True
            results.append({"type": "tool_result", "tool_use_id": call.id, "content": out, "is_error": failed})
    return results


def _no_output(response) -> RuntimeError:
    return RuntimeError(f"Model returned no structured output (stop reason: {response.stop_reason})")


def _validated[T: BaseModel](schema: type[T], data: str | dict) -> T:
    try:
        return schema.model_validate_json(data) if isinstance(data, str) else schema.model_validate(data)
    except ValidationError as exc:
        raise RuntimeError(f"Model returned invalid structured output: {exc}") from exc


def _parsed[T: BaseModel](response, schema: type[T]) -> T:
    text = "".join(b.text for b in response.content if b.type == "text")
    if response.stop_reason in ("refusal", "max_tokens") or not text.strip():
        raise _no_output(response)
    return _validated(schema, text)


# Constrained decoding compiles each schema into a grammar with a size limit, and
# thinking adds to it. Schemas over the limit fall back (remembered per schema) to
# "no_thinking" (still enforced by the API) or, if still too large, to "tool": the
# schema as a forced tool's input schema, validated here by Pydantic.
_GRAMMAR_FALLBACK: dict[type[BaseModel], str] = {}


def _grammar_too_large(exc: anthropic.BadRequestError) -> bool:
    return "grammar is too large" in str(exc)


async def _structured[T: BaseModel](model: str, instructions: str, msgs: list[dict], schema: type[T],
                                    reasoning_effort: str, thinking: dict) -> T:
    response = await client.messages.create(
        model=model, max_tokens=MAX_TOKENS, system=instructions, messages=msgs, thinking=thinking,
        output_config={"effort": reasoning_effort, "format": {"type": "json_schema", "schema": transform_schema(schema)}},
    )
    record_usage(model, response)
    return _parsed(response, schema)


async def _via_tool[T: BaseModel](model: str, instructions: str, msgs: list[dict], schema: type[T],
                                  reasoning_effort: str) -> T:
    name = schema.__name__
    response = await client.messages.create(
        model=model, max_tokens=MAX_TOKENS, system=instructions, messages=msgs,
        tools=[{"name": name, "description": f"Return the {name}.", "input_schema": transform_schema(schema)}],
        tool_choice={"type": "tool", "name": name},  # forced tool use needs thinking off
        thinking={"type": "disabled"}, output_config={"effort": reasoning_effort},
    )
    record_usage(model, response)
    block = next((b for b in response.content if b.type == "tool_use" and b.name == name), None)
    if block is None or response.stop_reason in ("refusal", "max_tokens"):
        raise _no_output(response)
    return _validated(schema, block.input)


async def _with_search[T: BaseModel](model: str, instructions: str, msgs: list[dict], schema: type[T],
                                     reasoning_effort: str) -> T:
    """Search first, then free choice; the last round must answer. Forced tool use needs
    thinking off, and thinking cannot be switched on partway through a tool loop."""
    from .execution.tools import TOOLS  # local import: the execution package imports this module

    output_config = {"effort": reasoning_effort, "format": {"type": "json_schema", "schema": transform_schema(schema)}}
    for round_ in range(SEARCH_ROUNDS + 1):
        choice = "any" if round_ == 0 else "auto" if round_ < SEARCH_ROUNDS else "none"
        response = await client.messages.create(
            model=model, max_tokens=MAX_TOKENS, system=instructions, messages=msgs, output_config=output_config,
            tools=[TOOLS["web_search"].spec()], tool_choice={"type": choice}, thinking={"type": "disabled"},
        )
        record_usage(model, response)
        calls = [b for b in response.content if b.type == "tool_use"]
        if not calls:
            break
        msgs = [*msgs, {"role": "assistant", "content": response.content}, {"role": "user", "content": await _search(calls)}]
    return _parsed(response, schema)


async def parse[T: BaseModel](
    *,
    model: str,
    instructions: str,
    messages: list[dict],
    schema: type[T],
    reasoning_effort: str = "medium",
    tools: list[dict] | None = None,
) -> T:
    """One structured-output call; returns the parsed Pydantic object.

    The API enforces the schema (output_config.format) and Pydantic validates the
    result. tools=[{"type": "web_search"}] makes the model search the web before it
    answers (left to choose, Claude often answered from memory at low effort).

    Raises BetaLimitReached before any request once the project owner's credits are
    used up. A call that starts with credit left runs to completion and is recorded.
    """
    check_project_allowance(current_project.get())
    msgs = _messages(messages)
    if any(t.get("type") == "web_search" for t in tools or []):
        return await _with_search(model, instructions, msgs, schema, reasoning_effort)
    fallback = _GRAMMAR_FALLBACK.get(schema)
    if fallback is None:
        try:
            return await _structured(model, instructions, msgs, schema, reasoning_effort, THINKING)
        except anthropic.BadRequestError as exc:
            if not _grammar_too_large(exc):
                raise
        fallback = _GRAMMAR_FALLBACK[schema] = "no_thinking"
    if fallback == "no_thinking":
        try:
            return await _structured(model, instructions, msgs, schema, reasoning_effort, {"type": "disabled"})
        except anthropic.BadRequestError as exc:
            if not _grammar_too_large(exc):
                raise
        _GRAMMAR_FALLBACK[schema] = "tool"
    return await _via_tool(model, instructions, msgs, schema, reasoning_effort)
