import json
import logging
import re
from collections.abc import AsyncIterator
from contextvars import ContextVar

import anthropic
import httpx
import httpx2
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


class StreamInterrupted(anthropic.APIConnectionError):
    """A streamed response that failed after it began: a dropped connection, or a transient error
    frame. The SDK raises these unwrapped (an httpx2 error, or a bare APIStatusError on the HTTP 200
    stream); as an APIConnectionError they are among TRANSIENT_ERRORS, which every caller handles.
    Nothing usable came back, so nothing was parsed or recorded."""

    def __init__(self, exc: Exception):
        try:
            request = exc.request
        except (AttributeError, RuntimeError):  # an httpx2 error raised without its request
            request = httpx2.Request("POST", "https://bedrock-runtime")
        super().__init__(message=f"Response stream interrupted: {type(exc).__name__}: {exc}", request=request)


# Error frames that can end a stream that had begun: Anthropic's own, and Bedrock's event-stream
# exceptions (compared lower-cased). Any other frame, e.g. a validation error, is not retried.
STREAM_TRANSIENT = frozenset({"overloaded_error", "api_error", "rate_limit_error", "throttlingexception",
                              "modelstreamerrorexception", "internalserverexception",
                              "serviceunavailableexception", "modeltimeoutexception"})


def _stream_error_transient(exc: anthropic.APIStatusError) -> bool:
    error = exc.body.get("error") if isinstance(exc.body, dict) else None
    kind = error.get("type") if isinstance(error, dict) else None
    return exc.status_code == 200 and isinstance(kind, str) and kind.lower() in STREAM_TRANSIENT


MAX_TOKENS = 32_000  # per-response ceiling (thinking included) for non-streaming calls: agent steps
                      # and routine structured outputs
# Claude Sonnet 4.6's per-response output maximum on Amazon Bedrock (model card: 64K, InvokeModel and
# InvokeModelWithResponseStream). Only the largest structured outputs ask for it (the research plan, the
# blueprint and the scientific judge, whose thinking plus JSON outgrew MAX_TOKENS), and such a request
# streams: streaming keeps a generation this long inside the HTTP timeout; it does not raise the model's limit.
LONG_MAX_TOKENS = 64_000
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
CONTINUATIONS = 2  # bounded continuation turns, per freeform parse, for an answer cut off by max_tokens
ANCHOR_CHARS = 80  # how much of a cut-off answer its continuation must repeat, so the join is exact

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


class OutputLimitReached(RuntimeError):
    """The response stopped at max_tokens before its answer was complete, so it was discarded,
    never parsed as one. thinking_only: the reasoning used the whole budget and no answer text was
    written at all. A RuntimeError, like every other unusable structured output."""

    def __init__(self, message: str, thinking_only: bool = False):
        super().__init__(message)
        self.thinking_only = thinking_only


def _no_output(response) -> RuntimeError:
    message = f"Model returned no structured output (stop reason: {response.stop_reason})"
    answered = bool(_text(response).strip())
    thought = any(b.type in ("thinking", "redacted_thinking") for b in response.content)
    if response.stop_reason == "max_tokens":
        used = getattr(getattr(response, "usage", None), "output_tokens", None)
        detail = "the answer was cut off by the output limit" if answered else \
            "the reasoning used the whole output budget before any answer was written"
        return OutputLimitReached(f"{message}: {detail}" + (f" ({used:,} output tokens)" if used else ""),
                                  thinking_only=not answered)
    if thought and not answered:
        return RuntimeError(f"{message}: the response held reasoning but no answer")
    return RuntimeError(message)


def _validated[T: BaseModel](schema: type[T], data: str | dict) -> T:
    try:
        return schema.model_validate_json(data) if isinstance(data, str) else schema.model_validate(data)
    except ValidationError as exc:
        raise RuntimeError(f"Model returned invalid structured output: {exc}") from exc


def _text(response) -> str:
    return "".join(b.text for b in response.content if b.type == "text")


def _parsed[T: BaseModel](response, schema: type[T]) -> T:
    text = _text(response)
    if response.stop_reason in ("refusal", "max_tokens") or not text.strip():
        raise _no_output(response)
    return _validated(schema, text)


_OPEN_FENCE = re.compile(r"^```(?:json)?\s*")
_CLOSE_FENCE = re.compile(r"\s*```$")


def _strip_fence(text: str) -> str:
    """The model was told to answer with bare JSON, but may still wrap it in a markdown
    code fence (or, across a continuation, only open or close one); tolerate that rather
    than failing a validation attempt over formatting."""
    return _CLOSE_FENCE.sub("", _OPEN_FENCE.sub("", text.strip())).strip()


FREEFORM_FORMAT = (
    "\n\nRespond with ONLY one JSON object matching the JSON Schema below exactly: no prose, no markdown code "
    "fences, no explanation. Write it compactly, without indentation or line breaks. Decide its content while "
    "you reason, but do not write the JSON, or a draft of it, in your reasoning: write it once, in your answer."
    "\n\nJSON Schema:\n")
CONTINUE = ("Your answer was cut off by the output limit. Continue it from exactly where it stopped: start your "
            "reply by repeating, verbatim, its last characters (shown between the <<< >>> markers below), then "
            "write the rest of the JSON object. Do not start the object over; no prose, no markdown fences."
            "\n<<<{anchor}>>>")
BRIEF_REASONING = ("Note: a previous attempt at this answer spent its whole output budget on reasoning and wrote no "
                   "answer. Keep your reasoning brief this time: settle the content, then write the complete JSON "
                   "object as your answer.")


def _splice(text: str, piece: str) -> str | None:
    """`text` joined with `piece`, its continuation, which must begin (after at most a stray fence or
    a little whitespace) by repeating text's last ANCHOR_CHARS characters: the pieces are joined
    exactly there. None if the continuation does not resume at the cut-off point; it is never
    appended blindly, since an overlap or a gap would still parse, as corrupted content."""
    anchor = text[-ANCHOR_CHARS:]
    for a in (anchor, anchor.lstrip()):
        i = piece.find(a, 0, len(a) + 64) if a else -1
        if i >= 0:
            return text[:len(text) - len(a)] + piece[i:]
    return None


def _with_note(msgs: list[dict], note: str) -> list[dict]:
    """msgs with `note` added to the final user turn."""
    last = msgs[-1] if msgs else {}
    if last.get("role") != "user":
        return [*msgs, {"role": "user", "content": note}]
    content = last["content"]
    content = f"{content}\n\n{note}" if isinstance(content, str) else [*content, {"type": "text", "text": note}]
    return [*msgs[:-1], {**last, "content": content}]


# Constrained decoding compiles each schema into a grammar with a size limit, and thinking
# adds to it. A schema over the limit is remembered here and, for every later call, skips
# straight to the freeform fallback below (never to a thinking-disabled mode: see _freeform).
_GRAMMAR_FALLBACK: dict[type[BaseModel], str] = {}


def _grammar_too_large(exc: anthropic.BadRequestError) -> bool:
    return "grammar is too large" in str(exc)


# Models whose endpoint refused a LONG_MAX_TOKENS request; their later calls use MAX_TOKENS instead.
_LONG_REFUSED: set[str] = set()


async def _attempt(model: str, instructions: str, msgs: list[dict], max_tokens: int, reasoning_effort: str,
                   output_config_extra: dict):
    if max_tokens > MAX_TOKENS and model in _LONG_REFUSED:
        max_tokens = MAX_TOKENS
    kw = dict(model=model, max_tokens=max_tokens, system=instructions, messages=msgs, thinking=THINKING,
              output_config={"effort": reasoning_effort, **output_config_extra})
    if max_tokens <= MAX_TOKENS:
        response = await client.messages.create(**kw)
    else:
        # Above the non-streaming ceiling the response streams (InvokeModelWithResponseStream), so a long
        # generation cannot outlast the HTTP timeout; the final message is the same as create()'s.
        try:
            async with client.messages.stream(**kw) as stream:
                response = await stream.get_final_message()
        except anthropic.BadRequestError as exc:
            if "max_tokens" not in str(exc):
                raise
            _LONG_REFUSED.add(model)
            log.warning("parse: %s refused max_tokens=%d (%s); using the %d-token ceiling",
                        model, max_tokens, exc, MAX_TOKENS)
            return await _attempt(model, instructions, msgs, MAX_TOKENS, reasoning_effort, output_config_extra)
        except TRANSIENT_ERRORS:
            raise
        except (httpx2.TransportError, anthropic.APIStatusError) as exc:
            if isinstance(exc, anthropic.APIStatusError) and not _stream_error_transient(exc):
                raise
            raise StreamInterrupted(exc) from exc
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


async def _continued(model: str, sys: str, turn: list[dict], text: str, budget: int, reasoning_effort: str,
                     turns: int) -> tuple[str, str | None, int]:
    """Continue an answer cut off by max_tokens, for at most `turns` more calls (adaptive thinking
    on, as everywhere). Returns the answer, why it is still incomplete (None once it ran to its end)
    and the number of calls used. Each continuation is joined by _splice, or rejected."""
    for used in range(1, turns + 1):
        log.info("parse: answer cut off at %d tokens; continuing (%d/%d)", budget, used, turns)
        response = await _attempt(model, sys, [*turn, {"role": "assistant", "content": text},
                                               {"role": "user", "content": CONTINUE.format(anchor=text[-ANCHOR_CHARS:])}],
                                  budget, reasoning_effort, {})
        if response.stop_reason == "refusal":
            raise _no_output(response)
        joined = _splice(text, _text(response))
        if joined is None:
            return text, "the response was cut off by the output limit and its continuation did not resume " \
                         "at the cut-off point", used
        text = joined
        if response.stop_reason != "max_tokens":
            return text, None, used
    return text, f"the response was cut off by the {budget}-token output limit" + (
        f" even after {turns} continuations" if turns else ""), turns


async def _freeform[T: BaseModel](model: str, instructions: str, msgs: list[dict], schema: type[T],
                                  reasoning_effort: str, max_tokens: int) -> T:
    """Schema too complex for Bedrock's constrained-decoding grammar: ask for plain JSON
    instead of an API-enforced schema, with adaptive thinking preserved (never disabled to
    work around the grammar limit, nor to make an answer fit). The result is validated with
    Pydantic exactly as the schema-constrained path is. Recovery is bounded and keeps thinking on:
    - a routine budget too small for the answer is raised once to MAX_TOKENS;
    - an attempt whose reasoning spent the whole budget before any answer is retried once,
      asked to reason briefly;
    - an answer cut off by max_tokens is continued (CONTINUATIONS turns per parse) instead of
      being regenerated from scratch, joined exactly where it stopped (see _splice);
    - a complete answer that fails validation gets REPAIR_ATTEMPTS repair turns with the actual
      error fed back.
    So one parse makes at most REPAIR_ATTEMPTS + CONTINUATIONS + 3 model calls. Never returns an
    unvalidated or malformed object: it raises instead (OutputLimitReached if the last attempt was
    still cut off by the output limit).
    """
    schema_text = json.dumps(transform_schema(schema), separators=(",", ":"), ensure_ascii=False)
    sys = f"{instructions}{FREEFORM_FORMAT}{schema_text}"
    budget, continued, nudged = max_tokens, 0, False
    turn = msgs
    problem = "no attempt was made"
    for attempt in range(1, REPAIR_ATTEMPTS + 2):
        response = await _attempt(model, sys, turn, budget, reasoning_effort, {})
        if response.stop_reason == "max_tokens" and budget < MAX_TOKENS:
            budget = MAX_TOKENS
            response = await _attempt(model, sys, turn, budget, reasoning_effort, {})
        text = _text(response)
        if response.stop_reason == "max_tokens" and not text.strip() and not nudged:
            nudged = True
            log.warning("parse: %s reasoning used the whole %d-token budget before any answer; retrying once "
                        "with brief reasoning", schema.__name__, budget)
            response = await _attempt(model, sys, _with_note(turn, BRIEF_REASONING), budget, reasoning_effort, {})
            text = _text(response)
        if response.stop_reason == "refusal" or not text.strip():
            raise _no_output(response)
        problem, cut_off = None, False
        if response.stop_reason == "max_tokens":
            text, problem, used = await _continued(model, sys, turn, text, budget, reasoning_effort,
                                                   CONTINUATIONS - continued)
            continued += used
            cut_off = problem is not None
        if problem is None:
            try:
                return _validated(schema, _strip_fence(text))
            except RuntimeError as exc:
                problem = str(exc)
        log.warning("parse: %s freeform output invalid (attempt %d/%d): %s",
                   schema.__name__, attempt, REPAIR_ATTEMPTS + 1, problem)
        if attempt <= REPAIR_ATTEMPTS:
            turn = [
                *msgs,
                {"role": "assistant", "content": text},
                {"role": "user", "content": f"That was invalid: {problem}\n\nReturn ONLY the corrected JSON "
                                            "object matching the schema; no prose, no markdown fences."},
            ]
    raise (OutputLimitReached if cut_off else RuntimeError)(
        f"Model could not produce valid structured output for {schema.__name__} after {REPAIR_ATTEMPTS + 1} "
        f"attempts: {problem}")


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
    work around that limit. A response truncated at a routine budget gets one retry at the
    full token ceiling; a freeform answer cut off by max_tokens is continued where it stopped,
    and one that fails Pydantic validation gets a bounded number of repair attempts with the
    actual validation error fed back (see _freeform). max_tokens above MAX_TOKENS (up to
    LONG_MAX_TOKENS) streams. This never silently returns a malformed or incomplete object:
    every failure mode raises a RuntimeError: OutputLimitReached (a subclass) when the output
    limit cut the answer off or the response was all reasoning. A stream that fails after it
    began raises StreamInterrupted, one of TRANSIENT_ERRORS.

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
