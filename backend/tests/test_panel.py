"""Review panel, conceptual audit, plan audit and reframing (offline; every model call is scripted).

Modelled on project 0c58935aa0be: a single reviewer called the headline result "analytically
exact", filed it as MINOR and scored 7; an outside referee showed the result follows from the
equation's scaling symmetry and that a sufficient condition was treated as the threshold."""

import asyncio

import pytest

from app import refine
from app.agents import judge
from app.agents import plan as plan_agent
from app.agents.judge import Evidence, IssueCheck, JudgeReport, RefereeReport, VerificationReport
from app.agents.plan import IssueDecision, PlanAudit, PlanProblem, RepairPlan, ResearchPlan
from app.config import settings
from study_fixture import research_plan
from test_judge import RESULTS_LINE, Handle, issue, report
from test_refinement import accept, blocking, env, loop, repair  # noqa: F401 (env is a fixture)

SCALING = Evidence(source="domain_knowledge", locator="scaling invariance of u_t = Δu + |u|^{p-1}u",
                   quote="u_λ(x,t) = λ^{2/(p-1)} u(λx, λ²t) solves the equation whenever u does",
                   observation="Rescaling the data by R gives a*(R) = a*(1) R^{-2/(p-1)} exactly.")


def trivial(ref="I1", severity="FATAL") -> object:
    return issue(ref, severity, category="novelty", origin="plan", title="Headline exponent follows from scaling symmetry",
                 evidence=[Evidence(source="manuscript", locator="L11", quote=RESULTS_LINE, observation="headline"),
                           SCALING])


def referee(*issues, score=9.0, upgrades=()) -> RefereeReport:
    return RefereeReport(field="semilinear parabolic PDE", established_theory=["Scaling invariance fixes the exponent."],
                         summary="Referee report.", score=score, score_rationale="Referee rationale.",
                         issues=list(issues), upgrades=list(upgrades))


def checks(**outcomes) -> VerificationReport:
    return VerificationReport(checks=[IssueCheck(ref=r, outcome=o, reason="checked by derivation", corrected_severity=s)
                                      for r, (o, s) in outcomes.items()])


@pytest.fixture
def panel(monkeypatch):
    monkeypatch.setattr(settings, "review_panel", True)


def review(study) -> dict:
    mistakes, _ = asyncio.run(judge.review(study.pid, Handle(), iteration=1))
    return mistakes


# ── Prompts ────────────────────────────────────────────────────────────────


def test_every_reviewer_does_the_conceptual_audit_and_grades_by_consequence():
    for text in (judge.JUDGE_INSTRUCTIONS, judge.REFEREE_INSTRUCTIONS):
        assert judge.CONCEPTUAL_AUDIT in text and judge.SEVERITY_CALIBRATION in text
        assert "{audit}" not in text and "{calibration}" not in text
    assert "never MINOR" in judge.SEVERITY_CALIBRATION
    assert "domain_knowledge" in judge.VERIFY_INSTRUCTIONS
    assert "established theory" in judge.JUDGE_SYSTEM


# ── Panel ──────────────────────────────────────────────────────────────────


def test_panel_finds_what_the_lead_missed_and_its_verified_fatal_issue_decides(env, panel):
    study, llm_, _ = env()
    fujita = issue("I1", "MINOR", category="statistics", title="Fujita boundary groups included in Wilcoxon test")
    llm_.add(JudgeReport, report([fujita], verdict="minor_revision", score=7.0))
    llm_.add(RefereeReport, referee(trivial(), score=2.0),
             referee(issue("I1", "MAJOR", category="statistics", title="Fujita boundary groups included in the Wilcoxon test"),
                     score=5.0))
    llm_.add(VerificationReport, checks(TH1=("confirmed", "FATAL"), ME1=("confirmed", "MAJOR")))
    m = review(study)
    assert llm_.kinds() == ["JudgeReport", "RefereeReport", "RefereeReport", "VerificationReport"]
    lead, theory, methods = (llm_.text(i) for i in range(3))
    assert "THEORY REFEREE" in theory and "METHODS REFEREE" in methods and "REFEREE" not in lead
    by_ref = {i["ref"]: i for i in m["issues"]}
    # The methods referee's MAJOR replaces the lead's MINOR on the same problem; FATAL first.
    assert list(by_ref) == ["TH1", "ME1"]
    assert by_ref["TH1"]["referee"] == "theory" and by_ref["TH1"]["blocking"]
    assert by_ref["TH1"]["evidence"][1]["verified"] is None  # domain knowledge is checked by reasoning
    assert by_ref["ME1"]["referee"] == "methods" and by_ref["ME1"]["blocking"]
    assert m["verdict"] == "reject" and m["score"] == 2.0 and m["score_claimed"] == 7.0
    assert next(r for r in m["rubric"] if r["criterion"] == "novelty")["assessment"] == "fatal"
    assert m["panel"]["theory"]["issues"] == ["TH1"] and m["referees"] == ["theory", "methods"]
    assert m["verdict_consistent"]


def test_a_refuted_referee_claim_neither_blocks_nor_sets_the_score(env, panel):
    study, llm_, _ = env()
    llm_.add(JudgeReport, report(verdict="accept", score=9.5))
    llm_.add(RefereeReport, referee(trivial(), score=2.0), referee(score=9.0))
    llm_.add(VerificationReport, checks(TH1=("refuted", "FATAL")))
    m = review(study)
    assert m["verdict"] == "accept" and m["score"] == 9.0  # the methods referee's 9.0, not the refuted 2.0
    assert not m["issues"][0]["blocking"] and m["issues"][0]["verification"] == "refuted"


def test_reviews_under_older_rules_are_never_reused(env, panel):
    study, llm_, _ = env()
    llm_.add(JudgeReport, accept(), accept())
    llm_.add(RefereeReport, referee(), referee(), referee(), referee())
    first = review(study)
    second, _ = asyncio.run(judge.review(study.pid, Handle(), iteration=2, previous=first))
    assert second.get("reused_from") == first["review_run_id"]  # same evidence, same rules
    third, _ = asyncio.run(judge.review(study.pid, Handle(), iteration=3, previous={**first, "rules": 1}))
    assert "reused_from" not in third and llm_.kinds().count("JudgeReport") == 2


def test_an_invalid_referee_report_is_retried_once_with_its_errors(env, panel):
    study, llm_, _ = env()
    bad = referee(issue("I1", "MAJOR", category="not_a_criterion"))
    llm_.add(JudgeReport, accept())
    llm_.add(RefereeReport, bad, referee(), referee())
    llm_.add(VerificationReport)
    review(study)
    tails = [m[0]["content"][-1]["text"] for k, m in llm_.calls if k == "RefereeReport"]
    assert len(tails) == 3
    retried = [t for t in tails if "YOUR PREVIOUS OUTPUT WAS INVALID" in t]
    assert len(retried) == 1 and "THEORY REFEREE" in retried[0] and "not_a_criterion" in retried[0]


# ── Reframing the question in a repair ─────────────────────────────────────


def test_a_trivial_question_is_reframed_at_the_plan_stage_and_recorded(env):
    study, llm_, lab = env()
    llm_.add(JudgeReport, blocking(trivial(), verdict="reject"), accept())
    llm_.add(VerificationReport, checks(I1=("confirmed", "FATAL")))
    new_question = "What is the sharp prefactor C(n,p,φ), and how far is it from the energy bound?"
    llm_.add(RepairPlan, repair([IssueDecision(issue_id="R1-01", disposition="fix", root_cause="plan", rationale="r")],
                                plan_revision="Study the sharp prefactor instead of the exponent.",
                                task_changes=[], blueprint_changes="Re-run the analysis for the prefactor.",
                                reframe=new_question))
    revised = research_plan()
    revised["research_question"] = new_question
    revised["hypothesis"] = "The sharp prefactor lies strictly below the energy bound."
    llm_.add(ResearchPlan, ResearchPlan.model_validate(revised))
    from app.agents.blueprint import BlueprintDelta
    llm_.add(BlueprintDelta, BlueprintDelta(add_tasks=[], replace_tasks=[], remove_task_ids=[], add_agents=[],
                                            add_datasets=[], add_python_packages=[], notes=[]))
    st = loop(study.pid)
    project = study.project()
    assert project.plan["research_question"] == new_question  # kept, not restored
    assert {"research_question", "hypothesis"} <= set(st["iterations"][0]["objective_changes"])
    amendments = project.settings["amendments"]
    assert amendments[-1]["task"] == "plan" and new_question in amendments[-1]["text"]
    reframe_call = next(m for k, m in llm_.calls if k == "ResearchPlan")
    assert "Reframe the question" in reframe_call[0]["content"]


def test_reframing_without_conceptual_grounds_is_rejected(env):
    study, llm_, _ = env()
    stats = issue("I1", "MAJOR", category="statistics", affected=["T3.1"])
    llm_.add(JudgeReport, blocking(stats))
    llm_.add(VerificationReport, checks(I1=("confirmed", "MAJOR")))
    sneaky = repair([IssueDecision(issue_id="R1-01", disposition="fix", root_cause="plan", rationale="r")],
                    plan_revision="Ask an easier question.", blueprint_changes="x", reframe="An easier question")
    llm_.add(RepairPlan, sneaky, sneaky)
    st = loop(study.pid)
    assert st["status"] == "attention" and "reframe is only for" in st["attention"]


def test_repair_plans_saved_before_reframe_existed_still_load():
    saved = repair([]).model_dump()
    del saved["reframe"]
    assert RepairPlan.model_validate({"reframe": "", **saved}).reframe == ""


# ── Plan audit before approval ─────────────────────────────────────────────


def audit(*problems) -> PlanAudit:
    return PlanAudit(field="semilinear heat equations", established_theory=["Scaling symmetry fixes the exponent."],
                     contribution="The sharp prefactor and its gap to the energy bound.", problems=list(problems))


FATAL_TRIVIAL = PlanProblem(severity="FATAL", kind="follows_from_known_theory",
                            problem="a*(R) ∝ R^{-2/(p-1)} follows from scaling.", fix="Study the sharp prefactor.")


def scripted_plan_calls(monkeypatch, *items):
    queue = list(items)
    calls = []

    async def parse(*, model, instructions, messages, schema, reasoning_effort="medium", tools=None, max_tokens=None):
        item = queue.pop(0)
        assert isinstance(item, schema), (schema, item)
        calls.append((schema.__name__, instructions, messages[-1]["content"]))
        return item

    monkeypatch.setattr(plan_agent, "parse", parse)
    return calls


def test_plan_audit_revises_a_trivial_question_and_audits_the_revision(monkeypatch):
    revised = ResearchPlan.model_validate({**research_plan(), "research_question": "Sharp prefactor?"})
    calls = scripted_plan_calls(monkeypatch, audit(FATAL_TRIVIAL), revised, audit())
    plan, record = asyncio.run(plan_agent._audited("CONTEXT", ResearchPlan.model_validate(research_plan()), Handle()))
    assert plan.research_question == "Sharp prefactor?" and record["revised"]
    assert record["first"]["problems"][0]["kind"] == "follows_from_known_theory" and record["final"]["problems"] == []
    assert [c[0] for c in calls] == ["PlanAudit", "ResearchPlan", "PlanAudit"]
    assert "follows_from_known_theory" in calls[1][2] and "Sharp prefactor?" in calls[2][2]


def test_a_sound_plan_is_audited_once_and_left_alone(monkeypatch):
    minor = PlanProblem(severity="MINOR", kind="other", problem="p", fix="f")
    calls = scripted_plan_calls(monkeypatch, audit(minor))
    original = ResearchPlan.model_validate(research_plan())
    plan, record = asyncio.run(plan_agent._audited("CONTEXT", original, Handle()))
    assert plan == original and not record["revised"] and len(calls) == 1


def test_a_revised_plan_marks_its_old_audit_stale():
    assert plan_agent.carried({"plan": {}, "audit": {"revised": False}})["audit"]["stale"] is True
    assert "audit" not in plan_agent.carried({"plan": {}})


def test_refine_reframe_categories_are_review_criteria():
    assert set(refine.REFRAME_CATEGORIES) <= set(judge.CRITERIA)
