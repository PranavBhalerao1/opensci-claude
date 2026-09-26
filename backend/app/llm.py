from collections.abc import AsyncIterator

from openai import AsyncOpenAI
from pydantic import BaseModel

from .config import settings

client = AsyncOpenAI(api_key=settings.openai_api_key)


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
        elif event.type == "error":
            raise RuntimeError(getattr(event, "message", "LLM stream error"))


async def parse[T: BaseModel](
    *,
    model: str,
    instructions: str,
    messages: list[dict],
    schema: type[T],
    reasoning_effort: str = "medium",
) -> T:
    """One structured-output call; returns the parsed Pydantic object."""
    response = await client.responses.parse(
        model=model,
        instructions=instructions,
        input=messages,
        text_format=schema,
        reasoning={"effort": reasoning_effort},
    )
    if response.output_parsed is None:
        raise RuntimeError("Model returned no structured output")
    return response.output_parsed
