"""Real Claude-on-Bedrock and Tavily calls through the app's own LLM and tool layers
(network; costs a little). Opt in with BEDROCK_INTEGRATION=1, which makes conftest keep
the AWS and Tavily keys from .env; usage rows go to the temporary test database.

    BEDROCK_INTEGRATION=1 uv run pytest tests/test_bedrock_integration.py -v -s
"""

import asyncio
import os
import uuid
from datetime import date

import httpx
import pytest
from sqlmodel import Session, select

from app import llm
from app.agents import plan as plan_agent
from app.agents.blueprint import RESOLVE_INSTRUCTIONS, Resolution
from app.agents.literature import EXTRACT_INSTRUCTIONS, PaperNotes
from app.config import settings
from app.db import Paper, Project, ProjectPaper, Run, Usage, engine
from app.execution.agent import AgentSpec, run_agent
from app.execution.orchestrator import COMMON_INSTRUCTIONS
from app.execution.tools import TOOLS, ToolContext
from app.jobs import RunHandle

pytestmark = pytest.mark.skipif(os.environ.get("BEDROCK_INTEGRATION") != "1",
                                reason="set BEDROCK_INTEGRATION=1 for real Bedrock/Tavily calls")

MODEL = settings.model_standard


@pytest.fixture
def run_id():
    rid = f"live-{uuid.uuid4().hex[:8]}"
    token = llm.current_run.set(rid)
    yield rid
    llm.current_run.reset(token)


def _rows(run_id: str) -> list[Usage]:
    with Session(engine) as s:
        return list(s.exec(select(Usage).where(Usage.run_id == run_id).order_by(Usage.created_at)))


def _report(name: str, run_id: str) -> None:
    rows = _rows(run_id)
    print(f"\n[{name}] model={MODEL} calls={len(rows)} in={sum(r.input_tokens for r in rows):,} "
          f"cached={sum(r.cached_tokens for r in rows):,} out={sum(r.output_tokens for r in rows):,} "
          f"searches={sum(r.web_searches for r in rows)} cost=${sum(r.cost for r in rows):.4f}")


def test_live_text_request(run_id):
    response = asyncio.run(llm.client.messages.create(
        model=MODEL, max_tokens=64, messages=[{"role": "user", "content": "Reply with exactly: OK"}]))
    llm.record_usage(MODEL, response)
    text = "".join(b.text for b in response.content if b.type == "text")
    assert response.stop_reason == "end_turn" and "OK" in text, (response.stop_reason, text)
    _report("text", run_id)


def test_live_structured_output(run_id):
    abstract = (
        "Title: Graph neural networks for molecular property prediction\nYear: 2021\nVenue: NeurIPS\n\nAbstract:\n"
        "We benchmark message-passing neural networks against random forests on 12 MoleculeNet datasets. "
        "GNNs improve ROC-AUC by 2.1 points on average but underperform on small datasets (<1,000 molecules). "
        "We release code and splits."
    )
    notes = asyncio.run(llm.parse(model=MODEL, instructions=EXTRACT_INSTRUCTIONS,
                                  messages=[{"role": "user", "content": abstract}], schema=PaperNotes,
                                  reasoning_effort="low"))
    assert isinstance(notes, PaperNotes) and notes.contribution and notes.methods
    print("\n", notes.model_dump_json(indent=1)[:600])
    _report("structured", run_id)


def test_live_streaming(run_id):
    async def go():
        return [d async for d in llm.stream_text(model=MODEL, instructions="Answer in one short sentence.",
                                                 messages=[{"role": "user", "content": "What is a p-value?"}])]

    deltas = asyncio.run(go())
    assert len(deltas) >= 1 and "".join(deltas).strip()
    print(f"\n{len(deltas)} deltas: {''.join(deltas)[:200]}")
    assert len(_rows(run_id)) == 1
    _report("stream", run_id)


def test_live_tool_use_cycle(run_id):
    """A real run_agent loop: tool_use → our handler → tool_result → report_result."""
    tools = ["lookup_resources", "read_webpage", "http_request", "search_papers", "post_note", "read_notes"]
    spec = AgentSpec(
        name="Data scout", model=MODEL, tools=tools, max_steps=6, reasoning_effort="low",
        instructions=COMMON_INSTRUCTIONS.format(name="Data scout", today=date.today().isoformat(),
                                                role="You find data sources for a study."),
    )
    task = ("Call lookup_resources with the query 'protein structure'. Then call report_result with status "
            "'success', a one-sentence summary naming the first resource returned, and artifacts [].")
    events: list[dict] = []

    async def go():
        async with httpx.AsyncClient() as http:
            return await run_agent(spec, task, ToolContext("live", None, http, agent_name="Data scout"),
                                   on_event=events.append)

    result = asyncio.run(go())
    print(f"\nstatus={result.status} steps={result.steps} summary={result.summary!r}")
    print("events:", [(e["type"], e.get("tool")) for e in events])
    assert result.status == "success" and result.steps >= 2
    assert [e.get("tool") for e in events if e["type"] == "tool"][:1] == ["lookup_resources"]
    rows = _rows(run_id)
    assert len(rows) == result.steps
    assert rows[-1].cached_tokens > 0, "later steps should read the cached transcript prefix"
    _report("tool loop", run_id)


def test_live_tavily_through_web_search_tool():
    async def go():
        async with httpx.AsyncClient() as http:
            return await TOOLS["web_search"].handler(ToolContext("live", None, http), {"query": "UniProt REST API"})

    import json

    results = json.loads(asyncio.run(go()))
    print("\n", [(r["title"], r["url"]) for r in results])
    assert results and all(r["url"].startswith("http") for r in results)


def test_live_structured_output_with_web_search(run_id):
    """The blueprint's dataset-resolve call: structured output with web_search (Tavily) in the loop."""
    datasets = [{"name": "MoleculeNet BBBP", "description": "Blood-brain barrier penetration labels",
                 "source": "to be located", "access": "public", "role": "benchmark"}]
    resolution = asyncio.run(llm.parse(
        model=MODEL, instructions=RESOLVE_INSTRUCTIONS,
        messages=[{"role": "user", "content": f"Research question: Do GNNs beat fingerprints on BBBP?\n\nDatasets:\n{datasets}"}],
        schema=Resolution, reasoning_effort="low", tools=[{"type": "web_search"}],
    ))
    print("\n", resolution.model_dump_json(indent=1)[:800])
    assert isinstance(resolution, Resolution) and len(resolution.datasets) == 1
    assert sum(r.web_searches for r in _rows(run_id)) >= 1, "the model should have searched"
    _report("parse+search", run_id)


def _seed_plan_project() -> str:
    """A project at the plan stage: brief, literature overview, three papers with notes, a chosen gap."""
    with Session(engine) as s:
        papers = [
            Paper(title=t, norm_title=t.lower(), year=y, authors=[a], notes={
                "contribution": c, "problem": c, "study_type": "empirical", "methods": m, "datasets": d,
                "tasks": ["molecular property prediction"], "metrics": ["ROC-AUC"], "key_findings": [c],
                "limitations": lim})
            for t, y, a, c, m, d, lim in [
                ("MoleculeNet: a benchmark for molecular machine learning", 2018, "Zhenqin Wu",
                 "Introduces MoleculeNet benchmark datasets.", ["random forest", "graph convolution"],
                 ["BBBP", "Tox21"], ["random splits overestimate performance"]),
                ("Analyzing learned molecular representations for property prediction", 2019, "Kevin Yang",
                 "D-MPNN outperforms fingerprints on most datasets.", ["D-MPNN", "Morgan fingerprints"],
                 ["BBBP", "ESOL"], ["few small-data comparisons"]),
                ("Do GNNs beat fingerprints on small molecular datasets?", 2022, "Ada Lovelace",
                 "Fingerprint models match GNNs below 1,000 molecules.", ["random forest", "GIN"],
                 ["BBBP"], ["single split", "no confidence intervals"]),
            ]
        ]
        project = Project(title="_live_plan", stage="plan", brief={
            "core_question": "Do graph neural networks outperform fingerprint baselines on small molecular datasets?",
            "summary": "Compare GNNs and fingerprint models on small MoleculeNet tasks with proper statistics.",
            "scope_in": ["MoleculeNet classification tasks", "scaffold splits"], "scope_out": ["wet-lab work"],
            "data_resources": "Public MoleculeNet datasets", "compute_resources": "Laptop CPU plus a small GPU budget",
            "user_expertise": "Graduate student in chemistry", "constraints": ["Under 10 GPU-hours"],
        })
        s.add(project)
        s.add_all(papers)
        s.commit()
        for p in papers:
            s.add(ProjectPaper(project_id=project.id, paper_id=p.id, included=True, relevance=3, score=1.0))
        lit = Run(project_id=project.id, kind="literature", status="done", result={"overview": {
            "summary": "", "themes": [], "common_methods": ["random forest", "D-MPNN"],
            "common_datasets": ["BBBP", "Tox21"], "open_problems": ["small-data regime understudied"]}})
        s.add(lit)
        s.commit()
        project.chosen_gap = {
            "id": "g1", "run_id": lit.id, "title": "GNNs vs fingerprints in the small-data regime",
            "question": "Below 1,000 molecules, do GNNs beat Morgan-fingerprint random forests on scaffold splits?",
            "hypothesis": "Fingerprint random forests match or beat GNNs below 1,000 training molecules.",
            "why_open": "Prior comparisons use random splits and lack confidence intervals.",
            "approach": "Subsample BBBP and Tox21 to 100-1,000 molecules; compare RF and GIN over 5 seeds.",
            "data_needed": "BBBP, Tox21", "compute_needed": "A few GPU-hours", "risks": ["noisy labels"],
            "supporting_paper_ids": [papers[2].id],
            "novelty_check": {"status": "partially_addressed", "explanation": "", "closest": [
                {"title": papers[2].title, "overlap": "Single split only"}]},
        }
        s.add(project)
        s.commit()
        return project.id


def test_live_master_plan_compile(run_id):
    """The blueprint compile call (MasterPlan, the schema too large for constrained decoding)
    with its real instructions, tool list and catalog, checked by the unchanged validator."""
    from app.agents.blueprint import COMPILE_INSTRUCTIONS, DEFAULT_BUDGET, MasterPlan, validate
    from app.execution import catalog
    from app.execution.tools import describe

    caps = {"python", "shell", "internet", "files", "cpu", "background", "conda"}
    plan = {"title": "GNNs vs fingerprints on small data", "research_question": "Do GNNs beat RF on <1k molecules?",
            "phases": [{"id": "P1", "name": "Data", "goal": "Get BBBP", "tasks": [
                {"id": "T1.1", "title": "Download BBBP", "description": "Fetch and clean BBBP.", "kind": "data_acquisition",
                 "inputs": [], "outputs": ["bbbp.csv"], "depends_on": [], "effort": "S", "tools_hint": ["pandas"]}]},
                {"id": "P2", "name": "Experiments", "goal": "Compare models", "tasks": [
                {"id": "T2.1", "title": "Train RF and GIN", "description": "5 seeds, 3 subsample sizes.",
                 "kind": "experiment", "inputs": ["bbbp.csv"], "outputs": ["results.csv"], "depends_on": ["T1.1"],
                 "effort": "M", "tools_hint": ["scikit-learn", "torch_geometric"]}]}],
            "datasets": [{"name": "BBBP", "description": "BBB labels", "source": "to be located", "access": "public",
                          "role": "benchmark"}]}
    context = (f"APPROVED PLAN:\n{plan}\n\nRESOLVED DATASETS:\n{{'datasets': [{{'name': 'BBBP', 'url': "
               f"'https://deepchemdata.s3-us-west-1.amazonaws.com/datasets/BBBP.csv'}}]}}\n\nTOOLS:\n{describe(caps)}\n\n"
               f"RUNTIME CAPABILITIES: {', '.join(sorted(caps))}\n\nBUDGET: $15.00 LLM, 5.0 GPU-hours\n\n"
               f"RESOURCE CATALOG:\n{catalog.summary()}")
    mp = asyncio.run(llm.parse(model=MODEL, instructions=COMPILE_INSTRUCTIONS,
                               messages=[{"role": "user", "content": context}], schema=MasterPlan,
                               reasoning_effort="medium"))
    errors, warnings = validate(mp, caps, DEFAULT_BUDGET)
    print(f"\nmaster plan: {len(mp.agents)} agents, {len(mp.tasks)} tasks; fallback={llm._GRAMMAR_FALLBACK.get(MasterPlan)}"
          f"; validation errors: {errors}")
    assert isinstance(mp, MasterPlan) and mp.tasks and mp.agents
    _report("master plan", run_id)


def test_live_research_plan_end_to_end(run_id):
    """plan.run unchanged: context → ResearchPlan (Claude structured output) → graph validation → citations."""
    pid = _seed_plan_project()
    with Session(engine) as s:
        run = Run(project_id=pid, kind="plan")
        s.add(run)
        s.commit()
        handle = RunHandle(run.id)
    token = llm.current_project.set(pid)
    try:
        result = asyncio.run(plan_agent.run(pid, handle))
    finally:
        llm.current_project.reset(token)
    plan, errors = plan_agent.parse_plan(result["plan"])
    tasks = [t for ph in plan.phases for t in ph.tasks]
    print(f"\nplan: {plan.title!r} — {len(plan.phases)} phases, {len(tasks)} tasks, graph errors: {errors}")
    assert errors == [] and len(plan.phases) >= 3 and tasks
    with Session(engine) as s:
        assert s.get(Run, run.id).counts == {"phases": len(plan.phases), "tasks": len(tasks)}
    _report("research plan", run_id)
