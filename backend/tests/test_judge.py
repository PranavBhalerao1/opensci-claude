"""Independent scientific judge (app/agents/judge.py), offline: the Bedrock client is scripted."""

import asyncio
import json
from types import SimpleNamespace as NS

import anthropic
import httpx2
import pytest

from app import llm
from app.agents import judge
from app.agents.judge import Evidence, IssueCheck, JudgeIssue, JudgeReport, RubricItem, VerificationReport
from study_fixture import SENTINELS, TEX, make_study, png
from test_llm import Provider, _Stream

REQUEST = httpx2.Request("POST", "https://bedrock-runtime.us-east-1.amazonaws.com/model/m/invoke")
RESULTS_LINE = "Method M reached an accuracy of 0.912 versus 0.874 for B (p = 0.031)."


class Handle:
    def __init__(self):
        self.notes: list[str] = []

    def phase(self, phase, text=None):
        self.notes.append(f"{phase}: {text}")

    def note(self, text):
        self.notes.append(text)


def rubric(skip: str | None = None) -> list[RubricItem]:
    return [RubricItem(criterion=c, assessment="sound", note="ok") for c in judge.CRITERIA if c != skip]


def issue(ref="I1", severity="MAJOR", quote=RESULTS_LINE, source="manuscript", locator="L11", **kw) -> JudgeIssue:
    fields = dict(ref=ref, severity=severity, category="statistics", certainty="demonstrated",
                  title=f"Problem {ref}", description="A paired t-test on one seed pair is invalid.",
                  evidence=[Evidence(source=source, locator=locator, quote=quote, observation="o")],
                  absence_terms=[], why_it_matters="The p-value is meaningless.",
                  corrective_action="Re-run the test across all seeds.", origin="analysis",
                  affected=["T3.1"], invalidates=["analysis/stats.csv"], evidence_needed="", requested_files=[])
    fields.update(kw)
    return JudgeIssue(**fields)


def report(issues=(), verdict="accept", rubric_items=None, score=10.0, upgrades=()) -> JudgeReport:
    return JudgeReport(summary="Reviewed.", score=score, score_rationale="Solid.", objective_alignment="answers",
                       objective_alignment_note="", hypothesis_support="supported",
                       rubric=rubric_items or rubric(), issues=list(issues), verdict=verdict,
                       upgrades=list(upgrades))


def garbage(provider: Provider, text="not json at all") -> None:
    provider.script.append(provider._message([NS(type="text", text=text)], "end_turn", (100, 0, 10)))


@pytest.fixture
def provider(monkeypatch):
    p = Provider()
    p.install(monkeypatch)
    monkeypatch.setattr(judge, "RETRY_DELAY", 0)
    monkeypatch.setattr(llm, "_LONG_REFUSED", set())
    return p


@pytest.fixture
def study(tmp_path, monkeypatch):
    s = make_study(tmp_path, monkeypatch)
    yield s
    s.cleanup()


def run(study, **kw):
    return asyncio.run(judge.review(study.pid, Handle(), iteration=kw.pop("iteration", 2), **kw))


def request_text(req: dict) -> str:
    return json.dumps([b.get("text", "") for m in req["messages"] for b in m["content"]] + [req["system"]])


# ── Request construction and independence ──────────────────────────────────


def test_request_is_one_fresh_message_with_numbered_manuscript_and_figures(study, provider):
    study.update(review={"preregistration": judge.preregistration_of(study.project().plan),
                         "directives": {"T-001": "SENTINEL_DIRECTIVE"}})
    provider.parse_result(report())
    mistakes, bundle = run(study)
    assert len(provider.requests) == 1
    req = provider.requests[0]
    assert req["system"].endswith(judge.JUDGE_SYSTEM)  # behind the standing identity rule
    assert [m["role"] for m in req["messages"]] == ["user"]
    content = req["messages"][0]["content"]
    texts = [b["text"] for b in content if b["type"] == "text"]
    assert any("L0011 " + RESULTS_LINE in t for t in texts)
    images = [b for b in content if b["type"] == "image"]
    assert len(images) == 1 and images[0]["source"]["media_type"] == "image/png"
    assert all(not k.startswith("_") for b in content for k in b)
    assert texts[-1].startswith(judge.JUDGE_INSTRUCTIONS[:40])
    assert req["output_config"]["effort"] == "high"
    for sid in ("objective", "preregistration", "plan_current", "protocol_amendments", "execution_record",
                "manuscript", "figure:figures/main.png", "artifact:results/SUMMARY.md", "artifact:analysis/stats.csv",
                "code:scripts/plot.py", "code:src/stats.py", "literature:smith2020data", "integrity", "omissions"):
        assert sid in bundle.sources, sid
    assert "five seeds" in bundle.sources["literature:smith2020data"].text  # abstract of the cited paper
    assert mistakes["verdict"] == "accept" and mistakes["issues"] == [] and mistakes["grammar_mode"] == "default"
    assert mistakes["inputs"]["bundle_sha256"] == bundle.sha256


def test_judge_never_sees_pipeline_self_assessments_or_review_history(study, provider):
    study.update(review={"directives": {"T-001": "SENTINEL_DIRECTIVE"}})
    provider.parse_result(report())
    run(study)
    text = request_text(provider.requests[0])
    for s in SENTINELS:
        assert s not in text, s
    assert "Use 5 seeds" in text and "R1-02" not in text  # amendments kept, review ids stripped


def test_integrity_gate_failure_skips_the_judge(study, provider):
    (study.root / "paper" / "paper.pdf").unlink()
    mistakes, bundle = run(study)
    assert provider.requests == [] and bundle is None
    assert mistakes["judged"] is False
    assert [i["id"] for i in mistakes["issues"]] == ["R2-P1"] and mistakes["issues"][0]["blocking"]


def test_unchanged_evidence_reuses_the_last_valid_review(study, provider):
    provider.parse_result(report())
    first, _ = run(study)
    again, _ = run(study, previous={**first, "review_run_id": "old"}, iteration=3)
    assert len(provider.requests) == 1 and again["reused_from"] == "old" and again["iteration"] == 3


def test_visual_and_text_budgets_are_enforced_and_listed(study, provider, monkeypatch):
    monkeypatch.setattr(judge, "VISUAL_BYTES", 10)
    monkeypatch.setattr(judge, "TEXT_BUDGET", 1000)
    provider.parse_result(report())
    mistakes, bundle = run(study)
    assert bundle.visuals == [] and {"path": "figures/main.png", "reason": "larger than 3.75 MB"} in bundle.omitted
    omitted = {o["path"] for o in mistakes["inputs"]["omitted"]}
    assert "analysis/stats.csv" in omitted and "omissions" in bundle.sources
    assert "analysis/stats.csv" in bundle.sources["omissions"].text


# ── Validation, retries, failures ──────────────────────────────────────────


def test_incomplete_rubric_is_retried_once_with_the_errors(study, provider):
    provider.parse_result(report(rubric_items=rubric(skip="novelty")))
    provider.parse_result(report())
    mistakes, _ = run(study)
    assert len(provider.requests) == 2 and mistakes["valid"]
    assert "YOUR PREVIOUS OUTPUT WAS INVALID" in provider.requests[1]["messages"][0]["content"][-1]["text"]
    assert "novelty" in provider.requests[1]["messages"][0]["content"][-1]["text"]


def test_malformed_output_twice_fails_the_review(study, provider):
    garbage(provider)
    garbage(provider, '{"summary": 1}')
    with pytest.raises(judge.ReviewFailed):
        run(study)


def test_truncated_output_retries_with_less_effort(study, provider):
    provider.script.append(provider._message([NS(type="text", text='{"summ')], "max_tokens", (100, 0, 10)))
    provider.parse_result(report())
    run(study)
    assert [provider.effort(i) for i in range(2)] == ["high", "medium"]


def test_bedrock_outage_gets_one_retry_then_fails(study, provider):
    provider.script += [anthropic.APIConnectionError(request=REQUEST)]
    provider.parse_result(report())
    mistakes, _ = run(study)
    assert mistakes["valid"] and len(provider.requests) == 2
    provider.script += [anthropic.APIConnectionError(request=REQUEST), anthropic.APIConnectionError(request=REQUEST)]
    with pytest.raises(judge.ReviewFailed, match="temporarily unavailable"):
        run(study)


# ── Grounding, verification, blocking ──────────────────────────────────────


def test_grounding_cases(study):
    gates = judge.integrity.check(study.pid, study.root)
    b = judge.build_bundle(study.pid, gates, study.root)
    cases = {
        "verified": issue(),
        "unverified": issue(quote="Method M reached 0.99 accuracy"),
        "out_of_range": issue(locator="L1-L2"),
        "artifact": issue(source="artifact:analysis/stats.csv", locator="row 1", quote="accuracy,0.912,0.874,0.031"),
        "unknown_source": issue(source="artifact:nope.csv", locator="", quote="x"),
        "figure": issue(source="figure:figures/main.png", locator="", quote=""),
        "absence_ok": issue(evidence=[], absence_terms=["random baseline"]),
        "absence_contradicted": issue(evidence=[], absence_terms=["paired t-test"]),
    }
    got = {k: judge.ground(v, b)[0] for k, v in cases.items()}
    assert got == {"verified": "verified", "unverified": "unverified", "out_of_range": "unverified",
                   "artifact": "verified", "unknown_source": "unverified", "figure": "visual",
                   "absence_ok": "absence_ok", "absence_contradicted": "absence_contradicted"}
    two = issue(evidence=[Evidence(source="manuscript", locator="L11", quote=RESULTS_LINE, observation=""),
                          Evidence(source="manuscript", locator="L11", quote="made up", observation="")])
    assert judge.ground(two, b)[0] == "partial"


@pytest.mark.parametrize("severity,certainty,grounding,check,verification,blocking,open_concern", [
    ("FATAL", "demonstrated", "verified", "confirmed", "ok", True, False),
    ("FATAL", "demonstrated", "verified", "refuted", "ok", False, False),
    ("MAJOR", "likely", "verified", "uncertain", "ok", False, True),
    ("MAJOR", "uncertain", "verified", "confirmed", "ok", True, False),
    ("MINOR", "demonstrated", "verified", "confirmed", "ok", False, False),
    ("MAJOR", "demonstrated", "verified", None, "failed", True, False),      # conservative fallback
    ("MAJOR", "demonstrated", "unverified", None, "failed", False, True),
    ("FATAL", "uncertain", "verified", None, "failed", False, True),
    ("MAJOR", "likely", "absence_contradicted", None, "disabled", False, True),
    ("MAJOR", "demonstrated", "verified", None, "ok", True, False),          # verifier skipped this issue
])
def test_blocking_table(severity, certainty, grounding, check, verification, blocking, open_concern):
    d = {"severity": severity, "certainty": certainty, "grounding": grounding}
    c = IssueCheck(ref="I1", outcome=check, reason="r", corrected_severity=severity) if check else None
    judge.classify(d, c, verification)
    assert (d["blocking"], d["open_concern"]) == (blocking, open_concern)


def test_verification_downgrades_never_upgrades(study):
    d = {"severity": "FATAL", "certainty": "demonstrated", "grounding": "verified"}
    judge.classify(d, IssueCheck(ref="I1", outcome="confirmed", reason="", corrected_severity="MINOR"), "ok")
    assert d["severity"] == "MINOR" and d["severity_claimed"] == "FATAL" and not d["blocking"]
    d = {"severity": "MAJOR", "certainty": "demonstrated", "grounding": "verified"}
    judge.classify(d, IssueCheck(ref="I1", outcome="confirmed", reason="", corrected_severity="FATAL"), "ok")
    assert d["severity"] == "MAJOR" and d["blocking"]


def test_serious_claims_are_verified_by_a_second_fresh_call(study, provider):
    provider.parse_result(report([issue("I1", "FATAL"), issue("I2", "MAJOR", quote="fabricated quote"),
                                  issue("I3", "MINOR")], verdict="reject"))
    provider.parse_result(VerificationReport(checks=[
        IssueCheck(ref="I1", outcome="confirmed", reason="seen", corrected_severity="FATAL"),
        IssueCheck(ref="I2", outcome="refuted", reason="no such text", corrected_severity="MAJOR")]))
    mistakes, _ = run(study)
    assert len(provider.requests) == 2
    verify = provider.requests[1]
    assert verify["system"].endswith(judge.JUDGE_SYSTEM) and len(verify["messages"]) == 1
    tail = verify["messages"][0]["content"][-1]["text"]
    assert "CLAIMED ISSUES" in tail and '"GROUNDING": "unverified"' in tail and "I3" not in tail
    by_id = {i["id"]: i for i in mistakes["issues"]}
    assert by_id["R2-01"]["blocking"] and by_id["R2-01"]["verification"] == "confirmed"
    assert not by_id["R2-02"]["blocking"] and by_id["R2-02"]["verification"] == "refuted"
    assert by_id["R2-03"]["verification"] == "not_needed"
    assert mistakes["verdict_consistent"] and mistakes["verification"] == "ok"


def test_failed_verification_falls_back_to_the_conservative_rule(study, provider):
    provider.parse_result(report([issue("I1", "MAJOR"), issue("I2", "MAJOR", quote="not in the paper")],
                                 verdict="major_revision"))
    garbage(provider)
    mistakes, _ = run(study)
    by_id = {i["id"]: i for i in mistakes["issues"]}
    assert by_id["R2-01"]["blocking"] and not by_id["R2-02"]["blocking"] and by_id["R2-02"]["open_concern"]
    assert mistakes["verification"] == "failed"


def test_reject_without_verified_issues_triggers_one_fresh_rejudge(study, provider):
    provider.parse_result(report(verdict="reject"))
    provider.parse_result(report(verdict="accept"))
    mistakes, _ = run(study)
    assert len(provider.requests) == 2 and mistakes["rejudged"] and mistakes["verdict_consistent"]
    provider.parse_result(report(verdict="reject"))
    provider.parse_result(report(verdict="major_revision"))
    mistakes, _ = run(study)
    assert mistakes["rejudged"] and not mistakes["verdict_consistent"]


def test_iteration_files_are_written_outside_the_workspace(study, provider):
    provider.parse_result(report())
    mistakes, bundle = run(study)
    out = judge.write_iteration_files(study.pid, 2, mistakes, bundle, study.root)
    assert out == study.exports / study.pid / "review" / "iter-2"
    assert json.loads((out / "mistakes.json").read_text())["schema"] == "openscientist.mistakes/v1"
    assert (out / "paper.tex").is_file() and (out / "paper.pdf").is_file() and "[IMAGE figures/main.png" in (
        out / "bundle.md").read_text(encoding="utf-8")
    assert not (study.root / "review").exists()


def test_files_the_verifier_requests_are_filtered_like_the_bundle():
    for rel in ("paper/scaffold.json", "team/NOTES.md", ".scratch/cell.py", "review/iter-1/mistakes.json",
                "context/AMENDMENTS.md", "src/__pycache__/x.py"):
        assert not judge.allowed_evidence(rel), rel
    assert judge.allowed_evidence("results/metrics.csv") and judge.allowed_evidence("context/brief.json")


def test_fatal_rubric_with_an_accept_verdict_is_inconsistent(study, provider):
    contradicting = report(verdict="accept", rubric_items=[
        RubricItem(criterion=c, assessment="fatal" if c == "statistics" else "sound", note="")
        for c in judge.CRITERIA])
    provider.parse_result(contradicting)
    provider.parse_result(contradicting)
    mistakes, _ = run(study)
    assert mistakes["rejudged"] and not mistakes["verdict_consistent"]


def test_bib_titles_parse_escapes():
    bib = "@article{a1,\n  title = {{Robust \\& fast tests}},\n  year = {2020}\n}\n\n@article{b2,\n title={B}\n}"
    assert judge.bib_entry_titles(bib) == {"a1": "Robust & fast tests", "b2": "B"}


# ── Output budget, truncation and stream failures ──────────────────────────
# Regression for project 6d8c3c93c209: at high effort the review's thinking plus its JSON hit the
# 32K ceiling in 4 of 5 calls, so each of those reviews cost a wasted full generation and was in
# the end written at medium effort.


def _usage(out: int) -> NS:
    return NS(input_tokens=100, cache_read_input_tokens=0, cache_creation_input_tokens=0, output_tokens=out)


def _cut_review(text: str) -> NS:
    """Stopped by the output limit partway through (or, as here, just after) the answer."""
    return NS(id="m", content=[NS(type="thinking", thinking="…", signature="s"), NS(type="text", text=text)],
              stop_reason="max_tokens", usage=_usage(64_000))


def _thought_only(stop: str = "max_tokens") -> NS:
    """The reasoning used the whole budget (or ended the turn): no answer text at all."""
    return NS(id="m", content=[NS(type="thinking", thinking="…", signature="s")], stop_reason=stop,
              usage=_usage(64_000 if stop == "max_tokens" else 900))


class _BrokenStream(_Stream):
    """A response stream that started and then failed before its final message."""

    def __init__(self, exc: Exception):
        super().__init__([], None, None)
        self.exc = exc

    async def get_final_message(self):
        raise self.exc


def _frame(kind: str) -> anthropic.APIStatusError:
    """An error frame on an HTTP 200 stream, as the SDK raises it (a bare APIStatusError)."""
    body = {"type": "error", "error": {"type": kind, "message": "stream failed"}}
    return anthropic.APIStatusError(str(body), response=httpx2.Response(200, request=REQUEST), body=body)


def _tail(req: dict) -> str:
    return req["messages"][0]["content"][-1]["text"]


def test_judge_and_verifier_stream_with_the_64k_budget_and_adaptive_thinking(study, provider):
    provider.parse_result(report([issue("I1", "MAJOR")], verdict="major_revision"))
    provider.parse_result(VerificationReport(checks=[
        IssueCheck(ref="I1", outcome="confirmed", reason="seen", corrected_severity="MAJOR")]))
    mistakes, _ = run(study)
    assert provider.transports == ["stream", "stream"]  # one review and one verification: nothing regenerated
    for req in provider.requests:
        assert req["max_tokens"] == judge.JUDGE_MAX_TOKENS == llm.LONG_MAX_TOKENS == 64_000
        assert req["thinking"] == {"type": "adaptive"} and req["output_config"]["effort"] == "high"
        assert req["output_config"]["format"]["type"] == "json_schema"  # schema still enforced server-side
    assert _tail(provider.requests[0]) == judge.JUDGE_INSTRUCTIONS  # review instructions unchanged
    assert mistakes["valid"] and mistakes["verdict"] == "major_revision" and mistakes["issues"][0]["blocking"]


def test_a_cut_off_review_is_discarded_never_parsed_even_if_its_text_validates(study, provider):
    h = Handle()
    provider.script.append(_cut_review(report(verdict="reject").model_dump_json()))
    provider.parse_result(report())
    mistakes, _ = asyncio.run(judge.review(study.pid, h, iteration=2))
    assert mistakes["verdict"] == "accept" and len(provider.requests) == 2  # the cut-off "reject" never counted
    first, retry = provider.requests
    assert retry["messages"][0]["content"][:-1] == first["messages"][0]["content"][:-1]  # the same evidence
    assert _tail(retry) == judge.JUDGE_INSTRUCTIONS + judge.OUTPUT_LIMIT_NOTE  # same criteria, plus the note
    assert retry["output_config"]["effort"] == "medium" and retry["thinking"] == {"type": "adaptive"}
    assert retry["max_tokens"] == 64_000
    assert any("output limit" in n and "retrying once" in n for n in h.notes)


def test_a_review_that_was_all_reasoning_is_retried_once_with_thinking_still_on(study, provider):
    provider.script.append(_thought_only())
    provider.parse_result(report())
    mistakes, _ = run(study)
    assert mistakes["valid"] and [provider.effort(i) for i in range(2)] == ["high", "medium"]
    assert all(r["thinking"] == {"type": "adaptive"} and r["max_tokens"] == 64_000 for r in provider.requests)


def test_an_answerless_turn_is_rejected_and_retried_with_the_reason(study, provider):
    provider.script.append(_thought_only(stop="end_turn"))
    provider.parse_result(report())
    mistakes, _ = run(study)
    assert mistakes["valid"] and provider.effort(1) == "high"  # not an output-limit problem: effort kept
    assert "reasoning but no answer" in _tail(provider.requests[1])


def test_an_exhausted_output_budget_fails_the_review_explicitly_after_one_retry(study, provider):
    provider.script += [_thought_only(), _cut_review('{"summary": "half a rev')]
    with pytest.raises(judge.ReviewFailed, match=r"did not return a valid review: .*stop reason: max_tokens"):
        run(study)
    assert len(provider.requests) == 2  # bounded: never a third full generation


def test_a_truncated_verification_falls_back_to_the_conservative_rule(study, provider):
    provider.parse_result(report([issue("I1", "MAJOR")], verdict="major_revision"))
    provider.script.append(_cut_review('{"checks": [{"ref": "I1", "outcome": "ref'))
    mistakes, _ = run(study)
    assert mistakes["verification"] == "failed" and mistakes["issues"][0]["blocking"]  # never approves
    assert len(provider.requests) == 2


@pytest.mark.parametrize("error", [httpx2.ReadError("connection reset", request=REQUEST),
                                   _frame("throttlingException"), _frame("modelStreamErrorException"),
                                   _frame("overloaded_error")])
def test_a_stream_that_breaks_mid_review_is_retried_once_then_fails_explicitly(study, provider, error):
    provider.script.append(_BrokenStream(error))
    provider.parse_result(report())
    mistakes, _ = run(study)
    assert mistakes["valid"] and len(provider.requests) == 2
    provider.script += [_BrokenStream(error), _BrokenStream(error)]
    # Generic: the provider and the exception class stay in the logs, out of the user's message.
    with pytest.raises(judge.ReviewFailed, match="temporarily unavailable") as failure:
        run(study)
    assert "StreamInterrupted" not in str(failure.value)


def test_a_non_transient_stream_error_is_not_retried(study, provider):
    provider.script.append(_BrokenStream(_frame("validationException")))
    with pytest.raises(anthropic.APIStatusError, match="validationException"):  # refine.py fails the review
        run(study)
    assert len(provider.requests) == 1


def test_a_refused_64k_budget_falls_back_to_the_32k_ceiling(study, provider):
    provider.script.append(anthropic.BadRequestError(
        "max_tokens: 64000 > 32000, which is the maximum allowed", response=httpx2.Response(400, request=REQUEST),
        body={}))
    provider.parse_result(report())
    mistakes, _ = run(study)
    assert mistakes["valid"] and provider.transports == ["stream", "create"]
    assert [r["max_tokens"] for r in provider.requests] == [64_000, llm.MAX_TOKENS]


# ── Figures and sub-figures in the evidence bundle ─────────────────────────


SUBFIGURES = r"""\begin{figure}
\begin{subfigure}{0.5\linewidth}\includegraphics{../figures/a.png}\caption{Panel A only.}\label{fig:pa}\end{subfigure}
\begin{subfigure}{0.5\linewidth}\includegraphics{../figures/b.png}\caption{Panel B only.}\label{fig:pb}\end{subfigure}
\caption{Both panels together.}
\label{fig:both}
\end{figure}
Figure~\ref{fig:main} shows the effect."""


def test_subfigure_panels_carry_their_own_caption_and_the_figure_caption_once(study, provider):
    for name in ("a.png", "b.png"):
        (study.root / "figures" / name).write_bytes(png())
    study.write_paper(TEX.replace("Figure~\\ref{fig:main} shows the effect.", SUBFIGURES))
    provider.parse_result(report())
    _, bundle = run(study)
    a = bundle.sources["figure:figures/a.png"].text.splitlines()
    b = bundle.sources["figure:figures/b.png"].text.splitlines()
    assert a[0].startswith("=== SOURCE id=figure:figures/a.png label=fig:pa ")
    assert a[1:3] == ["Sub-figure caption: Panel A only.",
                      "Part of figure label=fig:both (manuscript L17): figure caption: Both panels together."]
    assert b[0].startswith("=== SOURCE id=figure:figures/b.png label=fig:pb ")
    assert b[1:3] == ["Sub-figure caption: Panel B only.",
                      "Part of figure label=fig:both (manuscript L17): its caption is given with figure:figures/a.png"]
    # A figure without panels keeps exactly the header it always had.
    main = bundle.sources["figure:figures/main.png"].text.splitlines()
    assert main[1] == "Caption: Accuracy of M and B across seeds." and main[2].startswith("Code naming this file:")
    assert len(main) == 3
