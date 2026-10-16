"""Stage 8 · Independent scientific review (the Judge Agent).

Every review is a fresh, single model call that sees the finished study as a skeptical peer
reviewer would: the user's original question, the pre-registered plan and what changed since,
protocol amendments, platform facts about execution, the manuscript (line-numbered), its
figures as images, the result files and analysis code behind it, the cited papers' abstracts,
and deterministic integrity facts. It sees no conversation, no earlier reviews, no repair
plans and no agent self-assessments (scaffold, task summaries, verifier verdicts, team notes).

The output is validated (schema, rubric coverage, evidence), each quote is checked against
its source, and FATAL/MAJOR claims get an independent adversarial verification call before
they can block. Failures never become approval: they are reported as failed reviews.
"""

import asyncio
import base64
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from pydantic import BaseModel
from sqlmodel import Session, select

from .. import integrity, llm
from ..config import settings, tier_of
from ..db import Project, Run, TaskState, engine
from ..execution.orchestrator import TEXT_SUFFIXES, _previews
from ..execution.sandbox import sandbox_for
from ..jobs import RunHandle
from ..llm import MODEL_UNAVAILABLE, TRANSIENT_ERRORS, parse
from ..sources.common import norm_title
from . import plan as plan_agent

log = logging.getLogger("openscientist.judge")

CRITERIA = (
    "research_question", "experimental_design", "controls_confounds", "statistics", "math_computation",
    "reproducibility", "literature", "data_integrity", "figures_tables", "claims_support", "novelty",
    "internal_consistency",
)
PREREG_FIELDS = ("research_question", "hypothesis", "null_hypothesis", "objectives", "metrics", "baselines",
                 "validation_strategy", "success_criteria")
BLOCKING_SEVERITIES = ("FATAL", "MAJOR")
SEVERITY_RANK = {"MINOR": 0, "MAJOR": 1, "FATAL": 2}

TEXT_BUDGET = 400_000  # characters of text evidence (~110k tokens)
MANUSCRIPT_LIMIT = 160_000
CODE_FILE_LIMIT, CODE_TOTAL = 10_000, 60_000
ABSTRACT_LIMIT = 1200
MAX_VISUALS, VISUAL_BYTES, VISUALS_TOTAL = 20, int(3.75 * 1024**2), 10 * 1024**2
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
               ".webp": "image/webp"}
ANALYSIS_KINDS = {"analysis", "modeling", "experiment", "evaluation"}
DATA_SUFFIXES = {".csv", ".tsv", ".json", ".md", ".txt", ".yaml", ".yml"}
RETRY_DELAY = 30.0  # one extra retry after the SDK's own retries
# Output budget (thinking included) of every judge and verifier call: the 64K streamed maximum.
# At high effort the review's thinking plus its JSON reached the old 32K ceiling in 4 of 5 calls
# (project 6d8c3c93c209); only generated tokens are billed, so the larger ceiling costs nothing extra.
JUDGE_MAX_TOKENS = llm.LONG_MAX_TOKENS
_REVIEW_IDS = re.compile(r"\b(?:R\d+-P?\d+|T-\d{3,})\b")


# ── Schemas ────────────────────────────────────────────────────────────────


class Evidence(BaseModel):
    source: str
    locator: str
    quote: str
    observation: str


class JudgeIssue(BaseModel):
    ref: str
    severity: Literal["FATAL", "MAJOR", "MINOR"]
    category: str
    certainty: Literal["demonstrated", "likely", "uncertain"]
    title: str
    description: str
    evidence: list[Evidence]
    absence_terms: list[str]
    why_it_matters: str
    corrective_action: str
    origin: Literal["plan", "blueprint", "execution", "analysis", "report", "literature"]
    affected: list[str]
    invalidates: list[str]
    evidence_needed: str
    requested_files: list[str]


class RubricItem(BaseModel):
    criterion: str
    assessment: Literal["sound", "minor_concerns", "major_concerns", "fatal", "not_applicable"]
    note: str


class Upgrade(BaseModel):
    ref: str
    title: str
    action: str
    origin: Literal["plan", "blueprint", "execution", "analysis", "report", "literature"]
    impact: Literal["high", "medium", "low"]
    expected_gain: float  # points on the 0-10 score this upgrade alone would add


class JudgeReport(BaseModel):
    summary: str
    score: float
    score_rationale: str
    objective_alignment: Literal["answers", "partially_answers", "does_not_answer"]
    objective_alignment_note: str
    hypothesis_support: Literal["supported", "not_supported", "inconclusive", "mixed"]
    rubric: list[RubricItem]
    issues: list[JudgeIssue]
    verdict: Literal["accept", "minor_revision", "major_revision", "reject"]
    upgrades: list[Upgrade]


class IssueCheck(BaseModel):
    ref: str
    outcome: Literal["confirmed", "refuted", "uncertain"]
    reason: str
    corrected_severity: Literal["FATAL", "MAJOR", "MINOR"]


class VerificationReport(BaseModel):
    checks: list[IssueCheck]


# ── Prompts ────────────────────────────────────────────────────────────────

JUDGE_SYSTEM = """\
You are an independent scientific reviewer for OpenScientist, an automated research system.
You review completed studies with the rigour of a demanding peer reviewer at a top venue
(NeurIPS, ICML, ICLR, Nature, Science, or the leading venue of the paper's field): the paper
is judged as if it had been submitted there today, and leniency helps no one.
You know nothing about how the study was produced beyond the evidence in front of you, and
you do not assume that any part of the pipeline checked its own work correctly. Every claim
you make must be grounded in the numbered sources provided."""

JUDGE_INSTRUCTIONS = """\
Review the study above. Decide whether its conclusions are scientifically valid and supported
by its own evidence, and find every substantive mistake.

Assess each of these criteria exactly once in `rubric` (criterion names verbatim):
- research_question: is the question operationalized validly, and does the paper answer the
  ORIGINAL question in `objective` (not a narrower or easier one)?
- experimental_design: do the experiments actually test the hypothesis?
- controls_confounds: missing baselines/controls/ablations, confounds, leakage, alternative explanations.
- statistics: tests, assumptions, independence, multiple comparisons, effect sizes, CIs, seeds/sample size.
- math_computation: errors in equations, derivations, metrics or code that computes reported numbers.
- reproducibility: execution integrity; failed/skipped tasks; can the results be regenerated from the code?
- literature: are cited papers characterized correctly (check against their abstracts)?
- data_integrity: provenance; signs of fabricated, hard-coded or mismatched numbers.
- figures_tables: do figures and tables match the result files and the text? Misleading plots?
- claims_support: do the results support each conclusion at the strength claimed?
- novelty: are novelty claims substantiated against the related work provided? (Do not demand
  novelty the paper does not claim.)
- internal_consistency: contradictions, and changes from the pre-registration (see plan_current's
  diff and the protocol amendments) that are unjustified or move the goalposts.

Issues:
- severity FATAL: invalidates an essential finding or the study. MAJOR: a substantial weakness
  that must be corrected. MINOR: does not undermine validity. Ignore writing style unless it
  causes misinterpretation. Honest negative or inconclusive results are acceptable.
- certainty demonstrated: the cited evidence shows it; likely: strong but indirect; uncertain:
  a concern you cannot establish from the evidence (say what evidence would settle it in
  evidence_needed, and list workspace files you need in requested_files).
- Every FATAL or MAJOR issue needs evidence: source ids exactly as given (e.g. "manuscript",
  "artifact:results/metrics.csv", "code:src/stats.py", "figure:figures/main.png",
  "literature:smith2020data", "plan_current"), a locator (manuscript line range like "L120-L131",
  table row, figure panel) and a verbatim quote copied from that source (leave quote empty only
  for figures). For "X is missing" claims, put the search terms whose absence you verified in
  absence_terms.
- why_it_matters: why it undermines validity. corrective_action: the concrete fix (what to run,
  change or withdraw), not generic advice.
- origin: where the mistake was introduced: plan (design/operationalization), blueprint (a task
  specification omitted something needed), execution (implementation or data handling),
  analysis (statistics/computation), report (text, captions, claims, citations), literature
  (prior work mischaracterized).
- affected: manuscript sections, figure/table labels, artifact paths and task ids involved.
  invalidates: the artifacts or claims that would have to be regenerated or withdrawn.
- At most 15 issues; merge duplicates; FATAL and MAJOR first.

verdict: accept (no FATAL/MAJOR issues), minor_revision (MINOR issues only), major_revision
(MAJOR issues), reject (any FATAL issue).

score (0-10, one decimal): how good the paper is as a submission to a top venue of its field,
as it stands now. Weigh correctness, rigour (baselines, ablations, seeds, statistics), scale
and difficulty of the evidence, significance, novelty, depth of analysis and clarity. Anchors:
- 10: outstanding; a best-paper candidate. 9: strong accept. 8: clear accept at a top venue.
- 7: weak accept; solid but limited. 6: borderline. 5: weak reject; real contribution, not yet
  convincing. 4: reject; serious gaps. 2-3: fundamentally flawed or trivial. 0-1: invalid.
- A correct but small or routine study (toy scale, a single dataset or seed, missing standard
  baselines, an unsurprising result) is a 4-6, not an 8. Any FATAL issue caps the score at 3;
  any MAJOR issue caps it at 6. Do not inflate the score to be encouraging.
score_rationale: two to four sentences naming what holds the score down.

upgrades: what would turn this into an outstanding paper (a 10/10, ideally beyond): the
changes a top-venue area chair would ask for that are NOT already listed as issues, such as
stronger or standard baselines, more seeds and confidence intervals, ablations, additional
datasets or scales, a sharper analysis of why the result holds, or a clearer contribution.
Each must be concrete and doable by an automated system with code, public data, CPU sandboxes
and cloud GPUs within hours (no new human studies, no proprietary data, no wet lab). action
says exactly what to run or change; origin is the earliest stage that must change;
expected_gain is your estimate of score points it adds. Highest impact first, at most 8, refs
U1, U2, …; an empty list only for a paper that is already a 10."""

# Added only to the one fresh attempt after a review was cut off by the output limit.
OUTPUT_LIMIT_NOTE = """

NOTE: an earlier attempt at this review used its entire output budget, reasoning included, before
it finished, and was discarded. Apply exactly the same criteria and standard of evidence, but
reason economically: settle each criterion and issue once, do not draft the JSON answer in your
reasoning, and write the complete review as your answer."""

VERIFY_INSTRUCTIONS = """\
Another reviewer claims the problems listed below. Verify each one independently against the
evidence above. Try to show each claim is wrong before you accept it.
- confirmed: the evidence shows the problem exists as described and matters at least at
  corrected_severity.
- refuted: the evidence contradicts the claim, or its quotes/facts do not support it.
- uncertain: the evidence cannot settle it either way.
corrected_severity may be lower than claimed, never higher. Platform GROUNDING facts tell you
whether each quote was found verbatim in its source. Return one check per claimed issue (same ref)."""


# ── Bundle ─────────────────────────────────────────────────────────────────


@dataclass
class Source:
    id: str
    path: str | None
    text: str  # what the judge saw (for grounding)
    truncated: bool = False

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8", "replace")).hexdigest()


@dataclass
class Bundle:
    blocks: list[dict] = field(default_factory=list)  # user content blocks (text, image, document)
    sources: dict[str, Source] = field(default_factory=dict)
    visuals: list[dict] = field(default_factory=list)  # {id, path, sha256, bytes, media_type}
    omitted: list[dict] = field(default_factory=list)
    tex_lines: list[str] = field(default_factory=list)  # raw manuscript lines (1-based via index+1)
    markdown: list[str] = field(default_factory=list)
    numeric: dict | None = None  # numeric cross-check result, if run

    @property
    def sha256(self) -> str:
        """Identity of exactly what the judge is shown (text, and the hash of each visual)."""
        h = hashlib.sha256()
        for b in self.blocks:
            h.update((b["text"] if b["type"] == "text" else b["_sha"]).encode("utf-8", "replace"))
        return h.hexdigest()

    def add_text(self, source: Source, header: str) -> None:
        self.sources[source.id] = source
        text = f"=== SOURCE id={source.id}{header} ===\n{source.text}\n"
        self.blocks.append({"type": "text", "text": text})
        self.markdown.append(text)

    def request_blocks(self) -> list[dict]:
        """Content blocks without the private bookkeeping keys."""
        return [{k: v for k, v in b.items() if not k.startswith("_")} for b in self.blocks]


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=1, default=str)


# Pipeline self-assessments and review history: never evidence for the judge.
EXCLUDED_EVIDENCE = ("paper/scaffold.json", "team/", "review/", "context/AMENDMENTS.md")


def allowed_evidence(rel: str) -> bool:
    """Whether a workspace file may be shown to the judge (hidden dirs and self-assessments excluded)."""
    parts = rel.split("/")
    return not any(p.startswith(".") or p == "__pycache__" for p in parts) and \
        not any(rel == x or (x.endswith("/") and rel.startswith(x)) for x in EXCLUDED_EVIDENCE)


def _safe(root: Path, rel: str) -> Path | None:
    try:
        p = (root / rel.lstrip("/")).resolve()
    except (OSError, ValueError):
        return None
    return p if p == root or root in p.parents else None


def _plan_fields(plan: dict | None) -> dict:
    return {k: (plan or {}).get(k) for k in PREREG_FIELDS}


def preregistration_of(plan: dict | None) -> dict:
    return _plan_fields(plan)


def plan_diff(prereg: dict, plan: dict | None) -> list[str]:
    current = _plan_fields(plan)
    out = []
    for k in PREREG_FIELDS:
        if json.dumps(prereg.get(k), sort_keys=True, default=str) != json.dumps(current.get(k), sort_keys=True,
                                                                               default=str):
            before = json.dumps(prereg.get(k), ensure_ascii=False, default=str)[:1500]
            after = json.dumps(current.get(k), ensure_ascii=False, default=str)[:1500]
            out.append(f"CHANGED {k}:\n  pre-registered: {before}\n  current: {after}")
    return out


def _load(project_id: str) -> dict:
    with Session(engine) as s:
        project = s.get(Project, project_id)
        bp_id = (project.blueprint or {}).get("run_id")
        bp = s.get(Run, bp_id) if bp_id else None
        states = list(s.exec(select(TaskState).where(TaskState.blueprint_run_id == bp_id))) if bp_id else []
        return {
            "brief": project.brief or {}, "gap": project.chosen_gap or {}, "plan": project.plan or {},
            "review": project.review or {}, "amendments": list((project.settings or {}).get("amendments", [])),
            "mp": (bp.result or {}).get("master_plan", {}) if bp else {}, "states": states, "bp_run_id": bp_id,
        }


def _artifact_paths(root: Path, mp: dict) -> list[str]:
    """Text result files: declared task outputs (directories expanded) plus everything in results/."""
    found: set[str] = set()
    candidates = [o["path"] for t in mp.get("tasks", []) for o in t.get("outputs", [])] + ["results"]
    for rel in candidates:
        p = _safe(root, rel)
        if p is None or not p.exists():
            continue
        files = [p] if p.is_file() else [q for q in p.rglob("*") if q.is_file()]
        for q in files:
            r = q.relative_to(root)
            if q.suffix.lower() in DATA_SUFFIXES and allowed_evidence(r.as_posix()) \
                    and r.parts[0] != integrity.REPORT_DIR:
                found.add(r.as_posix())

    def rank(path: str) -> tuple:
        top = path.split("/", 1)[0]
        first = 0 if path == "results/SUMMARY.md" else 1
        return first, {"results": 0, "analysis": 1, "tables": 1}.get(top, 2), (root / path).stat().st_size, path

    return sorted(found, key=rank)


def _code_paths(root: Path, mp: dict, plan: dict, figure_code: dict[str, list[str]]) -> list[str]:
    kinds = {t["id"]: t.get("kind") for ph in plan.get("phases", []) for t in ph.get("tasks", [])}
    declared = [o["path"] for t in mp.get("tasks", []) if kinds.get(t["id"]) in ANALYSIS_KINDS
                for o in t.get("outputs", []) if Path(o["path"]).suffix.lower() in integrity.CODE_SUFFIXES]
    figure_scripts = [r for refs in figure_code.values() for r in refs]
    out = []
    for rel in dict.fromkeys(figure_scripts + declared):
        p = _safe(root, rel)
        if p is not None and p.is_file() and allowed_evidence(rel):
            out.append(rel)
    return out


def bib_entry_titles(bib: str) -> dict[str, str]:
    """Citation key → title for each entry of a .bib file (LaTeX escapes undone)."""
    out = {}
    for entry in re.split(r"\n(?=@)", bib):
        key = integrity.BIB_KEY_RE.search(entry)
        title = re.search(r"\btitle\s*=\s*\{+(.*?)\}+\s*,?\s*$", entry, re.MULTILINE | re.IGNORECASE)
        if key and title:
            out[key.group(1).strip()] = re.sub(r"\\([&%$#_{}])", r"\1", title.group(1))
    return out


def _literature_entry(key: str, paper, cites: list[tuple[int, str]]) -> str:
    if paper is None:
        head = f"[{key}] (not in the project's literature records)"
        body = ""
    else:
        notes = paper.notes or {}
        abstract = (paper.abstract or paper.tldr or "(no abstract available)")[:ABSTRACT_LIMIT]
        head = f"[{key}] {paper.title} ({paper.year or 'n.d.'}, {paper.venue or 'venue unknown'})"
        body = (f"\nAbstract: {abstract}\nContribution: {notes.get('contribution', '')}\n"
                f"Key findings: {' | '.join(notes.get('key_findings', [])[:3])}")
    uses = "\n".join(f"  L{n}: {sentence}" for n, sentence in cites[:6])
    return f"{head}{body}\nCited in the manuscript:\n{uses}"


def build_bundle(project_id: str, gates: dict, root: Path | None = None) -> Bundle:
    """Assemble the judge's evidence deterministically (an allowlist; see module docstring)."""
    from .report import _references  # local: report imports the execution package

    root = root or sandbox_for(project_id).root
    d = _load(project_id)
    b = Bundle()
    budget = TEXT_BUDGET

    def take(text: str) -> None:
        nonlocal budget
        budget -= len(text)

    brief = {k: d["brief"].get(k) for k in ("title", "core_question", "summary", "scope_in", "scope_out",
                                            "result_type", "constraints", "assumptions", "data_resources",
                                            "compute_resources")}
    gap = {k: d["gap"].get(k) for k in ("title", "question", "hypothesis", "why_open", "approach")}
    gap["closest_prior_work"] = (d["gap"].get("novelty_check") or {}).get("closest", [])
    objective = _json({"research_brief": brief, "chosen_research_gap": gap})
    prereg = d["review"].get("preregistration") or preregistration_of(d["plan"])
    current = {**_plan_fields(d["plan"]),
               "methods": d["plan"].get("methods"), "datasets": d["plan"].get("datasets")}
    diff = plan_diff(prereg, d["plan"])
    amendments = [_REVIEW_IDS.sub("", f"[{i + 1}] (task {a.get('task')}) {a.get('text', '')}").strip()
                  for i, a in enumerate(d["amendments"])]
    states = {st.task_id: st for st in d["states"]}
    record = []
    for t in d["mp"].get("tasks", []):
        st = states.get(t["id"])
        outs = [f"{o['path']} ({'present' if (p := _safe(root, o['path'])) and p.exists() else 'MISSING'})"
                for o in t.get("outputs", [])]
        record.append({"id": t["id"], "title": _REVIEW_IDS.sub("", t.get("title") or ""),
                       "objective": _REVIEW_IDS.sub("", t.get("objective") or ""),
                       "depends_on": t.get("depends_on", []), "inputs": [i["path"] for i in t.get("inputs", [])],
                       "outputs": outs, "compute": (t.get("compute") or {}).get("kind"),
                       "status": st.status if st else "not started", "attempts": st.attempts if st else 0})

    tex_path = root / integrity.REPORT_DIR / "paper.tex"
    tex = tex_path.read_text(encoding="utf-8", errors="replace") if tex_path.is_file() else ""
    b.tex_lines = tex.splitlines()
    numbered = "\n".join(f"L{n:04d} {line}" for n, line in enumerate(b.tex_lines, start=1))
    truncated = len(numbered) > MANUSCRIPT_LIMIT
    if truncated:
        b.omitted.append({"path": "paper/paper.tex", "reason": f"truncated to {MANUSCRIPT_LIMIT:,} characters"})
        numbered = numbered[:MANUSCRIPT_LIMIT]

    intro = ("The study under review follows as numbered sources. Cite them by id.\n")
    b.blocks.append({"type": "text", "text": intro})
    b.markdown.append(intro)
    for src, header in [
        (Source("objective", None, objective), " (the user's research brief and the chosen research gap)"),
        (Source("preregistration", "backend/data/projects/<id>/vague_research_plan.json", _json(prereg)),
         " (the approved plan before execution: question, hypothesis, metrics, success criteria)"),
        (Source("plan_current", None, _json(current) + ("\n\nDIFF VS PRE-REGISTRATION:\n" + "\n".join(diff)
                                                         if diff else "\n\n(no changes from the pre-registration)")),
         " (the plan as finally executed)"),
        (Source("protocol_amendments", "context/AMENDMENTS.md", "\n".join(amendments) or "(none)"),
         " (protocol amendments applied during execution; instructions, not evidence of outcomes)"),
        (Source("execution_record", None, _json(record)),
         " (tasks as specified, with platform facts: status, attempts, outputs present)"),
        (Source("manuscript", "paper/paper.tex", numbered, truncated), " path=paper/paper.tex (line-numbered LaTeX)"),
    ]:
        b.add_text(src, header)
        take(src.text)

    # Figures as images (or single-page PDFs), with their captions and the code that names them.
    total = 0
    seen: set[str] = set()
    figures_shown: dict[tuple, str] = {}  # enclosing figure → the source id that gave its caption
    for g in gates.get("figures", []):
        if not g.path or g.path in seen:
            continue
        seen.add(g.path)
        path = Path(g.path)
        png = path.with_suffix(".png")
        if path.suffix.lower() == ".pdf" and (root / png).is_file():
            path = png
        media = IMAGE_TYPES.get(path.suffix.lower()) or ("application/pdf" if path.suffix.lower() == ".pdf" else None)
        data = (root / path).read_bytes() if media else b""
        reason = ("unsupported format" if not media else "too many figures" if len(b.visuals) >= MAX_VISUALS
                  else "larger than 3.75 MB" if len(data) > VISUAL_BYTES
                  else "figure byte budget exceeded" if total + len(data) > VISUALS_TOTAL else "")
        sid = f"figure:{path.as_posix()}"
        refs = gates.get("figure_code", {}).get(g.path, [])
        header = (f"=== SOURCE id={sid} label={g.label or '(none)'} (manuscript L{g.line}) ===\n"
                  f"{'Sub-figure caption' if g.panel else 'Caption'}: "
                  f"{g.caption or (f'(not extracted: {g.note})' if g.note else '(none)')}\n")
        if g.figure_label or g.figure_caption or (g.panel and g.figure_line):
            # A panel of a larger figure: that figure's own caption, once per figure.
            header += f"Part of figure label={g.figure_label or '(none)'} (manuscript L{g.figure_line}): "
            key = (g.figure_line, g.figure_label, g.figure_caption)
            if key in figures_shown:
                header += f"its caption is given with {figures_shown[key]}\n"
            else:
                figures_shown[key] = sid
                header += f"figure caption: {g.figure_caption or '(none)'}\n"
        header += f"Code naming this file: {', '.join(refs) or '(none found)'}\n"
        b.sources[sid] = Source(sid, path.as_posix(), header)
        if reason:
            b.omitted.append({"path": path.as_posix(), "reason": reason})
            b.blocks.append({"type": "text", "text": header + f"(image not shown: {reason})\n"})
            b.markdown.append(header + f"(image not shown: {reason})\n")
            continue
        total += len(data)
        sha = hashlib.sha256(data).hexdigest()
        kind = "document" if media == "application/pdf" else "image"
        b.blocks.append({"type": "text", "text": header})
        b.blocks.append({"type": kind, "source": {"type": "base64", "media_type": media,
                                                  "data": base64.standard_b64encode(data).decode()}, "_sha": sha})
        b.visuals.append({"id": sid, "path": path.as_posix(), "sha256": sha, "bytes": len(data), "media_type": media})
        b.markdown.append(header + f"[{kind.upper()} {path.as_posix()} sha256={sha}]\n")

    # Evidence beyond the mandatory sources, greedily within the text budget:
    # the results summary, cited literature, analysis code, then the other result files.
    info = gates.get("tex")
    refs, _ = _references(project_id)
    by_title = {norm_title(p.title): p for p in refs.values()}
    bib = root / integrity.REPORT_DIR / "references.bib"
    bib_titles = bib_entry_titles(bib.read_text(encoding="utf-8", errors="replace")) if bib.is_file() else {}
    lit = []
    for key in sorted(info.cites if info else {}):
        paper = refs.get(key) or by_title.get(norm_title(bib_titles.get(key, "")))
        lit.append((f"literature:{key}", _literature_entry(key, paper, info.cites[key])))
    code_used = 0
    code = []
    for rel in _code_paths(root, d["mp"], d["plan"], gates.get("figure_code", {})):
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        cut = len(text) > CODE_FILE_LIMIT
        text = text[:CODE_FILE_LIMIT] + (f"\n… [{len(text) - CODE_FILE_LIMIT:,} chars omitted]" if cut else "")
        if code_used + len(text) > CODE_TOTAL:
            b.omitted.append({"path": rel, "reason": "code budget"})
            continue
        code_used += len(text)
        code.append((f"code:{rel}", rel, text, cut))
    shim = SimpleNamespace(path=lambda rel: _safe(root, rel) or root / "__outside__")
    artifacts = []
    for rel in _artifact_paths(root, d["mp"]):
        preview = _previews(shim, [{"path": rel}]).split("\n", 1)
        text = preview[1] if len(preview) > 1 else ""
        artifacts.append((f"artifact:{rel}", rel, text, "chars omitted" in text))
    ordered = ([a for a in artifacts if a[1] == "results/SUMMARY.md"]
               + [(sid, None, text, False) for sid, text in lit] + code
               + [a for a in artifacts if a[1] != "results/SUMMARY.md"])
    for sid, rel, text, cut in ordered:
        if len(text) > budget:
            b.omitted.append({"path": rel or sid, "reason": "evidence budget"})
            continue
        b.add_text(Source(sid, rel, text, cut), f" path={rel}" if rel else "")
        take(text)

    facts = list(gates.get("facts", []))
    numeric = None
    if settings.review_numeric_crosscheck and info is not None:
        numeric = integrity.numeric_crosscheck(info, evidence_texts(b))
    b.numeric = numeric
    if numeric and numeric.get("unmatched"):
        facts.append(
            f"Numeric cross-check (heuristic; derived values such as differences also appear here): "
            f"{numeric['unmatched_total']} of {numeric['checked']} reported numbers were not found in any result "
            "file at the printed precision:\n" + "\n".join(
                f"  L{n['line']} {n['text']}: {n['context']}" for n in numeric["unmatched"]))
    b.add_text(Source("integrity", None, "\n".join(f"- {f}" for f in facts) or "(no findings)"),
               " (deterministic platform checks)")
    omissions = "\n".join(f"- {o['path']}: {o['reason']}" for o in b.omitted) or "(none)"
    b.add_text(Source("omissions", None, omissions), " (workspace files not shown; request them if needed)")
    return b


def evidence_texts(bundle: Bundle) -> list[str]:
    return [s.text for sid, s in bundle.sources.items() if sid.startswith(("artifact:", "code:"))]


# ── Grounding and blocking ─────────────────────────────────────────────────


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\bL\d{4} ", " ", text)).strip().casefold()


def _line_range(locator: str) -> tuple[int, int] | None:
    """Manuscript line range from a locator such as 'L120-L131' or 'L88'."""
    m = re.search(r"L(\d+)\s*(?:[-–]\s*L?(\d+))?", locator or "")
    if not m:
        return None
    a = int(m.group(1))
    return a, max(a, int(m.group(2) or a))


def _quote_found(bundle: Bundle, ev: Evidence) -> bool | None:
    """Whether the quote appears verbatim (whitespace-normalised) in its source; None for
    figures, whose claims are visual. Manuscript quotes must lie within the cited lines ±3."""
    if ev.source.startswith("figure:"):
        return None
    quote = _norm(ev.quote)
    if not quote:
        return False
    if ev.source == "manuscript":
        lines = bundle.tex_lines
        rng = _line_range(ev.locator)
        if rng:
            lines = lines[max(0, rng[0] - 4):rng[1] + 3]
        return quote in _norm("\n".join(lines))
    src = bundle.sources.get(ev.source)
    return bool(src) and quote in _norm(src.text)


def ground(issue: JudgeIssue, bundle: Bundle) -> tuple[str, list[bool | None]]:
    found = [_quote_found(bundle, ev) for ev in issue.evidence]
    checkable = [f for f in found if f is not None]
    if issue.absence_terms:
        haystack = _norm(" ".join(s.text for sid, s in bundle.sources.items()
                                  if sid in ("manuscript", "plan_current", "protocol_amendments")))
        if any(_norm(t) and _norm(t) in haystack for t in issue.absence_terms):
            return "absence_contradicted", found
        if not checkable or not any(checkable):
            return "absence_ok", found
    if not checkable:
        return ("visual" if found else "unverified"), found
    if all(checkable):
        return "verified", found
    return ("partial" if any(checkable) else "unverified"), found


def semantic_errors(report: JudgeReport) -> list[str]:
    errors = []
    refs = [i.ref for i in report.issues]
    if len(set(refs)) != len(refs):
        errors.append("Issue refs must be unique.")
    criteria = [r.criterion for r in report.rubric]
    missing = [c for c in CRITERIA if c not in criteria]
    extra = sorted({c for c in criteria if c not in CRITERIA} | {c for c in criteria if criteria.count(c) > 1})
    if missing or extra:
        errors.append(f"rubric must assess each criterion exactly once; missing: {missing or 'none'}; "
                      f"unknown or repeated: {extra or 'none'}.")
    if not 0 <= report.score <= 10:
        errors.append(f"score must be between 0 and 10 (got {report.score}).")
    urefs = [u.ref for u in report.upgrades]
    if len(set(urefs)) != len(urefs) or set(urefs) & set(refs):
        errors.append("Upgrade refs must be unique and distinct from issue refs.")
    for i in report.issues:
        if i.category not in CRITERIA:
            errors.append(f"Issue {i.ref}: category '{i.category}' is not one of {', '.join(CRITERIA)}.")
        if i.severity in BLOCKING_SEVERITIES:
            if not i.evidence and not i.absence_terms:
                errors.append(f"Issue {i.ref}: a {i.severity} issue needs evidence (or absence_terms).")
            if not i.corrective_action.strip():
                errors.append(f"Issue {i.ref}: a {i.severity} issue needs a corrective_action.")
    return errors


def classify(issue: dict, check: IssueCheck | None, verification: str) -> None:
    """Set severity (after verification), blocking and open_concern on an issue dict in place.

    verification: "ok" (the verifier ran), "failed" or "disabled". FATAL/MAJOR issues block only
    when the verifier confirmed them; without a verdict for an issue the conservative rule
    applies (demonstrated/likely and grounded blocks), so a failure can never approve.
    """
    serious = issue["severity"] in BLOCKING_SEVERITIES
    if not serious:
        issue.update(verification="not_needed", verification_note="", blocking=False, open_concern=False)
        return
    if check and check.outcome == "confirmed" and \
            SEVERITY_RANK[check.corrected_severity] < SEVERITY_RANK[issue["severity"]]:
        issue["severity_claimed"], issue["severity"] = issue["severity"], check.corrected_severity
        serious = issue["severity"] in BLOCKING_SEVERITIES
    issue["verification"] = check.outcome if check else ("missing" if verification == "ok" else verification)
    issue["verification_note"] = check.reason if check else ""
    if check:
        issue["blocking"] = serious and check.outcome == "confirmed"
        issue["open_concern"] = serious and check.outcome == "uncertain"
    else:
        grounded = issue["grounding"] not in ("unverified", "absence_contradicted")
        issue["blocking"] = serious and issue["certainty"] in ("demonstrated", "likely") and grounded
        issue["open_concern"] = serious and not issue["blocking"]


SCORE_CAPS = {"FATAL": 3.0, "MAJOR": 6.0}


def capped_score(score: float, issues: list[dict]) -> float:
    """The judge's score, held to the caps its own rules set for the blocking issues that
    survived verification (a refuted claim no longer caps it)."""
    cap = min([SCORE_CAPS[i["severity"]] for i in issues if i.get("blocking")], default=10.0)
    return round(max(0.0, min(score, cap, 10.0)), 1)


# ── Model calls ────────────────────────────────────────────────────────────


class ReviewFailed(RuntimeError):
    """The judge could not produce a valid review (never treated as approval)."""


async def _parse(**kw):
    """parse() with one extra retry on network/provider failures (the SDK already retried)."""
    try:
        return await parse(**kw)
    except TRANSIENT_ERRORS:
        await asyncio.sleep(RETRY_DELAY)
        return await parse(**kw)


async def judge_call(bundle: Bundle, h: RunHandle | None = None) -> JudgeReport:
    """The review: at most two model calls, adaptive thinking on in both, each with the full
    JUDGE_MAX_TOKENS budget (streamed). A second call is made only when the first was unusable:
    - cut off by the output limit, or all reasoning and no answer (llm.OutputLimitReached): it is
      discarded, never parsed, and the one fresh attempt runs at medium effort with a note to reason
      economically, so it fits; the review's instructions and criteria are unchanged;
    - invalid, refused or empty, or failing semantic_errors: retried once with the errors fed back.
    A second failure raises ReviewFailed, which never counts as approval."""
    errors: list[str] = []
    effort, note = "high", ""
    problem = "no attempt was made"
    for attempt in range(2):
        tail = JUDGE_INSTRUCTIONS + note
        if errors:
            tail += ("\n\nYOUR PREVIOUS OUTPUT WAS INVALID. Fix these problems:\n- " + "\n- ".join(errors))
        try:
            # max_tokens stays at the full budget whatever the effort: dropping effort after a
            # truncation is meant to free up room for the JSON by thinking less, not to also
            # shrink the total budget available for it.
            report = await _parse(model=settings.model_judge, instructions=JUDGE_SYSTEM, schema=JudgeReport,
                                  messages=[{"role": "user", "content": [*bundle.request_blocks(),
                                                                         {"type": "text", "text": tail}]}],
                                  reasoning_effort=effort, max_tokens=JUDGE_MAX_TOKENS)
        except TRANSIENT_ERRORS as exc:
            log.warning("judge call failed: %s: %s", type(exc).__name__, exc)
            raise ReviewFailed(MODEL_UNAVAILABLE) from exc
        except llm.OutputLimitReached as exc:
            problem = str(exc)
            effort, note, errors = "medium", OUTPUT_LIMIT_NOTE, []
            if h:
                h.note(f"Review output hit the output limit and was discarded ({problem[:160]}); "
                       "retrying once with less reasoning")
            continue
        except RuntimeError as exc:  # invalid, refused or empty structured output
            problem = str(exc)[:600]
            errors = [problem]
            if h:
                h.note(f"Review output rejected ({problem[:120]}); retrying once")
            continue
        errors = semantic_errors(report)
        if not errors:
            return report
        problem = "; ".join(errors)
        if h:
            h.note(f"Review output incomplete ({errors[0][:120]}); retrying once")
    raise ReviewFailed("The judge did not return a valid review: " + problem[:800])


async def verify_call(bundle: Bundle, claims: list[dict], root: Path) -> VerificationReport:
    requested = []
    for c in claims:
        for rel in c.get("requested_files", [])[:3]:
            p = _safe(root, rel)
            if p is not None and p.is_file() and p.suffix.lower() in TEXT_SUFFIXES and \
                    allowed_evidence(p.relative_to(root).as_posix()) and f"artifact:{rel}" not in bundle.sources:
                requested.append(f"=== REQUESTED FILE {rel} ===\n{p.read_text(encoding='utf-8', errors='replace')[:8000]}")
    listing = _json([{k: c[k] for k in ("ref", "severity", "category", "certainty", "title", "description",
                                       "absence_terms", "why_it_matters", "origin")}
                     | {"evidence": [{**ev, "quote_found_verbatim": ev.get("verified")} for ev in c["evidence"]],
                        "GROUNDING": c["grounding"]} for c in claims])
    tail = VERIFY_INSTRUCTIONS + "\n\nCLAIMED ISSUES:\n" + listing + ("\n\n" + "\n\n".join(requested) if requested else "")
    return await _parse(model=settings.model_judge, instructions=JUDGE_SYSTEM, schema=VerificationReport,
                        messages=[{"role": "user", "content": [*bundle.request_blocks(), {"type": "text", "text": tail}]}],
                        reasoning_effort="high", max_tokens=JUDGE_MAX_TOKENS)


# ── Review ─────────────────────────────────────────────────────────────────


def platform_issues(iteration: int, hard: list[dict]) -> list[dict]:
    category = {"H1": "reproducibility", "H2": "literature", "H3": "figures_tables", "H4": "data_integrity",
                "H5": "reproducibility"}
    return [{
        "id": f"R{iteration}-P{k}", "gate": g["gate"], "severity": g["severity"], "category": category[g["gate"]],
        "certainty": "demonstrated", "title": g["title"], "description": g["detail"], "evidence": [],
        "absence_terms": [], "why_it_matters": "The manuscript cannot be reviewed until this is fixed.",
        "corrective_action": g["detail"], "origin": "report", "affected": g["paths"], "invalidates": g["paths"],
        "evidence_needed": "", "requested_files": [], "grounding": "platform", "verification": "platform",
        "verification_note": "", "blocking": True, "open_concern": False,
    } for k, g in enumerate(hard, start=1)]


def _issue_dict(iteration: int, k: int, issue: JudgeIssue, bundle: Bundle) -> dict:
    grounding, found = ground(issue, bundle)
    d = issue.model_dump()
    d["id"] = f"R{iteration}-{k:02d}"
    for ev, ok in zip(d["evidence"], found):
        ev["verified"] = ok
    d["grounding"] = grounding
    return d


def _sha_file(p: Path) -> str | None:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


async def review(project_id: str, h: RunHandle, iteration: int, previous: dict | None = None,
                 verify: bool = True, root: Path | None = None) -> tuple[dict, Bundle | None]:
    """One review iteration. Returns (mistakes dict without tracking/decision, bundle or None).

    Raises ReviewFailed (judge output unusable) or beta.BetaLimitReached; never returns an
    approval it could not establish.
    """
    root = root or sandbox_for(project_id).root
    h.phase("checking", "Deterministic integrity checks")
    gates = integrity.check(project_id, root)
    report_run = integrity.latest_run(project_id, "report")
    d = _load(project_id)
    base = {
        "schema": "openscientist.mistakes/v1", "project_id": project_id, "iteration": iteration,
        "review_run_id": llm.current_run.get(), "created_at": datetime.now(timezone.utc).isoformat(),
        "model": tier_of(settings.model_judge),
        "inputs": {"report_run_id": report_run.id if report_run else None,
                   "plan_run_id": d["plan"].get("run_id"), "blueprint_run_id": d["bp_run_id"],
                   "manuscript_sha256": _sha_file(root / "paper" / "paper.tex"),
                   "pdf_sha256": _sha_file(root / "paper" / "paper.pdf")},
        "integrity": {"passed": gates["passed"], "hard_failures": gates["hard_failures"], "facts": gates["facts"]},
    }
    if not gates["passed"]:
        h.note(f"Integrity gates failed: {', '.join(sorted({g['gate'] for g in gates['hard_failures']}))}; "
               "the manuscript is not reviewable yet")
        return {**base, "judged": False, "valid": True, "verdict": None, "summary": "Integrity gates failed.",
                "issues": platform_issues(iteration, gates["hard_failures"]), "rubric": [],
                "objective_alignment": None, "hypothesis_support": None, "verdict_consistent": True,
                "grammar_mode": None}, None

    h.phase("bundling", "Assembling the evidence for an independent review")
    bundle = build_bundle(project_id, gates, root)
    if bundle.numeric:
        base["integrity"]["numeric"] = {k: bundle.numeric[k] for k in ("checked", "unmatched_total")}
    base["inputs"].update({
        "bundle_sha256": bundle.sha256,
        "sources": [{"id": s.id, "path": s.path, "sha256": s.sha256, "chars": len(s.text), "truncated": s.truncated}
                    for s in bundle.sources.values()] + [
            {"id": v["id"], "path": v["path"], "sha256": v["sha256"], "bytes": v["bytes"]} for v in bundle.visuals],
        "omitted": bundle.omitted,
    })
    if previous and previous.get("valid") and previous.get("judged") and \
            (previous.get("inputs") or {}).get("bundle_sha256") == bundle.sha256:
        h.note("Evidence unchanged since the last valid review; reusing it")
        reused = {**previous, "iteration": iteration, "review_run_id": base["review_run_id"],
                  "created_at": base["created_at"], "reused_from": previous.get("review_run_id")}
        return reused, bundle

    result = None
    for attempt in range(2):  # a second, fresh review only if verdict and verified issues disagree
        h.phase("judging", "Independent review of the manuscript and its evidence"
                if attempt == 0 else "Second independent review (verdict and issues disagreed)")
        report = await judge_call(bundle, h)
        issues = [_issue_dict(iteration, k, i, bundle) for k, i in enumerate(report.issues, start=1)]
        claims = [i for i in issues if i["severity"] in BLOCKING_SEVERITIES]
        checks: dict[str, IssueCheck] = {}
        verification = "ok" if verify else "disabled"
        if claims and verify:
            h.phase("verifying", f"Adversarial check of {len(claims)} serious claims")
            try:
                checks = {c.ref: c for c in (await verify_call(bundle, claims, root)).checks}
            except (RuntimeError, *TRANSIENT_ERRORS) as exc:
                verification = "failed"
                h.note(f"Verification unavailable ({type(exc).__name__}); using the conservative rule")
        for i in issues:
            classify(i, checks.get(i["ref"]), verification)
        blocking = [i for i in issues if i["blocking"]]
        # Approval needs a verdict that agrees with the reviewer's own assessment, too.
        contradicts = any(r.assessment == "fatal" for r in report.rubric) or \
            report.objective_alignment == "does_not_answer"
        consistent = bool(blocking) or (report.verdict in ("accept", "minor_revision") and not contradicts)
        result = {
            **base, "judged": True, "valid": True, "verdict": report.verdict, "summary": report.summary,
            "score": capped_score(report.score, issues), "score_claimed": report.score,
            "score_rationale": report.score_rationale,
            "upgrades": [{**u.model_dump(), "id": f"R{iteration}-{u.ref}"} for u in report.upgrades][:8],
            "objective_alignment": {"value": report.objective_alignment, "note": report.objective_alignment_note},
            "hypothesis_support": report.hypothesis_support, "rubric": [r.model_dump() for r in report.rubric],
            "issues": issues, "verification": verification if claims else "not_needed",
            "verdict_consistent": consistent, "rejudged": attempt == 1,
            "grammar_mode": llm._GRAMMAR_FALLBACK.get(JudgeReport, "default"),
        }
        if consistent:
            break
    return result, bundle


# ── Files ──────────────────────────────────────────────────────────────────


def review_dir(project_id: str, iteration: int | None = None) -> Path:
    base = plan_agent.EXPORT_DIR / project_id / "review"
    return base / f"iter-{iteration}" if iteration is not None else base


def write_iteration_files(project_id: str, iteration: int, mistakes: dict, bundle: Bundle | None,
                          root: Path | None = None) -> Path:
    root = root or sandbox_for(project_id).root
    out = review_dir(project_id, iteration)
    out.mkdir(parents=True, exist_ok=True)
    (out / "mistakes.json").write_text(json.dumps(mistakes, indent=2, ensure_ascii=False, default=str),
                                       encoding="utf-8")
    if bundle is not None:
        (out / "bundle.md").write_text("".join(bundle.markdown), encoding="utf-8")
    for name in ("paper.tex", "paper.pdf"):
        src = root / integrity.REPORT_DIR / name
        if src.is_file():
            (out / name).write_bytes(src.read_bytes())
    return out
