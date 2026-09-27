from collections.abc import AsyncIterator
from contextvars import ContextVar

from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlmodel import Session

from .config import settings
from .db import Usage, engine

client = AsyncOpenAI(api_key=settings.openai_api_key)

# Attribution for cost tracking; set by jobs and request handlers.
current_project: ContextVar[str | None] = ContextVar("current_project", default=None)
current_run: ContextVar[str | None] = ContextVar("current_run", default=None)


def cost_of(model: str, input_tokens: int, cached: int, output_tokens: int, web_searches: int = 0) -> float:
    p_in, p_cached, p_out = settings.model_prices.get(model, settings.model_prices["gpt-6-astra"])
    return (
        (input_tokens - cached) * p_in + cached * p_cached + output_tokens * p_out
    ) / 1e6 + web_searches * settings.web_search_price


def record_usage(model: str, response) -> float:
    """Persist a response's token usage; returns its estimated cost in USD."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0.0
    cached = getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0) or 0
    searches = sum(1 for o in getattr(response, "output", []) or [] if o.type == "web_search_call")
    cost = cost_of(model, usage.input_tokens, cached, usage.output_tokens, searches)
    with Session(engine) as s:
        s.add(
            Usage(
                project_id=current_project.get(), run_id=current_run.get(), model=model,
                input_tokens=usage.input_tokens, cached_tokens=cached, output_tokens=usage.output_tokens,
                web_searches=searches, cost=cost,
            )
        )
        s.commit()
    return cost


async def stream_text(
    *,
    model: str,
    instructions: str,
    messages: list[dict],
    reasoning_effort: str = "low",
) -> AsyncIterator[str]:
    """Stream text deltas from the Responses API."""
    stream = await client.responses.create(
        model=model,
        instructions=instructions,
        input=messages,
        reasoning={"effort": reasoning_effort},
        stream=True,
    )
    async for event in stream:
        if event.type == "response.output_text.delta":
            yield event.delta
        elif event.type == "response.completed":
            record_usage(model, event.response)
        elif event.type == "error":
            raise RuntimeError(getattr(event, "message", "LLM stream error"))


async def parse[T: BaseModel](
    *,
    model: str,
    instructions: str,
    messages: list[dict],
    schema: type[T],
    reasoning_effort: str = "medium",
    tools: list[dict] | None = None,
) -> T:
    """One structured-output call; returns the parsed Pydantic object."""
    response = await client.responses.parse(
        model=model,
        instructions=instructions,
        input=messages,
        text_format=schema,
        reasoning={"effort": reasoning_effort},
        **({"tools": tools} if tools else {}),
    )
    record_usage(model, response)
    if response.output_parsed is None:
        raise RuntimeError("Model returned no structured output")
    return response.output_parsed
