import json
import logging
import re
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

log = logging.getLogger("openscientist.llm")

# Claude on Amazon Bedrock (InvokeModel). An explicit timeout lets long non-streaming
# calls run; without one the SDK refuses large max_tokens unless the call streams.
client = AsyncAnthropicBedrock(
    aws_region=settings.aws_region,
    aws_access_key=settings.aws_access_key_id,
    aws_secret_key=settings.aws_secret_access_key,
    aws_session_token=settings.aws_session_token,
    timeout=900.0,
)

# Network and provider failures: raised only once the SDK's own HTTP retries are spent, and
# never with a usable response, so nothing was recorded. Not the caller's fault.
TRANSIENT_ERRORS = (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.ServiceUnavailableError,
                    anthropic.OverloadedError, anthropic.InternalServerError)

MAX_TOKENS = 32_000  # hard per-response ceiling (thinking included) — the limit this Bedrock
                      # deployment supports for one Messages call
CHAT_MAX_TOKENS = 16_000
# Default structured-output / agent-step budget by reasoning effort, used whenever a caller
# does not request a specific max_tokens. "high" gets the full ceiling: the heaviest schemas
# (MasterPlan, ResearchPlan, the scientific judge) run at high effort and need room for both
# adaptive thinking and a large JSON object. Routine calls default lower to avoid requesting
# the model's maximum everywhere; parse() still retries once at the full ceiling if a smaller
# budget truncates the response, so under-sizing a tier here is self-healing, not a hard cap.
EFFORT_TOKENS = {"low": 8_000, "medium": 16_000, "high": MAX_TOKENS}
# Effort ("low"/"medium"/"high") steers how much the model thinks, as reasoning effort did.
THINKING = {"type": "adaptive"}
SEARCH_ROUNDS = 8  # web_search rounds allowed inside one structured-output call
REPAIR_ATTEMPTS = 2  # bounded JSON-repair retries for the freeform structured-output fallback

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


def _output_budget(reasoning_effort: str, max_tokens: int | None) -> int:
    return max_tokens if max_tokens is not None else EFFORT_TOKENS.get(reasoning_effort, EFFORT_TOKENS["medium"])


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


_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL)


def _strip_fence(text: str) -> str:
    """The model was told to answer with bare JSON, but may still wrap it in a markdown
    code fence; tolerate that rather than failing a validation attempt over formatting."""
    stripped = text.strip()
    m = _FENCE_RE.match(stripped)
    return m.group(1).strip() if m else stripped


# Constrained decoding compiles each schema into a grammar with a size limit, and thinking
# adds to it. A schema over the limit is remembered here and, for every later call, skips
# straight to the freeform fallback below (never to a thinking-disabled mode: see _freeform).
_GRAMMAR_FALLBACK: dict[type[BaseModel], str] = {}


def _grammar_too_large(exc: anthropic.BadRequestError) -> bool:
    return "grammar is too large" in str(exc)


async def _attempt(model: str, instructions: str, msgs: list[dict], max_tokens: int, reasoning_effort: str,
                   output_config_extra: dict):
    response = await client.messages.create(
        model=model, max_tokens=max_tokens, system=instructions, messages=msgs, thinking=THINKING,
        output_config={"effort": reasoning_effort, **output_config_extra},
    )
    record_usage(model, response)
    return response


async def _schema_constrained[T: BaseModel](model: str, instructions: str, msgs: list[dict], schema: type[T],
                                            reasoning_effort: str, max_tokens: int) -> T:
    """One schema-constrained attempt: adaptive thinking, the schema enforced server-side by
    Bedrock's constrained decoding. Raises anthropic.BadRequestError if the compiled grammar is
    too large; the caller falls back to _freeform, which keeps thinking on."""
    fmt = {"format": {"type": "json_schema", "schema": transform_schema(schema)}}
    response = await _attempt(model, instructions, msgs, max_tokens, reasoning_effort, fmt)
    if response.stop_reason == "max_tokens" and max_tokens < MAX_TOKENS:
        log.info("parse: %s truncated at %d tokens; retrying once at the %d-token ceiling",
                 schema.__name__, max_tokens, MAX_TOKENS)
        response = await _attempt(model, instructions, msgs, MAX_TOKENS, reasoning_effort, fmt)
    return _parsed(response, schema)


async def _freeform[T: BaseModel](model: str, instructions: str, msgs: list[dict], schema: type[T],
                                  reasoning_effort: str, max_tokens: int) -> T:
    """Schema too complex for Bedrock's constrained-decoding grammar: ask for plain JSON
    instead of an API-enforced schema, with adaptive thinking preserved (never disabled to
    work around the grammar limit). The result is validated with Pydantic exactly as the
    schema-constrained path is; a bounded number of repair attempts feed back the actual
    validation error so the model can fix it, and a truncated response gets one retry at the
    full token ceiling. Never returns an unvalidated or malformed object — it raises instead.
    """
    schema_text = json.dumps(transform_schema(schema), indent=1, ensure_ascii=False)
    sys = (f"{instructions}\n\nRespond with ONLY one JSON object matching this JSON Schema exactly. "
          f"No prose, no markdown code fences, no explanation — the JSON object alone.\n\n{schema_text}")
    attempt_msgs = msgs
    problem = "no attempt was made"
    for attempt in range(1, REPAIR_ATTEMPTS + 2):
        response = await _attempt(model, sys, attempt_msgs, max_tokens, reasoning_effort, {})
        if response.stop_reason == "max_tokens" and max_tokens < MAX_TOKENS:
            response = await _attempt(model, sys, attempt_msgs, MAX_TOKENS, reasoning_effort, {})
        text = "".join(b.text for b in response.content if b.type == "text")
        if response.stop_reason == "refusal" or not text.strip():
            raise _no_output(response)
        if response.stop_reason == "max_tokens":
            problem = f"the response was truncated even at the {MAX_TOKENS}-token ceiling"
        else:
            try:
                return _validated(schema, _strip_fence(text))
            except RuntimeError as exc:
                problem = str(exc)
        log.warning("parse: %s freeform output invalid (attempt %d/%d): %s",
                   schema.__name__, attempt, REPAIR_ATTEMPTS + 1, problem)
        if attempt <= REPAIR_ATTEMPTS:
            attempt_msgs = [
                *msgs,
                {"role": "assistant", "content": text or "(empty)"},
                {"role": "user", "content": f"That was invalid: {problem}\n\nReturn ONLY the corrected JSON "
                                            "object matching the schema; no prose, no markdown fences."},
            ]
    raise RuntimeError(f"Model could not produce valid structured output for {schema.__name__} after "
                       f"{REPAIR_ATTEMPTS + 1} attempts: {problem}")


async def _with_search[T: BaseModel](model: str, instructions: str, msgs: list[dict], schema: type[T],
                                     reasoning_effort: str, max_tokens: int) -> T:
    """Search first, then free choice; the last round must answer. Forced tool use needs
    thinking off, and thinking cannot be switched on partway through a tool loop."""
    from .execution.tools import TOOLS  # local import: the execution package imports this module

    output_config = {"effort": reasoning_effort, "format": {"type": "json_schema", "schema": transform_schema(schema)}}
    for round_ in range(SEARCH_ROUNDS + 1):
        choice = "any" if round_ == 0 else "auto" if round_ < SEARCH_ROUNDS else "none"
        response = await client.messages.create(
            model=model, max_tokens=max_tokens, system=instructions, messages=msgs, output_config=output_config,
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
    max_tokens: int | None = None,
) -> T:
    """One structured-output call; returns the parsed Pydantic object.

    The API enforces the schema (output_config.format) and adaptive thinking runs throughout.
    If the schema is too complex for Bedrock's constrained-decoding grammar, this falls back
    (remembered per schema) to asking for plain JSON instead — thinking is never disabled to
    work around that limit. A truncated response gets one retry at the full token ceiling;
    a freeform response that fails Pydantic validation gets a bounded number of repair
    attempts with the actual validation error fed back. This never silently returns a
    malformed or incomplete object: every failure mode raises.

    tools=[{"type": "web_search"}] makes the model search the web before it answers (left to
    choose, Claude often answered from memory at low effort).

    Raises BetaLimitReached before any request once the project owner's credits are used up.
    A call that starts with credit left runs to completion and is recorded.
    """
    check_project_allowance(current_project.get())
    msgs = _messages(messages)
    budget = _output_budget(reasoning_effort, max_tokens)
    if any(t.get("type") == "web_search" for t in tools or []):
        return await _with_search(model, instructions, msgs, schema, reasoning_effort, budget)
    if _GRAMMAR_FALLBACK.get(schema) != "freeform":
        try:
            return await _schema_constrained(model, instructions, msgs, schema, reasoning_effort, budget)
        except anthropic.BadRequestError as exc:
            if not _grammar_too_large(exc):
                raise
            _GRAMMAR_FALLBACK[schema] = "freeform"
            log.info("parse: %s's schema is too complex for constrained decoding; falling back to freeform "
                     "JSON with adaptive thinking preserved", schema.__name__)
    return await _freeform(model, instructions, msgs, schema, reasoning_effort, budget)
