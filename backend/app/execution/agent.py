"""Agent runtime: a Responses API tool-use loop with step and cost limits.

Conversation state is kept server-side via `previous_response_id`, so each step
only sends new tool outputs (cheaper than resending the transcript).
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from ..llm import client, record_usage
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


async def run_agent(spec: AgentSpec, task: str, ctx: ToolContext, on_event: Event | None = None) -> AgentResult:
    tool_names = [n for n in spec.tools if n in TOOLS]
    if "report_result" not in tool_names:
        tool_names.append("report_result")
    cost = 0.0
    previous: str | None = None
    pending: list[dict] = [{"role": "user", "content": task}]

    for step in range(1, spec.max_steps + 1):
        response = await client.responses.create(
            model=spec.model,
            instructions=spec.instructions,
            input=pending,
            tools=specs(tool_names),
            previous_response_id=previous,
            reasoning={"effort": spec.reasoning_effort},
            truncation="auto",  # long coding/training sessions drop the oldest context instead of failing
        )
        cost += record_usage(spec.model, response)
        previous = response.id
        pending = []

        for item in response.output:
            if item.type == "web_search_call":
                query = getattr(getattr(item, "action", None), "query", None)
                await _emit(on_event, {"type": "tool", "step": step, "tool": "web_search", "args": query or "", "cost": cost})

        calls = [o for o in response.output if o.type == "function_call"]
        if not calls:
            text = response.output_text.strip()
            await _emit(on_event, {"type": "message", "step": step, "text": _short(text, 600), "cost": cost})
            return AgentResult("partial", text or "Agent stopped without reporting a result.", steps=step, cost=cost)

        for call in calls:
            try:
                args = json.loads(call.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            tool = TOOLS.get(call.name)
            try:
                if tool is None or tool.handler is None:
                    raise ValueError(f"Unknown tool {call.name}")
                output = await tool.handler(ctx, args)
            except Exception as exc:  # tool errors go back to the model, which can adapt
                output = f"Tool error: {type(exc).__name__}: {exc}"
            if len(output) > TOOL_OUTPUT_LIMIT:
                output = output[:TOOL_OUTPUT_LIMIT] + "\n… [truncated]"
            await _emit(on_event, {
                "type": "tool", "step": step, "tool": call.name, "args": _short(args), "result": _short(output, 500),
                "cost": cost,
            })
            pending.append({"type": "function_call_output", "call_id": call.call_id, "output": output})

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
