"""Stage 7 · Consolidation and report.

Consolidation turns the executed workspace (results, logs, checks, figures)
plus the planning context into a structured report scaffold. The Report Agent
then writes a conference-style LaTeX paper from it, compiles a PDF itself, and
code audits the result: citations must come from the literature stage's
references.bib, and a claims audit compares reported numbers with the evidence.
"""

import json
import re
import zipfile
from datetime import date
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..db import Paper, Project, ProjectPaper, Run, TaskState, engine
from ..execution.agent import AgentSpec, run_agent
from ..execution.orchestrator import TEXT_SUFFIXES, model_for
from ..execution.sandbox import sandbox_for
from ..execution.tools import ToolContext
from ..jobs import RunHandle
from ..llm import parse

REPORT_DIR = "paper"
MAX_FILE_CHARS = 4000
MAX_CONTEXT_FILES = 40


# ── Schemas ────────────────────────────────────────────────────────────────


class Finding(BaseModel):
    claim: str = Field(description="One precise sentence")
    evidence: list[str] = Field(description="Artifact paths and the exact numbers they contain")
    strength: Literal["strong", "moderate", "weak"]
    relation: Literal["supports", "contradicts", "partial", "neutral"] = Field(description="Relation to the hypothesis")


class Criterion(BaseModel):
    criterion: str
    status: Literal["met", "not_met", "partial", "unknown"]
    evidence: str


class FigureRef(BaseModel):
    path: str
    caption: str = Field(description="Publication-quality caption stating what is shown and the takeaway")
    section: str


class Section(BaseModel):
    title: str
    purpose: str
    key_points: list[str]
    evidence: list[str] = Field(description="Artifact paths or finding numbers this section relies on")
    citations: list[str] = Field(description="Citation keys from the provided reference list only")


class Scaffold(BaseModel):
    title: str
    one_sentence_summary: str
    hypothesis_verdict: Literal["supported", "not_supported", "inconclusive", "mixed"]
    verdict_explanation: str
    findings: list[Finding]
    success_criteria: list[Criterion]
    figures: list[FigureRef]
    tables: list[str] = Field(description="Tables to include: source artifact and what they show")
    limitations: list[str]
    deviations: list[str] = Field(description="Where execution departed from the plan (failed/skipped tasks, substitutions)")
    outline: list[Section] = Field(description="Paper sections in order: Abstract, Introduction, Related Work, Methods, Results, Discussion, Limitations, Conclusion")
    reproducibility: list[str] = Field(description="Code entry points, environment, data sources, seeds")
    writing_instructions: str = Field(description="Guidance for the Report Agent: tone, emphasis, what not to overclaim")


class AuditIssue(BaseModel):
    claim: str = Field(description="The statement in the paper")
    problem: str = Field(description="How it disagrees with or is unsupported by the evidence")
    severity: Literal["high", "medium", "low"]


class Audit(BaseModel):
    issues: list[AuditIssue]


CONSOLIDATE_INSTRUCTIONS = """\
You are the Consolidation Agent of OpenScientist. Turn a finished investigation into
a report scaffold for the Report Agent. Be rigorous and honest:
- Every finding must cite concrete evidence (artifact path + exact number/value).
- Judge the hypothesis only from the evidence; say "inconclusive" when warranted.
- Record failed, skipped or blocked tasks and substitutions as deviations.
- Figures: only files that exist in the inventory.
- Citations: only keys from the reference list.
Never invent results."""

REPORT_INSTRUCTIONS = """\
You are the Report Agent of OpenScientist. Today's date is {today}. Write a
conference-style paper in LaTeX from the report scaffold, then compile it to PDF.

Rules:
- Write {dir}/paper.tex (article class, 11pt, natbib or plain \\cite with the
  provided {dir}/references.bib; bibliography style plainnat or unsrt).
- Follow the outline. Use ONLY numbers and claims supported by the scaffold's
  findings and the workspace files; read files to confirm numbers. Never invent.
- Cite only keys present in {dir}/references.bib.
- Include the listed figures with \\includegraphics (paths relative to {dir}/,
  e.g. ../figures/x.png) and captions; include tables from the listed artifacts.
- State limitations and deviations honestly; include a reproducibility statement.
- Write like a conference paper: report numbers at sensible precision (usually 3-4
  significant figures, with units), never raw floats; keep file paths, commands
  and task ids out of the abstract and main text — put them in a Reproducibility
  appendix. Refer to methods and results in prose, not by artifact name.
- Compile: install the LaTeX engine with install_conda_packages(["tectonic"])
  if `tectonic` is not on PATH, then run `cd {dir} && tectonic paper.tex`. Fix
  errors until {dir}/paper.pdf exists.
- Finish with report_result listing {dir}/paper.tex, {dir}/paper.pdf and
  {dir}/references.bib."""

AUDIT_INSTRUCTIONS = """\
You audit a scientific paper against its evidence. List statements in the paper
(especially numbers, comparisons and conclusions) that disagree with, overstate, or
are not supported by the evidence given. Ignore style. Return an empty list if
everything is supported."""


# ── Context gathering ──────────────────────────────────────────────────────


def _bib_key(p: Paper, taken: set[str]) -> str:
    surname = re.sub(r"[^A-Za-z]", "", (p.authors[0].split()[-1] if p.authors else p.title.split()[0])) or "anon"
    word = next((w for w in re.findall(r"[A-Za-z]{4,}", p.title)), "paper").lower()
    base = f"{surname.lower()}{p.year or ''}{word}"
    key, n = base, 1
    while key in taken:
        n += 1
        key = f"{base}{n}"
    taken.add(key)
    return key


def _bibtex(key: str, p: Paper) -> str:
    def esc(s: str) -> str:
        return re.sub(r"([&%$#_{}])", r"\\\1", s)

    fields = {
        "title": "{" + esc(p.title) + "}",
        "author": " and ".join(esc(a) for a in (p.authors or ["Anonymous"])),
        "year": str(p.year or ""),
        "journal": esc(p.venue or "Preprint"),
        "doi": p.doi or "",
        "url": p.url or "",
    }
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields.items() if v)
    return f"@article{{{key},\n{body}\n}}"


def _references(project_id: str) -> tuple[dict[str, Paper], str]:
    """Citation keys → papers for everything the literature stage kept, and a .bib text."""
    with Session(engine) as s:
        rows = s.exec(
            select(ProjectPaper, Paper).join(Paper, Paper.id == ProjectPaper.paper_id)
            .where(ProjectPaper.project_id == project_id, ProjectPaper.included)
            .order_by(ProjectPaper.relevance.desc(), ProjectPaper.score.desc())
        ).all()
    taken: set[str] = set()
    refs = {_bib_key(p, taken): p for _, p in rows}
    return refs, "\n\n".join(_bibtex(k, p) for k, p in refs.items())


def _inventory(root: Path) -> list[dict]:
    files = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if p.is_file() and not any(part.startswith(".") or part == "__pycache__" for part in rel.parts):
            files.append({"path": str(rel), "size": p.stat().st_size, "suffix": p.suffix.lower()})
    return files


def _file_digest(root: Path, files: list[dict]) -> str:
    """Contents of the most informative small text artifacts (results first)."""
    def rank(f: dict) -> tuple:
        top = f["path"].split("/")[0]
        return ({"results": 0, "analysis": 1, "team": 2, "docking": 1, "paper": 5}.get(top, 3), f["size"])

    chosen = [f for f in sorted(files, key=rank)
              if f["suffix"] in TEXT_SUFFIXES and f["size"] < 200_000 and not f["path"].startswith(REPORT_DIR + "/")]
    out = []
    for f in chosen[:MAX_CONTEXT_FILES]:
        text = (root / f["path"]).read_text(errors="replace")
        if f["suffix"] in (".csv", ".tsv"):
            lines = text.splitlines()
            text = "\n".join(lines[:25]) + (f"\n… ({len(lines) - 1} data rows total)" if len(lines) > 25 else "")
        out.append(f"### {f['path']}\n{text[:MAX_FILE_CHARS]}")
    return "\n\n".join(out)


def _gather(project_id: str) -> dict:
    with Session(engine) as s:
        project = s.get(Project, project_id)
        bp = s.get(Run, project.blueprint["run_id"]).result["master_plan"]
        states = list(s.exec(select(TaskState).where(TaskState.blueprint_run_id == project.blueprint["run_id"])))
        lit = s.exec(select(Run).where(Run.project_id == project_id, Run.kind == "literature", Run.status == "done")
                     .order_by(Run.started_at.desc())).first()
        cfg = project.settings or {}
        brief, plan, gap = project.brief, project.plan, project.chosen_gap
    return {"brief": brief, "plan": plan, "gap": gap, "blueprint": bp, "states": states,
            "overview": lit.result["overview"] if lit else None, "policy": cfg.get("model_policy", "default"),
            "report_budget": float(cfg.get("report_budget", 1.0))}


# ── Job ────────────────────────────────────────────────────────────────────


async def run(project_id: str, h: RunHandle) -> dict:
    g = _gather(project_id)
    sandbox = sandbox_for(project_id)
    root = sandbox.root
    refs, bib = _references(project_id)
    (root / REPORT_DIR).mkdir(parents=True, exist_ok=True)
    (root / REPORT_DIR / "references.bib").write_text(bib or "% No literature references available\n")
    files = _inventory(root)

    # 1 · Consolidate
    h.phase("consolidating", f"Consolidating {len(g['states'])} tasks and {len(files)} files")
    tasks = "\n".join(
        f"- {st.task_id} [{st.status}] {st.summary or ''} Artifacts: {', '.join(st.artifacts) or 'none'}. "
        f"Checks: {'; '.join(('PASS ' if c['passed'] else 'FAIL ') + c['check'] for c in st.checks) or 'none'}. "
        f"Issues: {'; '.join(st.issues) or 'none'}. {('Note: ' + st.note) if st.note else ''}"
        for st in g["states"]
    )
    ref_list = "\n".join(f"- {k}: {p.title} ({p.year})" for k, p in list(refs.items())[:80]) or "(none)"
    plan = {k: v for k, v in (g["plan"] or {}).items() if k in (
        "title", "research_question", "hypothesis", "null_hypothesis", "objectives", "metrics", "success_criteria",
        "validation_strategy", "background")}
    context = (
        f"BRIEF: {json.dumps(g['brief'], ensure_ascii=False)[:4000]}\n\nCHOSEN GAP: "
        f"{json.dumps({k: g['gap'][k] for k in ('title', 'question', 'hypothesis', 'why_open')} if g['gap'] else None, ensure_ascii=False)}\n\n"
        f"PLAN: {json.dumps(plan, ensure_ascii=False)[:8000]}\n\n"
        f"BLUEPRINT SUMMARY: {g['blueprint']['title']} — {g['blueprint']['summary']}\n\n"
        f"LITERATURE OVERVIEW: {json.dumps(g['overview'], ensure_ascii=False)[:6000] if g['overview'] else '(none)'}\n\n"
        f"REFERENCE KEYS:\n{ref_list}\n\nTASK OUTCOMES:\n{tasks}\n\n"
        f"FILE INVENTORY:\n" + "\n".join(f"- {f['path']} ({f['size']:,} B)" for f in files[:300])
        + f"\n\nFILE CONTENTS:\n{_file_digest(root, files)}"
    )
    scaffold = await parse(
        model=model_for("reasoning", g["policy"]),
        instructions=CONSOLIDATE_INSTRUCTIONS,
        messages=[{"role": "user", "content": context}],
        schema=Scaffold,
        reasoning_effort="medium",
    )
    existing = {f["path"] for f in files}
    scaffold.figures = [f for f in scaffold.figures if f.path in existing]
    for sec in scaffold.outline:
        sec.citations = [c for c in sec.citations if c in refs]
    (root / REPORT_DIR / "scaffold.json").write_text(scaffold.model_dump_json(indent=2))
    h.counts(findings=len(scaffold.findings), figures=len(scaffold.figures))
    h.note(f"Hypothesis: {scaffold.hypothesis_verdict.replace('_', ' ')} · {len(scaffold.findings)} findings")

    # 2 · Write & compile (agentic)
    h.phase("writing", "Writing and compiling the paper")
    spec = AgentSpec(
        name="Report Agent",
        instructions=REPORT_INSTRUCTIONS.format(dir=REPORT_DIR, today=date.today().isoformat()),
        # Writing from a finished scaffold is not flagship work; the standard tier suffices.
        model=model_for("standard", g["policy"]),
        tools=["read_file", "list_files", "write_file", "edit_file", "run_shell", "run_python", "install_conda_packages",
               "report_result"],
        max_steps=60,
        max_cost=g["report_budget"],
        reasoning_effort="medium",
    )
    prompt = (f"Report scaffold ({REPORT_DIR}/scaffold.json):\n{scaffold.model_dump_json()}\n\n"
              f"Citation keys available in {REPORT_DIR}/references.bib: {', '.join(refs) or 'none'}")
    async with httpx.AsyncClient() as http:
        result = await run_agent(spec, prompt, ToolContext(project_id, sandbox, http, agent_name="Report Agent"),
                                 on_event=lambda e: h.note(f"{e.get('tool') or e['type']}: {str(e.get('args') or e.get('text') or '')[:90]}")
                                 if e.get("tool") in ("write_file", "run_shell", "install_conda_packages", "report_result") else None)

    # 3 · Audit
    h.phase("auditing", "Checking citations and claims against the evidence")
    tex_path = root / REPORT_DIR / "paper.tex"
    tex = tex_path.read_text(errors="replace") if tex_path.exists() else ""
    cited = set(re.findall(r"\\cite[pt]?\*?(?:\[[^\]]*\])*\{([^}]*)\}", tex))
    cited_keys = {k.strip() for group in cited for k in group.split(",") if k.strip()}
    unknown_citations = sorted(cited_keys - set(refs))
    audit = Audit(issues=[])
    if tex:
        audit = await parse(
            model=model_for("standard", g["policy"]),
            instructions=AUDIT_INSTRUCTIONS,
            messages=[{"role": "user", "content": f"EVIDENCE (findings):\n{json.dumps([f.model_dump() for f in scaffold.findings], ensure_ascii=False)}"
                       f"\n\nFILE CONTENTS:\n{_file_digest(root, files)[:30000]}\n\nPAPER:\n{tex[:40000]}"}],
            schema=Audit,
            reasoning_effort="low",
        )
    pdf = (root / REPORT_DIR / "paper.pdf").exists()
    h.note("Report complete" if pdf else "Paper written but PDF was not produced")
    return {
        "scaffold": scaffold.model_dump(),
        "agent": {"status": result.status, "summary": result.summary, "cost": result.cost, "issues": result.issues},
        "files": {"tex": tex_path.exists(), "pdf": pdf, "bib": True},
        "citations": {"used": sorted(cited_keys), "unknown": unknown_citations, "available": len(refs)},
        "audit": [i.model_dump() for i in audit.issues],
    }


def package(project_id: str) -> Path:
    """Zip the research package: everything in the workspace except environments and caches."""
    root = sandbox_for(project_id).root
    out = root.parent / f"{project_id}-research-package.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in _inventory(root):
            if f["size"] < 200 * 1024**2:
                z.write(root / f["path"], f"{project_id}/{f['path']}")
    return out
