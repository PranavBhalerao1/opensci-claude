"""Agent runtime: a Claude tool-use loop with step and cost limits.

The transcript is kept here for one run and resent each step with a prompt-cache
breakpoint at its end, so the repeated prefix is billed at the cached rate.
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from .. import llm
from ..llm import MAX_TOKENS, THINKING, record_usage
from .tools import TOOLS, ToolContext, specs

TOOL_OUTPUT_LIMIT = 16_000


@dataclass
class AgentSpec:
    name: str
    instructions: str
    model: str
    tools: list[str]
    max_steps: int = 30
    max_cost: float = 1.0  # USD
    reasoning_effort: str = "medium"


@dataclass
class AgentResult:
    status: str  # success | partial | failed | step_limit | budget_exceeded | needs_credential
    summary: str
    artifacts: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    credential: dict | None = None
    steps: int = 0
    cost: float = 0.0


Event = Callable[[dict], Awaitable[None] | None]


def _short(value, limit: int = 300) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "…"


async def _emit(on_event: Event | None, event: dict) -> None:
    if on_event:
        out = on_event(event)
        if hasattr(out, "__await__"):
            await out


def _cached(transcript: list[dict]) -> list[dict]:
    """The transcript with a prompt-cache breakpoint on its final block."""
    last = transcript[-1]
    blocks = [*last["content"][:-1], {**last["content"][-1], "cache_control": {"type": "ephemeral"}}]
    return [*transcript[:-1], {**last, "content": blocks}]


async def run_agent(spec: AgentSpec, task: str, ctx: ToolContext, on_event: Event | None = None) -> AgentResult:
    tool_names = [n for n in spec.tools if n in TOOLS]
    if "report_result" not in tool_names:
        tool_names.append("report_result")
    cost = 0.0
    transcript: list[dict] = [{"role": "user", "content": [{"type": "text", "text": task}]}]

    for step in range(1, spec.max_steps + 1):
        response = await llm.client.messages.create(
            model=spec.model,
            max_tokens=MAX_TOKENS,
            system=spec.instructions,
            messages=_cached(transcript),
            tools=specs(tool_names),
            thinking=THINKING,
            output_config={"effort": spec.reasoning_effort},
        )
        cost += record_usage(spec.model, response)
        # Full content, so thinking blocks go back with their tool calls.
        transcript.append({"role": "assistant", "content": response.content})
        pending: list[dict] = []

        calls = [b for b in response.content if b.type == "tool_use"]
        if not calls:
            text = "".join(b.text for b in response.content if b.type == "text").strip()
            await _emit(on_event, {"type": "message", "step": step, "text": _short(text, 600), "cost": cost})
            return AgentResult("partial", text or "Agent stopped without reporting a result.", steps=step, cost=cost)

        for call in calls:
            args = call.input if isinstance(call.input, dict) else {}
            tool = TOOLS.get(call.name)
            try:
                if tool is None or tool.handler is None:
                    raise ValueError(f"Unknown tool {call.name}")
                output = await tool.handler(ctx, args)
            except Exception as exc:  # tool errors go back to the model, which can adapt
                output = f"Tool error: {type(exc).__name__}: {exc}"
            if len(output) > TOOL_OUTPUT_LIMIT:
                output = output[:TOOL_OUTPUT_LIMIT] + "\n… [truncated]"
            if call.name == "web_search":  # the event the hosted search produced
                await _emit(on_event, {"type": "tool", "step": step, "tool": "web_search",
                                       "args": str(args.get("query") or ""), "cost": cost})
            else:
                await _emit(on_event, {
                    "type": "tool", "step": step, "tool": call.name, "args": _short(args),
                    "result": _short(output, 500), "cost": cost,
                })
            pending.append({"type": "tool_result", "tool_use_id": call.id, "content": output})
        transcript.append({"role": "user", "content": pending})

        if ctx.credential_request is not None:
            c = ctx.credential_request
            return AgentResult("needs_credential", f"Needs {c['env_var']} for {c['service']}: {c['reason']}",
                               credential=c, steps=step, cost=cost)
        if ctx.result is not None:
            r = ctx.result
            return AgentResult(
                status=r.get("status", "success"), summary=r.get("summary", ""), artifacts=r.get("artifacts", []),
                metrics=r.get("metrics") or {}, issues=r.get("issues") or [], steps=step, cost=cost,
            )
        if cost >= spec.max_cost:
            return AgentResult("budget_exceeded", f"Stopped at the ${spec.max_cost:.2f} budget.", steps=step, cost=cost)

    return AgentResult("step_limit", f"Stopped after {spec.max_steps} steps.", steps=spec.max_steps, cost=cost)
