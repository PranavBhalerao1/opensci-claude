"""Report-stage claims verification (app/agents/report.py), offline.

The fallback claims audit must run for any report the independent-review loop is not about
to check itself — including a paper regenerated after an earlier, now-stale review — and must
never run twice for a report the review loop IS about to check (see app/refine.py's
will_review, which this exercises end to end through the real report.run()).
"""

import asyncio

import pytest

from app.agents import report as report_agent
from app.agents.report import Audit, AuditIssue, Scaffold
from app.execution.agent import AgentResult
from study_fixture import make_study

SCAFFOLD = Scaffold(title="t", one_sentence_summary="s", hypothesis_verdict="supported", verdict_explanation="",
                    findings=[], success_criteria=[], figures=[], tables=[], limitations=[], deviations=[],
                    outline=[], reproducibility=[], writing_instructions="")


class Handle:
    def phase(self, phase, text=None):
        pass

    def note(self, text):
        pass

    def counts(self, **kw):
        pass


@pytest.fixture
def study(tmp_path, monkeypatch):
    s = make_study(tmp_path, monkeypatch, refinement=None)
    yield s
    s.cleanup()


def _fake_agent(monkeypatch, study):
    async def run_agent(spec, prompt, ctx, on_event=None):
        study.write_paper()
        return AgentResult("success", "wrote the paper", artifacts=["paper/paper.tex", "paper/paper.pdf"])

    monkeypatch.setattr(report_agent, "run_agent", run_agent)


def _fake_parse(monkeypatch):
    calls: list[str] = []

    async def parse(*, schema, reasoning_effort, **kw):
        calls.append(schema.__name__)
        if schema is Scaffold:
            return SCAFFOLD
        if schema is Audit:
            return Audit(issues=[AuditIssue(claim="x", problem="y", severity="low")])
        raise AssertionError(f"unexpected schema {schema}")

    monkeypatch.setattr(report_agent, "parse", parse)
    return calls


def test_refinement_never_enabled_runs_the_fallback_audit(study, monkeypatch):
    _fake_agent(monkeypatch, study)
    calls = _fake_parse(monkeypatch)
    out = asyncio.run(report_agent.run(study.pid, Handle()))
    assert calls.count("Audit") == 1
    assert out["audit"] == [{"claim": "x", "problem": "y", "severity": "low"}]


@pytest.mark.parametrize("status", ["approved", "unresolved", "budget_exhausted", "stopped"])
def test_regenerating_a_previously_reviewed_paper_still_gets_a_claims_check(study, monkeypatch, status):
    """The old approval must not silently cover a new version of the paper: report.run() must
    run its own fallback audit for a report whose review session already concluded."""
    study.update(review={"status": status, "started_at": "2024-01-01T00:00:00+00:00"})
    _fake_agent(monkeypatch, study)
    calls = _fake_parse(monkeypatch)
    out = asyncio.run(report_agent.run(study.pid, Handle()))
    assert calls.count("Audit") == 1
    assert out["audit"] == [{"claim": "x", "problem": "y", "severity": "low"}]


@pytest.mark.parametrize("status", ["reviewing", "repairing", "attention", "review_failed"])
def test_a_report_the_review_loop_will_check_skips_the_duplicate_audit(study, monkeypatch, status):
    study.update(review={"status": status, "started_at": "2024-01-01T00:00:00+00:00"})
    _fake_agent(monkeypatch, study)
    calls = _fake_parse(monkeypatch)
    out = asyncio.run(report_agent.run(study.pid, Handle()))
    assert "Audit" not in calls
    assert out["audit"] == []


def test_a_freshly_enabled_review_about_to_start_skips_the_duplicate_audit(study, monkeypatch):
    study.update(settings={**study.project().settings, "refinement": {"enabled": True}})
    _fake_agent(monkeypatch, study)
    calls = _fake_parse(monkeypatch)
    out = asyncio.run(report_agent.run(study.pid, Handle()))
    assert "Audit" not in calls
    assert out["audit"] == []


def test_a_consolidation_that_was_all_reasoning_is_retried_once_at_medium_effort(study, monkeypatch):
    """The galaxy report: the whole output budget spent reasoning, no scaffold written."""
    _fake_agent(monkeypatch, study)
    efforts: list[str] = []

    async def parse(*, schema, reasoning_effort, instructions, **kw):
        if schema is Scaffold:
            efforts.append(reasoning_effort)
            if len(efforts) == 1:
                raise report_agent.llm.OutputLimitReached("all reasoning", thinking_only=True)
            assert instructions.endswith(report_agent.llm.BRIEF_REASONING)
            return SCAFFOLD
        return Audit(issues=[])

    monkeypatch.setattr(report_agent, "parse", parse)
    asyncio.run(report_agent.run(study.pid, Handle()))
    assert efforts == ["high", "medium"]


@pytest.mark.parametrize("name, schema", [("vague_research_plan.json", "openscientist.vague_research_plan/v1"),
                                          ("master_plan.json", "openscientist.master_plan/v1"),
                                          ("context.json", None)])
def test_plan_exports_wiped_by_a_restart_are_rebuilt_from_the_database(study, name, schema):
    import json

    from app.agents import plan as plan_agent

    path = plan_agent.export_path(study.pid, name)  # never written: as after a restart wiped the disk
    assert path is not None and path.is_file()
    doc = json.loads(path.read_text())
    if schema:
        assert doc["schema"] == schema and "run_id" not in doc


def test_packaging_a_workspace_that_is_gone_is_reported_not_crashed(study):
    import shutil

    from app.execution.sandbox import sandbox_for

    shutil.rmtree(sandbox_for(study.pid).root, ignore_errors=True)
    assert not report_agent.has_files(study.pid)
