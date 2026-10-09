"""Deterministic integrity checks on a finished manuscript and its workspace (no model calls).

Hard gates block scientific approval: a paper that is missing, not compiled, cites unknown
keys, includes figures that do not exist, was written while its research files changed, or
predates its evidence cannot be reviewed. Soft facts (unmatched numbers, figures without
provenance or older than their code, unfinished tasks, dangling references, placeholders)
are evidence for the judge, never verdicts by themselves.

The PDF is built in the E2B sandbox and the tex is often written on this host, so file
times from the two clocks are compared with a tolerance.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, select

from .db import Project, Run, TaskState, engine
from .execution.sandbox import sandbox_for

REPORT_DIR = "paper"
CLOCK_TOLERANCE = 120.0  # seconds between the host and sandbox clocks
MAX_UNMATCHED = 40
CODE_SUFFIXES = {".py", ".r", ".jl", ".m", ".sh", ".ipynb"}
GRAPHIC_EXTENSIONS = ("", ".png", ".pdf", ".jpg", ".jpeg", ".eps", ".svg")
UNFINISHED = ("failed", "blocked", "skipped", "human", "cancelled", "pending", "running")

# Every natbib/biblatex cite form, \nocite included: \cite, \citep, \citet*, \citealp[..]{a,b}.
CITE_RE = re.compile(r"\\(?:no)?cite[a-zA-Z]*\*?(?:\[[^\]]*\])*\{([^}]*)\}")
GRAPHICS_RE = re.compile(r"\\includegraphics\*?(?:\[[^\]]*\])?\{([^}]*)\}")
GRAPHICSPATH_RE = re.compile(r"\\graphicspath\{((?:\s*\{[^}]*\})+)\s*\}")
LABEL_RE = re.compile(r"\\label\{([^}]*)\}")
REF_RE = re.compile(r"\\(?:auto|c|C|eq|page|name|v)?ref\*?\{([^}]*)\}")
BIB_KEY_RE = re.compile(r"@\w+\s*\{\s*([^,\s]+)\s*,")
PLACEHOLDER_RE = re.compile(r"\b(TODO|TBD|FIXME|XXX)\b|lorem ipsum|citation needed|\?\?\?", re.IGNORECASE)
# Command arguments that hold layout, not results: stripped before numbers are read.
_NOISE_RE = re.compile(
    r"\\(?:begin|end|usepackage|documentclass|hspace|vspace|setlength|addtolength|resizebox|scalebox|"
    r"includegraphics|input|include|bibliography|bibliographystyle|label|ref|eqref|autoref|cref|Cref|"
    r"pageref|url|href|multicolumn|multirow|cline|cmidrule|arraystretch|renewcommand|newcommand|"
    r"definecolor|color|textcolor|captionsetup|graphicspath)\*?(?:\[[^\]]*\])*(?:\{[^{}]*\})*"
)
_LENGTH_RE = re.compile(r"\d*\.?\d+\s*\\(?:linewidth|textwidth|columnwidth|textheight|baselineskip)")
_DIMENSION_RE = re.compile(r"\d*\.?\d+\s*(?:pt|cm|mm|in|em|ex)\b")
# A number in prose or a table cell: not part of an identifier (T4.1, ResNet-50, v2.0).
_NUMBER_RE = re.compile(r"(?<![\w.\-/])([-−]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[-−]?\d+(?:\.\d+)?)(\s*\\?%)?(?![\w.])")
_EVIDENCE_NUMBER_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


# ── LaTeX parsing ──────────────────────────────────────────────────────────


def strip_comments(line: str) -> str:
    return re.sub(r"(?<!\\)%.*", "", line)


def _braced(text: str, start: int) -> tuple[str, int]:
    """The balanced {...} group starting at text[start] == '{'; returns (inner, end)."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{" and (i == 0 or text[i - 1] != "\\"):
            depth += 1
        elif text[i] == "}" and text[i - 1] != "\\":
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i + 1
    return text[start + 1:], len(text)


def _caption(block: str) -> str:
    m = re.search(r"\\caption\*?(?:\[[^\]]*\])?\s*\{", block)
    if not m:
        return ""
    inner, _ = _braced(block, m.end() - 1)
    return re.sub(r"\s+", " ", inner).strip()


def _sentence(line: str, pos: int, limit: int = 320) -> str:
    """The sentence of `line` that contains position `pos`."""
    left = max(line.rfind(". ", 0, pos), line.rfind("\n", 0, pos))
    right = line.find(". ", pos)
    text = line[left + 1 if left >= 0 else 0: right + 1 if right >= 0 else len(line)].strip()
    return text if len(text) <= limit else text[:limit] + "…"


def _context(lines: list[str], idx: int, pos: int, limit: int = 320) -> str:
    """The sentence around position `pos` of lines[idx], joined across the neighbouring source
    lines (LaTeX wraps sentences over several lines)."""
    before = " ".join(x.strip() for x in lines[max(0, idx - 2):idx])
    after = " ".join(x.strip() for x in lines[idx + 1:idx + 3])
    line = lines[idx]
    offset = len(before) + 1 if before else 0
    joined = (before + " " if before else "") + line + (" " + after if after else "")
    return _sentence(joined, offset + pos, limit)


@dataclass
class Graphic:
    target: str  # as written in \includegraphics
    line: int
    caption: str = ""
    label: str = ""
    path: str | None = None  # resolved workspace-relative posix path, if the file exists


@dataclass
class TexInfo:
    lines: list[str]  # comment-stripped source lines
    body: tuple[int, int]  # line indices [start, end) of the document body
    cites: dict[str, list[tuple[int, str]]] = field(default_factory=dict)  # key → [(line no, sentence)]
    graphics: list[Graphic] = field(default_factory=list)
    graphicspath: list[str] = field(default_factory=list)
    labels: set[str] = field(default_factory=set)
    refs: dict[str, int] = field(default_factory=dict)  # label → first line it is referenced on

    @property
    def cite_keys(self) -> set[str]:
        return set(self.cites)


def parse_tex(tex: str) -> TexInfo:
    lines = [strip_comments(x) for x in tex.splitlines()]
    begin = next((i for i, x in enumerate(lines) if "\\begin{document}" in x), 0)
    end = next((i for i, x in enumerate(lines) if "\\end{document}" in x), len(lines))
    info = TexInfo(lines=lines, body=(begin, end))
    text = "\n".join(lines)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line) + 1)

    def line_of(pos: int) -> int:
        lo, hi = 0, len(offsets) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if offsets[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    for m in GRAPHICSPATH_RE.finditer(text):
        info.graphicspath += re.findall(r"\{([^}]*)\}", m.group(1))
    for m in CITE_RE.finditer(text):  # on the whole text: key lists may span lines
        n = line_of(m.start())
        for key in (k.strip() for k in m.group(1).split(",")):
            if key and key != "*":  # \nocite{*} adds the whole bibliography
                info.cites.setdefault(key, []).append((n, _context(lines, n - 1, m.start() - offsets[n - 1])))
    for n, line in enumerate(lines, start=1):
        info.labels.update(m.group(1).strip() for m in LABEL_RE.finditer(line))
        for m in REF_RE.finditer(line):
            for key in (k.strip() for k in m.group(1).split(",")):
                info.refs.setdefault(key, n)

    # Graphics with their figure's caption and label (figure and figure* environments).
    figures = [(m.start(), m.end()) for m in
               re.finditer(r"\\begin\{(figure\*?|wrapfigure|subfigure)\}.*?\\end\{\1\}", text, re.DOTALL)]
    for m in GRAPHICS_RE.finditer(text):
        if "#" in m.group(1) or "\\" in m.group(1):  # a macro parameter or path macro, not a file
            continue
        g = Graphic(target=m.group(1).strip(), line=line_of(m.start()))
        env = next(((a, b) for a, b in figures if a <= m.start() < b), None)
        if env:
            block = text[env[0]:env[1]]
            g.caption = _caption(block)
            labels = LABEL_RE.findall(block)
            g.label = labels[0].strip() if labels else ""
        info.graphics.append(g)
    return info


def bib_keys(bib: str) -> set[str]:
    return {m.group(1).strip() for m in BIB_KEY_RE.finditer(bib)}


def resolve_graphic(root: Path, target: str, graphicspath: list[str]) -> str | None:
    """Workspace-relative posix path of an \\includegraphics target (relative to paper/), or None."""
    base = root / REPORT_DIR
    for prefix in ["", *graphicspath]:
        for ext in GRAPHIC_EXTENSIONS:
            try:
                p = (base / prefix / f"{target}{ext}").resolve()
            except OSError:
                continue
            if (p == root or root in p.parents) and p.is_file():
                return p.relative_to(root).as_posix()
    return None


# ── Workspace scans ────────────────────────────────────────────────────────


def _visible(rel: Path) -> bool:
    return not any(part.startswith(".") or part == "__pycache__" for part in rel.parts)


def workspace_manifest(root: Path, exclude_top: tuple[str, ...] = (REPORT_DIR,)) -> dict[str, tuple[int, int]]:
    """(size, mtime_ns) of every visible file outside the excluded top-level directories."""
    out: dict[str, tuple[int, int]] = {}
    if not root.exists():
        return out
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if not _visible(rel) or rel.parts[0] in exclude_top or not p.is_file():
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        out[rel.as_posix()] = (st.st_size, st.st_mtime_ns)
    return out


def manifest_violations(before: dict, after: dict, started: datetime, protected: set[str],
                        tolerance: float = CLOCK_TOLERANCE) -> dict[str, list[str]]:
    """What the report stage did to research files.

    hard: an existing file was rewritten (new signature and a modification time from this stage),
    or a declared research output was deleted. soft: new files, other deletions. Files that only
    arrive late from the sandbox keep their older remote modification times, so they are not hard.
    """
    cutoff = (_aware(started).timestamp() - tolerance) * 1e9
    modified = sorted(p for p, sig in after.items() if p in before and before[p] != sig and sig[1] >= cutoff)
    deleted = sorted(p for p in before if p not in after)
    hard_deleted = [p for p in deleted if _under(p, protected)]
    return {
        "hard": modified + [f"{p} (deleted)" for p in hard_deleted],
        "soft": [f"{p} (new)" for p in sorted(set(after) - set(before))]
                + [f"{p} (deleted)" for p in deleted if p not in hard_deleted],
    }


def _under(path: str, prefixes: set[str]) -> bool:
    return any(path == q.rstrip("/") or path.startswith(q.rstrip("/") + "/") for q in prefixes)


def code_files(root: Path, limit: int = 3000) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if p.suffix.lower() in CODE_SUFFIXES and _visible(rel) and p.is_file():
            out[rel.as_posix()] = p
            if len(out) >= limit:
                break
    return out


def code_references(root: Path, names: list[str], files: dict[str, Path] | None = None) -> dict[str, list[str]]:
    """For each workspace file (e.g. 'figures/main_effect.png'), the code files that name it:
    its file name, or its stem as a whole word (scripts often add the extension separately)."""
    files = code_files(root) if files is None else files
    refs: dict[str, list[str]] = {n: [] for n in names}
    patterns = {n: re.compile(rf"{re.escape(Path(n).name)}|(?<![\w]){re.escape(Path(n).stem)}(?![\w])")
                for n in names if Path(n).stem}
    for rel, p in files.items():
        try:
            text = p.read_text(encoding="utf-8", errors="replace")[:1_000_000]
        except OSError:
            continue
        for n, pattern in patterns.items():
            if pattern.search(text):
                refs[n].append(rel)
    return refs


# ── Numeric cross-check ────────────────────────────────────────────────────


def _decimals(s: str) -> int:
    return len(s.split(".", 1)[1]) if "." in s else 0


def manuscript_numbers(info: TexInfo) -> list[dict]:
    """Reported numbers in the body worth checking: decimals, percentages, integers >= 100
    (not years). Layout arguments, citations and references are stripped first."""
    out = []
    start, end = info.body
    for i in range(start, end):
        raw = info.lines[i]
        if "\\bibliography" in raw:
            break
        line = _NOISE_RE.sub(" ", CITE_RE.sub(" ", raw))
        line = _DIMENSION_RE.sub(" ", _LENGTH_RE.sub(" ", line)).replace("--", " -- ")  # ranges: 0.88--0.94
        for m in _NUMBER_RE.finditer(line):
            text, pct = m.group(1).replace("−", "-"), bool(m.group(2))
            digits = text.replace(",", "")
            try:
                value = float(digits)
            except ValueError:
                continue
            decimal = "." in digits
            if not decimal and not pct:
                if abs(value) < 100 or (1900 <= value <= 2100 and len(digits.lstrip("-")) == 4):
                    continue
            out.append({"text": m.group(0).strip(), "value": value, "decimals": _decimals(digits), "percent": pct,
                        "line": i + 1, "context": _sentence(line, m.start(), 200)})
    return out


def _keys(value: float, decimals: int) -> set[str]:
    """Printed forms of an evidence value at `decimals` places (as is, or as a percentage);
    the nudges let exact halves match whichever way the writer rounded them."""
    out = set()
    for v in (abs(value), abs(value) * 100):
        for nudge in (0.0, 1e-9, -1e-9):
            out.add(f"{max(v + nudge * max(1.0, v), 0.0):.{decimals}f}")
    return out


def numeric_crosscheck(info: TexInfo, evidence_texts: list[str], limit: int = MAX_UNMATCHED) -> dict:
    """Manuscript numbers that no evidence text contains at the printed precision (heuristic:
    derived values such as differences or ratios also appear unmatched)."""
    numbers = manuscript_numbers(info)
    pool: list[float] = []
    for text in evidence_texts:
        for m in _EVIDENCE_NUMBER_RE.finditer(text):
            try:
                pool.append(float(m.group(0)))
            except ValueError:
                continue
            if len(pool) >= 300_000:
                break
    wanted = {n["decimals"] for n in numbers}
    seen: set[tuple[int, str]] = set()
    for v in pool:
        for d in wanted:
            for k in _keys(v, d):
                seen.add((d, k))
    unmatched = []
    for n in numbers:
        if (n["decimals"], f"{abs(n['value']):.{n['decimals']}f}") in seen:
            continue
        unmatched.append(n)
    return {"checked": len(numbers), "unmatched": unmatched[:limit], "unmatched_total": len(unmatched)}


# ── Gates and facts ────────────────────────────────────────────────────────


def _aware(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime.fromtimestamp(0, timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _mtime(p: Path) -> float:
    return p.stat().st_mtime


def latest_run(project_id: str, kind: str) -> Run | None:
    with Session(engine) as s:
        return s.exec(select(Run).where(Run.project_id == project_id, Run.kind == kind)
                      .order_by(Run.started_at.desc())).first()


def _blueprint(project_id: str) -> tuple[dict, list[TaskState]]:
    with Session(engine) as s:
        project = s.get(Project, project_id)
        bp_id = (project.blueprint or {}).get("run_id") if project else None
        bp = s.get(Run, bp_id) if bp_id else None
        mp = (bp.result or {}).get("master_plan", {}) if bp else {}
        states = list(s.exec(select(TaskState).where(TaskState.blueprint_run_id == bp_id))) if bp_id else []
    return mp, states


def declared_outputs(mp: dict, states: list[TaskState] | None = None, done_only: bool = False) -> set[str]:
    ok = {st.task_id for st in states or [] if st.status == "done"}
    return {o["path"] for t in mp.get("tasks", []) for o in t.get("outputs", [])
            if not done_only or t["id"] in ok}


def _gate(gate: str, severity: str, title: str, detail: str, paths: list[str] | None = None) -> dict:
    return {"gate": gate, "severity": severity, "title": title, "detail": detail, "paths": paths or []}


def check(project_id: str, root: Path | None = None) -> dict:
    """Hard gates and soft facts for the project's current manuscript.

    Returns {passed, hard_failures: [...], facts: [...], figures: [...], tex: TexInfo | None,
    figure_code: {figure path: [code files]}, report_run_id}.
    """
    root = root or sandbox_for(project_id).root
    report = latest_run(project_id, "report")
    execute = latest_run(project_id, "execute")
    mp, states = _blueprint(project_id)
    hard: list[dict] = []
    facts: list[str] = []
    tex_path, pdf_path, bib_path = (root / REPORT_DIR / n for n in ("paper.tex", "paper.pdf", "references.bib"))

    if report is None or report.status != "done":
        hard.append(_gate("H1", "FATAL", "No finished report", "The report stage has not completed successfully."))
    if not tex_path.is_file():
        hard.append(_gate("H1", "FATAL", "Manuscript missing", "paper/paper.tex does not exist.", ["paper/paper.tex"]))
        return {"passed": False, "hard_failures": hard, "facts": facts, "figures": [], "tex": None,
                "figure_code": {}, "report_run_id": report.id if report else None}

    tex = tex_path.read_text(encoding="utf-8", errors="replace")
    info = parse_tex(tex)
    started = _aware(report.started_at).timestamp() if report else 0.0
    if not pdf_path.is_file() or pdf_path.stat().st_size == 0:
        hard.append(_gate("H1", "FATAL", "PDF not compiled", "paper/paper.pdf is missing or empty.", ["paper/paper.pdf"]))
    else:
        if report and _mtime(pdf_path) < started - CLOCK_TOLERANCE:
            hard.append(_gate("H1", "FATAL", "PDF predates this report",
                              "paper/paper.pdf was not rebuilt by the latest report run.", ["paper/paper.pdf"]))
        if _mtime(tex_path) > _mtime(pdf_path) + CLOCK_TOLERANCE:
            hard.append(_gate("H1", "FATAL", "PDF older than its source",
                              "paper/paper.tex changed after paper/paper.pdf was compiled.", ["paper/paper.pdf"]))

    known = bib_keys(bib_path.read_text(encoding="utf-8", errors="replace")) if bib_path.is_file() else set()
    unknown = sorted(info.cite_keys - known)
    if unknown:
        hard.append(_gate("H2", "MAJOR", "Unknown citation keys",
                          f"Cited keys not in paper/references.bib: {', '.join(unknown[:20])}", ["paper/references.bib"]))

    figures = []
    for g in info.graphics:
        g.path = resolve_graphic(root, g.target, info.graphicspath)
        figures.append(g)
    missing = [g.target for g in figures if g.path is None]
    if missing:
        hard.append(_gate("H3", "MAJOR", "Missing figure files",
                          f"\\includegraphics targets that do not exist: {', '.join(missing[:20])}", missing))

    guard = ((report.result or {}).get("integrity") or {}) if report and report.status == "done" else {}
    if guard.get("hard"):
        hard.append(_gate("H4", "FATAL", "Report stage modified research files",
                          "Files outside paper/ were changed while the paper was written: "
                          + ", ".join(guard["hard"][:20]), [p.split(" (")[0] for p in guard["hard"]]))
    if guard.get("soft"):
        facts.append("Files that appeared or disappeared outside paper/ while the paper was written: "
                     + ", ".join(guard["soft"][:20]))

    if report and execute and (execute.status == "running" or (
            execute.finished_at and _aware(execute.finished_at) > _aware(report.started_at))):
        hard.append(_gate("H5", "MAJOR", "Evidence changed after the paper was written",
                          "An execution run finished (or is running) after the latest report run started."))

    # Soft facts.
    paths = [g.path for g in figures if g.path]
    files = code_files(root)
    figure_code = code_references(root, paths, files)
    outputs = declared_outputs(mp, states, done_only=True)
    for p in paths:
        refs = figure_code.get(p, [])
        if not _under(p, outputs) and not refs:
            facts.append(f"Figure {p} is neither a declared output of a completed task nor referenced by any code "
                         "file (provenance unknown).")
        newer = [r for r in refs if _mtime(files[r]) > _mtime(root / p) + CLOCK_TOLERANCE]
        if newer:
            facts.append(f"Figure {p} is older than code that references it ({', '.join(newer[:5])}); it may not "
                         "reflect the current analysis.")
    unfinished = [f"{st.task_id} [{st.status}]" for st in states if st.status in UNFINISHED]
    if unfinished:
        facts.append("Blueprint tasks not completed: " + ", ".join(unfinished))
    dangling = sorted(k for k in info.refs if k not in info.labels)
    if dangling:
        facts.append("\\ref targets with no matching \\label: " + ", ".join(dangling[:20]))
    placeholders = [f"L{n}" for n in range(info.body[0] + 1, info.body[1] + 1)
                    if PLACEHOLDER_RE.search(info.lines[n - 1])]
    if placeholders:
        facts.append("Placeholder text (TODO/TBD/??? etc.) on manuscript lines " + ", ".join(placeholders[:20]))

    return {"passed": not hard, "hard_failures": hard, "facts": facts, "figures": figures, "tex": info,
            "figure_code": figure_code, "report_run_id": report.id if report else None}
