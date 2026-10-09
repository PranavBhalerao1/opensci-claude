"""LLM layer and agent loop contracts (app/llm.py, app/execution/agent.py), offline.

The provider is faked at the SDK client; everything above it is real. `Provider`
is the only provider-specific code in this file: the tests below it pin
OpenScientist's own behavior (statuses, error strings, truncation, events, usage
and cost rows, SSE frames) and must not change when the provider does.
"""

import asyncio
import hashlib
import json
import uuid
from types import SimpleNamespace as NS

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

import anthropic
import httpx2

from app import llm
from app.auth import CurrentUser, get_current_user
from app.config import settings
from app.db import BetaUser, Project, Usage, engine
from app.execution.agent import AgentSpec, run_agent
from app.execution.orchestrator import CheckResult, Verdict
from app.execution.tools import TOOLS, Tool, ToolContext, _obj
from app.sources import tavily

# ── Provider fake (Claude Messages API on Bedrock) ─────────────────────────

SEARCH_RESULTS = [{"title": "Result A", "url": "https://a.example.org/x", "content": "About A."}]


class _Stream:
    def __init__(self, events: list, final, error: str | None):
        self._events, self._final, self._error = events, final, error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    async def text_stream(self):
        for text in self._events:
            yield text
        if self._error:
            raise anthropic.APIError(self._error, httpx2.Request("POST", "https://bedrock.example"), body=None)

    async def get_final_message(self):
        return self._final


class Provider:
    """Scripted fake of the AsyncAnthropicBedrock client used by app.llm and the agent loop."""

    def __init__(self) -> None:
        self.script: list = []
        self.requests: list[dict] = []
        self.responses: list = []
        self.searches: list[str] = []
        self.messages_api = NS(create=self._create, stream=self._stream)

    def install(self, monkeypatch) -> None:
        monkeypatch.setattr(llm, "client", NS(messages=self.messages_api))

        async def search(client, query, limit=tavily.MAX_RESULTS):
            self.searches.append(query)
            return SEARCH_RESULTS

        monkeypatch.setattr(tavily, "search", search)

    @staticmethod
    def _usage(usage: tuple[int, int, int]):
        total, cached, out = usage
        return NS(input_tokens=total - cached, cache_read_input_tokens=cached, cache_creation_input_tokens=0,
                  output_tokens=out)

    def _message(self, content: list, stop_reason: str, usage) -> NS:
        return NS(id=f"msg_{len(self.script)}", content=content, stop_reason=stop_reason, usage=self._usage(usage))

    # Scripting
    def agent_turn(self, calls=(), text: str = "", searches=(), usage=(1000, 0, 100)) -> None:
        n = len(self.script)
        content = [NS(type="thinking", thinking="Planning.", signature=f"sig_{n}")]
        content += [NS(type="tool_use", id=f"toolu_{n}_s{i}", name="web_search", input={"query": q})
                    for i, q in enumerate(searches)]
        content += [NS(type="tool_use", id=f"toolu_{n}_{i}", name=name, input=args) for i, (name, args) in enumerate(calls)]
        if text:
            content.append(NS(type="text", text=text))
        tool_use = any(b.type == "tool_use" for b in content)
        self.script.append(self._message(content, "tool_use" if tool_use else "end_turn", usage))

    def parse_result(self, parsed, usage=(1000, 0, 100), searches=()) -> None:
        if searches:
            self.agent_turn(searches=searches, usage=usage)
            usage = (0, 0, 0)
        if parsed is None:  # declined: no structured output
            self.script.append(self._message([NS(type="text", text="I can't help with that.")], "refusal", usage))
        else:
            self.script.append(self._message([NS(type="thinking", thinking="ok", signature="s"),
                                              NS(type="text", text=parsed.model_dump_json())], "end_turn", usage))

    def stream_result(self, deltas, usage=(1000, 0, 100), error: str | None = None) -> None:
        final = self._message([NS(type="text", text="".join(deltas))], "end_turn", usage)
        self.script.append(_Stream(list(deltas), final, error))

    async def _create(self, **kw):
        self.requests.append(kw)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        self.responses.append(item)
        return item

    def _stream(self, **kw):
        self.requests.append(kw)
        return self.script.pop(0)

    # Inspection
    def model(self, i: int) -> str:
        return self.requests[i]["model"]

    def system(self, i: int) -> str:
        return self.requests[i]["system"]

    def messages(self, i: int) -> list[dict]:
        return self.requests[i]["messages"]

    def effort(self, i: int) -> str:
        return self.requests[i]["output_config"]["effort"]

    def tool_names(self, i: int) -> list[str]:
        return [t["name"] for t in self.requests[i].get("tools", [])]

    def call_ids(self, i: int) -> list[str]:
        return [b.id for b in self.responses[i].content if b.type == "tool_use"]

    def tool_results(self, i: int) -> list[tuple[str, str]]:
        last = self.requests[i]["messages"][-1]["content"]
        return [(b["tool_use_id"], b["content"]) for b in last if b.get("type") == "tool_result"]

    def continues(self, i: int) -> bool:
        """Request i carries the conversation so far (whatever the provider's mechanism)."""
        return any(m["role"] == "assistant" and m["content"] is self.responses[i - 1].content
                   for m in self.requests[i]["messages"])


# ── Fixtures and helpers ───────────────────────────────────────────────────


@pytest.fixture
def provider(monkeypatch):
    p = Provider()
    p.install(monkeypatch)
    return p


@pytest.fixture
def run_id():
    """Attribute usage rows to a fresh run id so each test can find its own."""
    rid = f"test-run-{uuid.uuid4().hex[:8]}"
    token = llm.current_run.set(rid)
    yield rid
    llm.current_run.reset(token)


def _usage_rows(run_id: str) -> list[Usage]:
    with Session(engine) as s:
        return list(s.exec(select(Usage).where(Usage.run_id == run_id).order_by(Usage.created_at)))


def _tavily_transport(seen: list | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if request.url.host == "api.tavily.com":
            return httpx.Response(200, json={"query": json.loads(request.content)["query"], "results": [
                {"title": "Result A", "url": "https://a.example.org/x", "content": "About A.", "score": 0.9},
                {"title": "Result B", "url": "https://b.example.org/y", "content": "About B.", "score": 0.5},
            ]})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


async def _agent(spec: AgentSpec, task: str = "Do the task.", sandbox=None, transport=None,
                 project_id: str = "proj-test"):
    events: list[dict] = []
    async with httpx.AsyncClient(transport=transport or _tavily_transport()) as http:
        ctx = ToolContext(project_id, sandbox or NS(secrets={}), http, agent_name=spec.name)
        result = await run_agent(spec, task, ctx, on_event=events.append)
    return result, events, ctx


def _spec(**kw) -> AgentSpec:
    return AgentSpec(**{"name": "Tester", "instructions": "You test.", "model": settings.model_standard,
                        "tools": ["echo", "boom"], **kw})


@pytest.fixture
def test_tools(monkeypatch):
    async def echo(ctx, a):
        return a["text"]

    async def boom(ctx, a):
        raise RuntimeError("boom")

    monkeypatch.setitem(TOOLS, "echo", Tool("echo", "Echo text back.", _obj({"text": {"type": "string"}}, ["text"]),
                                            (), echo))
    monkeypatch.setitem(TOOLS, "boom", Tool("boom", "Always fails.", _obj({}, []), (), boom))


REPORT = {"status": "success", "summary": "Did it.", "artifacts": [], "metrics": {"n": 3}, "issues": ["minor"]}


# ── run_agent: the tool loop ───────────────────────────────────────────────


def test_agent_runs_tools_in_order_and_returns_results_together(provider, test_tools, run_id):
    provider.agent_turn(calls=[("echo", {"text": "first"}), ("echo", {"text": "second"})])
    provider.agent_turn(calls=[("report_result", REPORT)])
    result, events, _ = asyncio.run(_agent(_spec()))

    assert (result.status, result.summary, result.artifacts, result.metrics, result.issues, result.steps) == (
        "success", "Did it.", [], {"n": 3}, ["minor"], 2)
    # Both outputs go back in the next request, in call order, keyed by the call ids.
    assert provider.tool_results(1) == list(zip(provider.call_ids(0), ["first", "second"]))
    assert provider.continues(1)
    assert len(provider.requests) == 2
    assert [(e["type"], e["step"], e["tool"], e["result"]) for e in events] == [
        ("tool", 1, "echo", "first"), ("tool", 1, "echo", "second"), ("tool", 2, "report_result", "Result recorded.")]
    assert events[0]["args"] == json.dumps({"text": "first"})
    assert all(e["cost"] == pytest.approx(events[0]["cost"]) for e in events[:2])
    assert result.cost == pytest.approx(sum(r.cost for r in _usage_rows(run_id)))


def test_agent_request_carries_spec(provider, test_tools):
    provider.agent_turn(calls=[("report_result", REPORT)])
    spec = _spec(tools=["echo", "not_a_tool"], reasoning_effort="low")
    asyncio.run(_agent(spec, task="The task text"))
    assert provider.model(0) == spec.model
    assert provider.system(0) == spec.instructions
    assert provider.effort(0) == "low"
    # Unknown tool names are dropped; report_result is always offered.
    assert provider.tool_names(0) == ["echo", "report_result"]


def test_agent_tool_errors_go_back_to_the_model(provider, test_tools):
    provider.agent_turn(calls=[("nope", {}), ("boom", {})])
    provider.agent_turn(calls=[("report_result", REPORT)])
    result, events, _ = asyncio.run(_agent(_spec()))
    outputs = [o for _, o in provider.tool_results(1)]
    assert outputs == ["Tool error: ValueError: Unknown tool nope", "Tool error: RuntimeError: boom"]
    assert result.status == "success"


def test_agent_truncates_long_tool_output(provider, test_tools):
    long = "x" * 20_000
    provider.agent_turn(calls=[("echo", {"text": long})])
    provider.agent_turn(calls=[("report_result", REPORT)])
    _, events, _ = asyncio.run(_agent(_spec()))
    (_, sent), = provider.tool_results(1)
    assert sent == "x" * 16_000 + "\n… [truncated]"
    assert events[0]["result"] == sent[:500] + "…"


def test_agent_without_tool_calls_returns_partial(provider, test_tools):
    provider.agent_turn(text="  All done.  ")
    result, events, _ = asyncio.run(_agent(_spec()))
    assert (result.status, result.summary, result.steps) == ("partial", "All done.", 1)
    assert events == [{"type": "message", "step": 1, "text": "All done.", "cost": result.cost}]


def test_agent_empty_reply_returns_partial_default(provider, test_tools):
    provider.agent_turn(text="")
    result, _, _ = asyncio.run(_agent(_spec()))
    assert (result.status, result.summary) == ("partial", "Agent stopped without reporting a result.")


def test_agent_credential_request_stops(provider, test_tools):
    provider.agent_turn(calls=[("request_credential", {"env_var": "ncbi_api_key", "service": "NCBI",
                                                       "reason": "higher rate limits"})])
    spec = _spec(tools=["request_credential"])
    result, _, _ = asyncio.run(_agent(spec))
    assert result.status == "needs_credential"
    assert result.summary == "Needs NCBI_API_KEY for NCBI: higher rate limits"
    assert result.credential == {"env_var": "NCBI_API_KEY", "service": "NCBI", "reason": "higher rate limits",
                                 "signup_url": None}
    assert result.steps == 1 and len(provider.requests) == 1


def test_agent_has_no_dollar_cap(provider, test_tools, run_id):
    # Each turn costs ~$4.95, far past any old per-task cap ($0.05-$0.30); with no
    # credit limit in play the agent keeps working until it reports.
    for text in ("a", "b", "c"):
        provider.agent_turn(calls=[("echo", {"text": text})], usage=(1_000_000, 0, 100_000))
    provider.agent_turn(calls=[("report_result", REPORT)])
    assert not hasattr(AgentSpec, "max_cost")
    result, _, _ = asyncio.run(_agent(_spec()))
    assert (result.status, result.steps) == ("success", 4)
    assert result.cost > 3 * 4.9
    assert result.cost == pytest.approx(sum(r.cost for r in _usage_rows(run_id)))
    assert len(_usage_rows(run_id)) == 4


def _capped_project(cap: float | None) -> tuple[str, str]:
    """A beta user with a USD cap and a project they own; returns (user_id, project_id)."""
    uid = str(uuid.uuid4())
    with Session(engine) as s:
        s.add(BetaUser(user_id=uid, approved=True, cap_usd=cap))
        p = Project(title="_credit_test", user_id=uid)
        s.add(p)
        s.commit()
        return uid, p.id


def _owned_agent(pid: str, spec: AgentSpec):
    token = llm.current_project.set(pid)  # as jobs.start does: usage is charged to the owner
    try:
        return asyncio.run(_agent(spec, project_id=pid))
    finally:
        llm.current_project.reset(token)


def test_agent_spends_past_old_task_caps_while_credits_remain(provider, test_tools, run_id):
    from app import beta

    uid, pid = _capped_project(100.0)
    provider.agent_turn(calls=[("echo", {"text": "a"})], usage=(1_000_000, 0, 100_000))
    provider.agent_turn(calls=[("report_result", REPORT)])
    result, _, _ = _owned_agent(pid, _spec())
    assert result.status == "success" and result.cost > 4.9
    rows = _usage_rows(run_id)
    assert len(rows) == 2 and all(r.user_id == uid for r in rows)
    assert beta.get_user_spend(uid) == pytest.approx(result.cost)  # credits consumed by actual cost
    assert beta.get_user_remaining(uid) == pytest.approx(100.0 - result.cost)


def test_agent_stops_when_owner_credits_run_out(provider, test_tools, run_id):
    from app import beta

    uid, pid = _capped_project(5.0)
    for text in ("a", "b", "c"):  # ~$4.95 each: step 2 crosses the $5 cap
        provider.agent_turn(calls=[("echo", {"text": text})], usage=(1_000_000, 0, 100_000))
    provider.agent_turn(calls=[("report_result", REPORT)])
    result, _, _ = _owned_agent(pid, _spec())
    assert (result.status, result.summary, result.steps) == ("credit_limit", beta.LIMIT_MESSAGE, 2)
    assert len(provider.requests) == 2  # checked before step 3: no further model call
    assert result.cost == pytest.approx(sum(r.cost for r in _usage_rows(run_id)))
    # Overshoot is bounded by the one call that was already in flight when credits ran out.
    assert 5.0 < beta.get_user_spend(uid) < 5.0 + 4.95 + 0.01
    assert beta.get_user_remaining(uid) == 0


def test_agent_with_no_credits_left_makes_no_call(provider, test_tools):
    uid, pid = _capped_project(1.0)
    with Session(engine) as s:
        s.add(Usage(project_id=pid, user_id=uid, model=settings.model_standard, cost=1.0))
        s.commit()
    result, _, _ = _owned_agent(pid, _spec())
    assert (result.status, result.steps, result.cost) == ("credit_limit", 0, 0.0)
    assert provider.requests == []


def test_agent_step_limit(provider, test_tools):
    provider.agent_turn(calls=[("echo", {"text": "a"})])
    provider.agent_turn(calls=[("echo", {"text": "b"})])
    result, _, _ = asyncio.run(_agent(_spec(max_steps=2)))
    assert (result.status, result.summary, result.steps) == ("step_limit", "Stopped after 2 steps.", 2)
    assert len(provider.requests) == 2


def test_agent_web_search_event_and_billing(provider, test_tools, run_id):
    provider.agent_turn(searches=["protein folding benchmarks"], calls=[("report_result", REPORT)],
                        usage=(2000, 0, 200))
    result, events, _ = asyncio.run(_agent(_spec(tools=["web_search"])))
    assert result.status == "success"
    first = events[0]
    assert first == {"type": "tool", "step": 1, "tool": "web_search", "args": "protein folding benchmarks",
                     "cost": first["cost"]}
    (row,) = _usage_rows(run_id)
    assert row.web_searches == 1
    assert row.cost == pytest.approx(llm.cost_of(settings.model_standard, 2000, 0, 200, 1))
    assert result.cost == pytest.approx(row.cost)


# ── parse: structured output ───────────────────────────────────────────────


def _verdict() -> Verdict:
    return Verdict(results=[CheckResult(check="file exists", passed=True, reason="It is listed.")])


def test_parse_returns_the_schema_object_and_records_usage(provider, run_id):
    provider.parse_result(_verdict(), usage=(100_000, 40_000, 10_000))
    msgs = [{"role": "user", "content": "Check this."}]
    out = asyncio.run(llm.parse(model=settings.model_standard, instructions="Verify.", messages=msgs,
                                schema=Verdict, reasoning_effort="low"))
    assert isinstance(out, Verdict) and out == _verdict()
    assert provider.model(0) == settings.model_standard
    assert provider.system(0) == "Verify."
    assert provider.messages(0) == msgs
    assert provider.effort(0) == "low"
    (row,) = _usage_rows(run_id)
    assert (row.model, row.input_tokens, row.cached_tokens, row.output_tokens, row.web_searches) == (
        settings.model_standard, 100_000, 40_000, 10_000, 0)
    p_in, p_cached, p_out = settings.model_prices[settings.model_standard]
    assert row.cost == pytest.approx((60_000 * p_in + 40_000 * p_cached + 10_000 * p_out) / 1e6)


def _owned_parse(pid: str, n: int = 1):
    """Run n parse calls one after another as the project's job would (usage charged to its owner)."""
    token = llm.current_project.set(pid)
    try:
        async def go():
            return [await llm.parse(model=settings.model_standard, instructions="Verify.",
                                    messages=[{"role": "user", "content": f"Check {i}."}], schema=Verdict)
                    for i in range(n)]
        return asyncio.run(go())
    finally:
        llm.current_project.reset(token)


def _project_rows(pid: str) -> list[Usage]:
    with Session(engine) as s:
        return list(s.exec(select(Usage).where(Usage.project_id == pid)))


EXPENSIVE = (100_000, 0, 30_000)  # $0.33 input + $0.495 output = $0.825 per call


def test_parse_refuses_before_any_request_when_credits_are_exhausted(provider):
    from app import beta

    uid, pid = _capped_project(1.0)
    with Session(engine) as s:
        s.add(Usage(project_id=pid, user_id=uid, model=settings.model_standard, cost=1.0))
        s.commit()
    provider.parse_result(_verdict())
    with pytest.raises(beta.BetaLimitReached, match="Beta usage limit reached"):
        _owned_parse(pid)
    assert provider.requests == []  # no Bedrock request was issued
    assert len(_project_rows(pid)) == 1 and beta.get_user_spend(uid) == pytest.approx(1.0)


def test_parse_call_that_uses_up_the_credit_blocks_the_next_one(provider):
    from app import beta

    uid, pid = _capped_project(0.5)
    provider.parse_result(_verdict(), usage=EXPENSIVE)
    provider.parse_result(_verdict(), usage=EXPENSIVE)
    (out,) = _owned_parse(pid)  # starts with $0.50 left; may finish past it
    assert out == _verdict()
    (row,) = _project_rows(pid)
    assert row.user_id == uid
    assert row.cost == pytest.approx(llm.cost_of(settings.model_standard, *EXPENSIVE)) == pytest.approx(0.825)
    assert beta.get_user_spend(uid) == pytest.approx(0.825) and beta.get_user_remaining(uid) == 0
    with pytest.raises(beta.BetaLimitReached):
        _owned_parse(pid)
    assert len(provider.requests) == 1 and len(_project_rows(pid)) == 1


def test_parse_calls_already_in_flight_are_not_cancelled(provider):
    from app import beta

    uid, pid = _capped_project(0.5)
    for _ in range(3):
        provider.parse_result(_verdict(), usage=EXPENSIVE)
    started: list[dict] = []
    gate = asyncio.Event()  # binds to the loop on first use
    original = provider.messages_api.create

    async def gated(**kw):  # hold every request until both calls are in flight
        started.append(kw)
        await gate.wait()
        return await original(**kw)

    provider.messages_api.create = gated

    async def scenario():
        calls = [asyncio.create_task(llm.parse(model=settings.model_standard, instructions="Verify.",
                                               messages=[{"role": "user", "content": f"Check {i}."}],
                                               schema=Verdict)) for i in range(2)]
        for _ in range(200):
            if len(started) == 2:
                break
            await asyncio.sleep(0.01)
        assert len(started) == 2  # both passed the credit check while $0.50 was left
        gate.set()
        return await asyncio.gather(*calls)

    token = llm.current_project.set(pid)
    try:
        outs = asyncio.run(scenario())
    finally:
        llm.current_project.reset(token)
    assert outs == [_verdict(), _verdict()]  # both completed despite the overshoot
    rows = _project_rows(pid)
    assert len(rows) == 2 and all(r.user_id == uid for r in rows)
    assert beta.get_user_spend(uid) == pytest.approx(2 * 0.825)  # every in-flight call is recorded
    with pytest.raises(beta.BetaLimitReached):  # but no new call may begin
        _owned_parse(pid)
    assert len(started) == 2


def test_parse_default_effort_is_medium(provider):
    provider.parse_result(_verdict())
    asyncio.run(llm.parse(model=settings.model_standard, instructions="x",
                          messages=[{"role": "user", "content": "y"}], schema=Verdict))
    assert provider.effort(0) == "medium"


def test_parse_without_structured_output_raises(provider):
    provider.parse_result(None)
    with pytest.raises(RuntimeError, match="Model returned no structured output"):
        asyncio.run(llm.parse(model=settings.model_standard, instructions="x",
                              messages=[{"role": "user", "content": "y"}], schema=Verdict))


def test_parse_with_web_search_bills_the_search(provider, run_id):
    provider.parse_result(_verdict(), searches=["dataset download page"])
    out = asyncio.run(llm.parse(model=settings.model_standard, instructions="Find sources.",
                                messages=[{"role": "user", "content": "Datasets: X"}], schema=Verdict,
                                reasoning_effort="low", tools=[{"type": "web_search"}]))
    assert out == _verdict()
    assert "web_search" in provider.tool_names(0)
    assert sum(r.web_searches for r in _usage_rows(run_id)) == 1


# ── stream_text: chat streaming ────────────────────────────────────────────


async def _collect(gen) -> list[str]:
    return [d async for d in gen]


def test_stream_yields_text_deltas_and_records_usage(provider, run_id):
    provider.stream_result(["Hel", "lo", "!"], usage=(500, 100, 50))
    msgs = [{"role": "user", "content": "Hi"}]
    out = asyncio.run(_collect(llm.stream_text(model=settings.model_standard, instructions="Be nice.", messages=msgs)))
    assert out == ["Hel", "lo", "!"]
    assert provider.system(0) == "Be nice." and provider.messages(0) == msgs
    assert provider.effort(0) == "low"
    (row,) = _usage_rows(run_id)
    assert (row.input_tokens, row.cached_tokens, row.output_tokens) == (500, 100, 50)


def test_stream_error_raises_runtime_error(provider):
    provider.stream_result(["partial"], error="overloaded")
    with pytest.raises(RuntimeError, match="overloaded"):
        asyncio.run(_collect(llm.stream_text(model=settings.model_standard, instructions="x",
                                             messages=[{"role": "user", "content": "y"}])))


def _sse(text: str) -> list[tuple[str, dict]]:
    frames = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        event, data = "message", []
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].strip())
        if data:
            frames.append((event, json.loads("\n".join(data))))
    return frames


def test_chat_route_streams_sse_frames(provider):
    from app.main import app

    uid = str(uuid.uuid4())
    with Session(engine) as s:
        s.add(BetaUser(user_id=uid, approved=True))
        p = Project(title="_chat_test", user_id=uid, stage="literature")
        s.add(p)
        s.commit()
        pid = p.id
    provider.stream_result(["Hi", " there"])
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=uid, email="chat@example.com")
    try:
        with TestClient(app) as client:
            r = client.post(f"/api/projects/{pid}/messages", json={"content": "hello"})
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    frames = _sse(r.text)
    assert [e for e, _ in frames] == ["message", "delta", "delta", "message", "done"]
    assert frames[0][1]["role"] == "user" and frames[0][1]["content"] == "hello"
    assert [d["text"] for e, d in frames if e == "delta"] == ["Hi", " there"]
    assert frames[3][1]["role"] == "assistant" and frames[3][1]["content"] == "Hi there"
    assert provider.messages(0) == [{"role": "user", "content": "hello"}]


# ── Usage and cost ─────────────────────────────────────────────────────────


def test_cost_formula():
    p_in, p_cached, p_out = settings.model_prices[settings.model_standard]
    assert llm.cost_of(settings.model_standard, 1_000_000, 250_000, 100_000, 3) == pytest.approx(
        (750_000 * p_in + 250_000 * p_cached + 100_000 * p_out) / 1e6 + 3 * settings.web_search_price)


def test_cost_of_unknown_model_uses_the_reasoning_tier_price():
    assert llm.cost_of("some-unknown-model", 10_000, 0, 1_000) == pytest.approx(
        llm.cost_of(settings.model_reasoning, 10_000, 0, 1_000))


# ── Tool registry ──────────────────────────────────────────────────────────

# sha256 of (description, requires, parameters) per tool, taken before the provider
# migration: only web_search may differ. run_gpu_jobs is the Google Colab spec (the only GPU provider).
REGISTRY = {
    "run_python": "202b8af858b3ec00", "run_shell": "3a119e8628ae7d87", "write_file": "ebcb480955a79280",
    "read_file": "40d618f07b9b6f8a", "list_files": "ca5a92d2fccac372", "edit_file": "8428c865eebfa0b7",
    "install_packages": "6ab290a7a14658c4", "install_conda_packages": "e37a2b639244f2d6",
    "start_process": "fdfa6600935b4509", "check_process": "7a747e16b106e8bc", "stop_process": "889c378dd7d42c13",
    "wait": "3e6ba88a3abee2eb", "read_webpage": "3bbb4fccea30c82d", "post_note": "26136dbd3f50cfc2",
    "read_notes": "9411dc89f70e250b", "request_credential": "0c31d1972c48da47",
    "spawn_subagents": "e2955b7c4db5659b", "http_request": "1c2fc8e6c3813de0", "download_file": "1cfd98292699f23f",
    "search_papers": "a1cc79f1f222cced", "lookup_resources": "15f565ad5f46ae8a", "run_gpu_jobs": "8fd3516dda47ce03",
    "report_result": "78947e1a5b5c00dc",
}
HANDLERS = {
    "run_python": "_run_python", "run_shell": "_run_shell", "write_file": "_write_file", "read_file": "_read_file",
    "list_files": "_list_files", "edit_file": "_edit_file", "install_packages": "_install",
    "install_conda_packages": "_install_conda", "start_process": "_start_process", "check_process": "_check_process",
    "stop_process": "_stop_process", "wait": "_wait", "read_webpage": "_read_webpage", "post_note": "_post_note",
    "read_notes": "_read_notes", "request_credential": "_request_credential", "spawn_subagents": "_spawn_subagents",
    "http_request": "_http_request", "download_file": "_download", "search_papers": "_search_papers",
    "lookup_resources": "_lookup_resources", "run_gpu_jobs": "_run_gpu_jobs", "report_result": "_report_result",
}


def test_tool_registry_unchanged_except_web_search():
    assert list(TOOLS) == [*list(REGISTRY)[:-1], "web_search", "report_result"]
    for name, digest in REGISTRY.items():
        t = TOOLS[name]
        got = hashlib.sha256(json.dumps([t.description, list(t.requires), t.parameters], sort_keys=True).encode())
        assert got.hexdigest()[:16] == digest, name
        assert t.handler.__name__ == HANDLERS[name], name
    ws = TOOLS["web_search"]
    assert (ws.description, ws.requires) == ("Search the web (hosted).", ("internet",))


# ── Claude / Bedrock adapter specifics ─────────────────────────────────────
# Provider-specific by design: how the adapter speaks the Messages API.


def test_client_uses_bedrock_settings():
    assert isinstance(llm.client, anthropic.AsyncAnthropicBedrock)
    assert llm.client.aws_region == settings.aws_region
    assert llm.client.aws_access_key == settings.aws_access_key_id
    assert llm.client.aws_secret_key == settings.aws_secret_access_key
    assert str(llm.client.base_url).startswith(f"https://bedrock-runtime.{settings.aws_region}.amazonaws.com")
    assert settings.model_standard == settings.model_reasoning == settings.model_bulk == "us.anthropic.claude-sonnet-4-6"


def test_model_tiers_default_to_bedrock_model_id_and_can_be_overridden():
    from app.config import Settings

    assert Settings(_env_file=None).model_standard == "us.anthropic.claude-sonnet-4-6"
    s = Settings(_env_file=None, bedrock_model_id="global.anthropic.claude-sonnet-4-6", model_bulk="custom-bulk")
    assert (s.model_reasoning, s.model_standard, s.model_bulk) == (
        "global.anthropic.claude-sonnet-4-6", "global.anthropic.claude-sonnet-4-6", "custom-bulk")


def test_agent_passes_thinking_and_tool_blocks_back(provider, test_tools):
    provider.agent_turn(calls=[("echo", {"text": "a"})])
    provider.agent_turn(calls=[("report_result", REPORT)])
    asyncio.run(_agent(_spec(), task="The task"))
    first, assistant, results = provider.messages(1)
    assert first["role"] == "user" and first["content"][0]["text"] == "The task"
    assert assistant == {"role": "assistant", "content": provider.responses[0].content}
    assert [b.type for b in assistant["content"]] == ["thinking", "tool_use"]
    assert results["role"] == "user" and [b["type"] for b in results["content"]] == ["tool_result"]
    assert provider.requests[0]["thinking"] == {"type": "adaptive"}
    assert all(set(t) == {"name", "description", "input_schema"} for t in provider.requests[0]["tools"])


def _breakpoints(messages: list[dict]) -> list[tuple[int, int]]:
    return [(i, j) for i, m in enumerate(messages) if isinstance(m["content"], list)
            for j, b in enumerate(m["content"]) if isinstance(b, dict) and "cache_control" in b]


def test_agent_caches_the_transcript_prefix(provider, test_tools):
    provider.agent_turn(calls=[("echo", {"text": "a"})])
    provider.agent_turn(calls=[("echo", {"text": "b"})])
    provider.agent_turn(calls=[("report_result", REPORT)])
    asyncio.run(_agent(_spec()))
    for i in range(3):
        msgs = provider.messages(i)
        # Exactly one breakpoint, on the final block: earlier ones never accumulate.
        assert _breakpoints(msgs) == [(len(msgs) - 1, len(msgs[-1]["content"]) - 1)]


def test_agent_web_search_runs_tavily_and_returns_results(provider, test_tools):
    provider.agent_turn(searches=["crystal structures"])
    provider.agent_turn(calls=[("report_result", REPORT)])
    asyncio.run(_agent(_spec(tools=["web_search"])))
    assert provider.searches == ["crystal structures"]
    assert provider.tool_results(1) == [(provider.call_ids(0)[0], json.dumps(SEARCH_RESULTS))]


def test_parse_enforces_the_schema_server_side(provider):
    provider.parse_result(_verdict())
    asyncio.run(llm.parse(model=settings.model_standard, instructions="x",
                          messages=[{"role": "user", "content": "y"}], schema=Verdict))
    req = provider.requests[0]
    assert req["output_config"] == {"effort": "medium", "format": {"type": "json_schema",
                                                                   "schema": anthropic.transform_schema(Verdict)}}
    assert req["thinking"] == {"type": "adaptive"} and "tools" not in req


def _final(text: str, stop: str = "end_turn") -> NS:
    return NS(id="m", content=[NS(type="text", text=text)], stop_reason=stop,
              usage=NS(input_tokens=10, cache_read_input_tokens=0, cache_creation_input_tokens=0, output_tokens=5))


@pytest.mark.parametrize("text, stop, match", [
    ('{"results": [{"check": "a"', "max_tokens", r"no structured output \(stop reason: max_tokens\)"),
    ("", "end_turn", "no structured output"),
    ('{"results": "nope"}', "end_turn", "invalid structured output"),
])
def test_parse_rejects_truncated_empty_or_invalid_output(provider, text, stop, match):
    provider.script.append(_final(text, stop))
    with pytest.raises(RuntimeError, match=match):
        asyncio.run(llm.parse(model=settings.model_standard, instructions="x",
                              messages=[{"role": "user", "content": "y"}], schema=Verdict))


def test_parse_search_loop_searches_first_and_must_answer_last(provider, monkeypatch, run_id):
    monkeypatch.setattr(llm, "SEARCH_ROUNDS", 2)
    provider.agent_turn(searches=["dataset portal"])
    provider.agent_turn(searches=["dataset portal download"])
    provider.parse_result(_verdict())
    out = asyncio.run(llm.parse(model=settings.model_standard, instructions="x",
                                messages=[{"role": "user", "content": "y"}], schema=Verdict,
                                tools=[{"type": "web_search"}]))
    assert out == _verdict() and provider.searches == ["dataset portal", "dataset portal download"]
    assert [r["tool_choice"] for r in provider.requests] == [{"type": "any"}, {"type": "auto"}, {"type": "none"}]
    assert all(r["thinking"] == {"type": "disabled"} for r in provider.requests)
    assert all(r["output_config"]["format"]["type"] == "json_schema" for r in provider.requests)
    (result,) = provider.messages(1)[-1]["content"]
    assert (result["content"], result["is_error"]) == (json.dumps(SEARCH_RESULTS), False)
    assert [r.web_searches for r in _usage_rows(run_id)] == [1, 1, 0]


def test_parse_search_errors_go_back_to_the_model(provider, monkeypatch):
    async def down(client, query, limit=5):
        raise RuntimeError("Web search is not configured (no TAVILY_API_KEY)")

    monkeypatch.setattr(tavily, "search", down)
    provider.agent_turn(searches=["x"])
    provider.parse_result(_verdict())
    asyncio.run(llm.parse(model=settings.model_standard, instructions="x", messages=[{"role": "user", "content": "y"}],
                          schema=Verdict, tools=[{"type": "web_search"}]))
    (result,) = provider.messages(1)[-1]["content"]
    assert result["is_error"] and result["content"] == (
        "Tool error: RuntimeError: Web search is not configured (no TAVILY_API_KEY)")


def _bad_request(message: str) -> anthropic.BadRequestError:
    request = httpx2.Request("POST", "https://bedrock-runtime.us-east-1.amazonaws.com/model/x/invoke")
    return anthropic.BadRequestError(message, response=httpx2.Response(400, request=request), body={"message": message})


TOO_LARGE = "The compiled grammar is too large, which would cause performance issues."


def _ask(schema=Verdict):
    return asyncio.run(llm.parse(model=settings.model_standard, instructions="x",
                                 messages=[{"role": "user", "content": "y"}], schema=schema))


def test_oversized_grammar_retries_without_thinking_and_remembers(provider, monkeypatch):
    monkeypatch.setattr(llm, "_GRAMMAR_FALLBACK", {})
    provider.script.append(_bad_request(TOO_LARGE))
    provider.parse_result(_verdict())
    provider.parse_result(_verdict())
    assert _ask() == _verdict() and _ask() == _verdict()
    thinking = [r["thinking"] for r in provider.requests]
    assert thinking == [{"type": "adaptive"}, {"type": "disabled"}, {"type": "disabled"}]
    # Still enforced by the API on every attempt.
    assert all(r["output_config"]["format"]["type"] == "json_schema" for r in provider.requests)


def test_grammar_still_too_large_uses_the_schema_as_a_forced_tool(provider, monkeypatch, run_id):
    monkeypatch.setattr(llm, "_GRAMMAR_FALLBACK", {})
    provider.script += [_bad_request(TOO_LARGE), _bad_request(TOO_LARGE)]
    tool_answer = NS(id="m", content=[NS(type="tool_use", id="t1", name="Verdict", input=_verdict().model_dump())],
                     stop_reason="tool_use", usage=NS(input_tokens=50, cache_read_input_tokens=0,
                                                      cache_creation_input_tokens=0, output_tokens=20))
    provider.script += [tool_answer, tool_answer]
    assert _ask() == _verdict() and _ask() == _verdict()
    assert len(provider.requests) == 4  # the second call goes straight to the tool form
    req = provider.requests[2]
    assert req["tool_choice"] == {"type": "tool", "name": "Verdict"} and req["thinking"] == {"type": "disabled"}
    assert req["tools"] == [{"name": "Verdict", "description": "Return the Verdict.",
                             "input_schema": anthropic.transform_schema(Verdict)}]
    assert "format" not in req["output_config"] and req["output_config"]["effort"] == "medium"
    assert len(_usage_rows(run_id)) == 2  # rejected requests are not billed rows


def test_forced_tool_output_is_still_validated(provider, monkeypatch):
    monkeypatch.setattr(llm, "_GRAMMAR_FALLBACK", {Verdict: "tool"})
    provider.script.append(NS(id="m", content=[NS(type="tool_use", id="t1", name="Verdict", input={"results": "x"})],
                              stop_reason="tool_use", usage=NS(input_tokens=1, cache_read_input_tokens=0,
                                                               cache_creation_input_tokens=0, output_tokens=1)))
    with pytest.raises(RuntimeError, match="invalid structured output"):
        _ask()


def test_other_bad_requests_are_not_swallowed(provider, monkeypatch):
    monkeypatch.setattr(llm, "_GRAMMAR_FALLBACK", {})
    provider.script.append(_bad_request("messages: text content blocks must be non-empty"))
    with pytest.raises(anthropic.BadRequestError, match="non-empty"):
        _ask()
    assert llm._GRAMMAR_FALLBACK == {}


def test_record_usage_counts_cache_reads_and_writes(run_id):
    response = NS(content=[], usage=NS(input_tokens=1_000, cache_read_input_tokens=50_000,
                                       cache_creation_input_tokens=4_000, output_tokens=2_000))
    cost = llm.record_usage(settings.model_standard, response)
    (row,) = _usage_rows(run_id)
    assert (row.input_tokens, row.cached_tokens, row.output_tokens) == (55_000, 50_000, 2_000)
    p_in, p_cached, p_out = settings.model_prices[settings.model_standard]
    assert cost == pytest.approx((5_000 * p_in + 50_000 * p_cached + 2_000 * p_out + 4_000 * p_in * 0.25) / 1e6)


def test_empty_turns_are_dropped(provider):
    provider.stream_result(["ok"])
    history = [{"role": "user", "content": "a"}, {"role": "assistant", "content": ""}, {"role": "user", "content": "b"}]
    asyncio.run(_collect(llm.stream_text(model=settings.model_standard, instructions="x", messages=history)))
    assert provider.messages(0) == [{"role": "user", "content": "a"}, {"role": "user", "content": "b"}]


# ── web_search backend (Tavily over httpx) ─────────────────────────────────


def test_tavily_search_request_and_result_shape(monkeypatch):
    monkeypatch.setattr(settings, "tavily_api_key", "tvly-test")
    seen: list[httpx.Request] = []

    async def go():
        async with httpx.AsyncClient(transport=_tavily_transport(seen)) as http:
            return await TOOLS["web_search"].handler(ToolContext("p", None, http), {"query": "graphene thermal"})

    out = json.loads(asyncio.run(go()))
    assert out == [{"title": "Result A", "url": "https://a.example.org/x", "content": "About A."},
                   {"title": "Result B", "url": "https://b.example.org/y", "content": "About B."}]
    (req,) = seen
    assert (req.method, str(req.url)) == ("POST", "https://api.tavily.com/search")
    assert req.headers["authorization"] == "Bearer tvly-test"
    assert json.loads(req.content) == {"query": "graphene thermal", "max_results": 5}


def test_tavily_without_key_raises():
    with pytest.raises(RuntimeError, match="no TAVILY_API_KEY"):
        asyncio.run(tavily.search(httpx.AsyncClient(), "x"))


def test_tavily_http_errors_raise(monkeypatch):
    monkeypatch.setattr(settings, "tavily_api_key", "tvly-bad")
    transport = httpx.MockTransport(lambda r: httpx.Response(401, json={"detail": {"error": "Unauthorized"}}))

    async def go():
        async with httpx.AsyncClient(transport=transport) as http:
            return await tavily.search(http, "x")

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(go())


def test_web_search_spec():
    assert TOOLS["web_search"].spec() == {
        "name": "web_search", "description": "Search the web (hosted).",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"],
                         "additionalProperties": False}}
