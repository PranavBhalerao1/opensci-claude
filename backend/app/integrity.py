"""Deterministic integrity checks on a finished manuscript and its workspace (no model calls).

Hard gates block scientific approval: a paper that is missing, not compiled, cites unknown
keys, includes figures that do not exist, was written while its research files changed, or
predates its evidence cannot be reviewed. Soft facts (unmatched numbers, figures without
provenance or older than their code, unfinished tasks, dangling references, placeholders)
are evidence for the judge, never verdicts by themselves.

The PDF is built in the E2B sandbox and the tex is often written on this host, so file
times from the two clocks are compared with a tolerance.
"""

import json
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
    # A % starts a comment unless escaped (\%); after a line break (\\%) it still does.
    return re.sub(r"(?<!\\)((?:\\\\)*)%.*", r"\1", line)


def _escaped(text: str, i: int) -> bool:
    """Whether text[i] is escaped: preceded by an odd run of backslashes (\\{ is a brace, \\\\{ is not)."""
    n = 0
    while i - n > 0 and text[i - n - 1] == "\\":
        n += 1
    return n % 2 == 1


def _group(text: str, start: int) -> tuple[str, int] | None:
    """The balanced argument opening at text[start], a {...} or an optional [...] (braces nested
    inside either; a ] inside braces does not close [...]); returns (inner, end), or None if it is
    never closed."""
    optional = text[start] == "["
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c not in "{}]" or _escaped(text, i):
            continue
        if c == "]":
            if optional and depth == 0:
                return text[start + 1:i], i + 1
            continue
        depth += 1 if c == "{" else -1
        if depth < 0:
            return None
        if depth == 0 and not optional:
            return text[start + 1:i], i + 1
    return None


def _args(text: str, pos: int, spec: str) -> tuple[list[str | None], int] | None:
    """A command's arguments from text[pos] on, by spec: 'o' an optional [...] (None if absent),
    'm' a mandatory {...}. Returns (args, end), or None if a mandatory one is missing or unclosed."""
    out: list[str | None] = []
    for kind in spec:
        i = pos
        while i < len(text) and text[i] in " \t\n":
            i += 1
        if i < len(text) and text[i] == ("[" if kind == "o" else "{"):
            group = _group(text, i)
            if group is None:
                return None
            out.append(group[0])
            pos = group[1]
        elif kind == "o":
            out.append(None)
        else:
            return None
    return out, pos


def _clean_caption(text: str) -> str:
    return re.sub(r"\s+", " ", LABEL_RE.sub(" ", text)).strip()


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
    caption: str = ""  # its own unit's: the sub-figure's when panel, else the figure's
    label: str = ""
    path: str | None = None  # resolved workspace-relative posix path, if the file exists
    panel: bool = False  # inside a sub-figure (subfigure, \subfloat, \subcaptionbox, \subcaption)
    figure_caption: str = ""  # the enclosing figure's own caption and label, when the graphic is
    figure_label: str = ""  # in a sub-figure or captioned minipage inside it (else empty)
    figure_line: int = 0  # line of the enclosing figure's \begin (0 outside any figure)
    note: str = ""  # why a caption could not be extracted (malformed LaTeX), if it could not


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

    # Graphics with their own caption and label, and their enclosing figure's (see _figure_units).
    units = _figure_units(text, line_of)
    for m in GRAPHICS_RE.finditer(text):
        if "#" in m.group(1) or "\\" in m.group(1):  # a macro parameter or path macro, not a file
            continue
        g = Graphic(target=m.group(1).strip(), line=line_of(m.start()))
        _attach(g, m.start(), units)
        info.graphics.append(g)
    return info


# ── Figures, sub-figures, captions and labels ──────────────────────────────
# A figure's \begin/\end pairs are matched as a tree, so a sub-figure is never swallowed by the
# figure around it. A graphic takes the caption and label of its own unit (the sub-figure that
# holds it, or else the figure), and a sub-figure's enclosing figure keeps its own caption and
# label separately. Captions are only ever read from the source: one that cannot be parsed, or
# that belongs to an environment that is never closed, is left empty with a note.

FLOAT_ENVS = frozenset({"figure", "figure*", "wrapfigure", "wrapfigure*", "SCfigure", "sidewaysfigure",
                        "sidewaysfigure*", "table", "table*", "wraptable", "SCtable", "sidewaystable"})
PANEL_ENVS = frozenset({"subfigure", "subfigure*", "subtable", "subtable*"})  # subcaption package
BOX_ENVS = frozenset({"minipage"})  # a unit of its own only when it carries a caption
ENV_RE = re.compile(r"\\(begin|end)\s*\{([^{}]+)\}")
# \caption[short]{text}, \captionof{type}[short]{text}, \subcaption[short]{text}; not \captionsetup,
# \subcaptionbox (a panel command below) or a user macro such as \captionfont.
CAPTION_RE = re.compile(r"\\(caption|captionof|subcaption)(?![a-zA-Z@])\s*\*?")
CAPTION_ARGS = {"caption": ("om", 1), "captionof": ("mom", 2), "subcaption": ("om", 1)}  # (spec, text index)
# Sub-figures written as commands: \subfloat[list][caption]{body} (subfig), \subfigure[..][..]{body}
# (subfigure package), \subcaptionbox[list]{caption}[width][pos]{body} (subcaption).
PANEL_CMD_RE = re.compile(r"\\(subfloat|sidesubfloat|subfigure|subtable|subcaptionbox)(?![a-zA-Z@])\s*\*?")


@dataclass
class _Unit:
    kind: str  # "float", "panel" or "box"
    name: str
    start: int
    end: int
    line: int
    captions: list[tuple[int, str | None, bool]] = field(default_factory=list)  # (pos, text or None, sub)
    labels: list[tuple[int, str]] = field(default_factory=list)
    malformed: str = ""
    command: bool = False  # a sub-figure command (\subfloat...), whose caption is an argument

    def contains(self, pos: int) -> bool:
        return self.start <= pos < self.end


def _figure_units(text: str, line_of) -> list[_Unit]:
    """Every float, sub-figure and minipage in `text`, each with its own captions and labels
    (those not inside a smaller unit nested in it)."""
    units: list[_Unit] = []
    stack: list[tuple[str, int]] = []

    def close(name: str, start: int, end: int, malformed: str = "") -> None:
        kind = "float" if name in FLOAT_ENVS else "panel" if name in PANEL_ENVS else "box" if name in BOX_ENVS else ""
        if kind:
            units.append(_Unit(kind, name, start, end, line_of(start), malformed=malformed))

    for m in ENV_RE.finditer(text):
        if _escaped(text, m.start()):
            continue
        name = m.group(2).strip()
        if m.group(1) == "begin":
            stack.append((name, m.start()))
            continue
        if not any(n == name for n, _ in stack):
            continue  # a stray \end: ignored
        while stack:
            open_name, start = stack.pop()
            if open_name == name:
                close(name, start, m.end())
                break
            close(open_name, start, m.start(), f"\\begin{{{open_name}}} on line {line_of(start)} is never closed")
    for name, start in stack:
        close(name, start, len(text), f"\\begin{{{name}}} on line {line_of(start)} is never closed")

    for m in PANEL_CMD_RE.finditer(text):
        if _escaped(text, m.start()):
            continue
        box = m.group(1) == "subcaptionbox"
        parsed = _args(text, m.end(), "omoom" if box else "oom")
        if parsed is None:
            around = [u for u in units if u.contains(m.start())]
            end = min((u.end for u in around), default=len(text))
            units.append(_Unit("panel", m.group(1), m.start(), end, line_of(m.start()), command=True,
                               malformed=f"the arguments of \\{m.group(1)} on line {line_of(m.start())} "
                                         "could not be parsed"))
            continue
        args, end = parsed
        caption = args[1] if box else (args[1] if args[1] is not None else args[0])
        unit = _Unit("panel", m.group(1), m.start(), end, line_of(m.start()), command=True)
        if caption is not None:
            unit.captions.append((m.start(), _clean_caption(caption), True))
        units.append(unit)

    def owner(pos: int) -> _Unit | None:
        return min((u for u in units if u.contains(pos)), key=lambda u: u.end - u.start, default=None)

    for m in CAPTION_RE.finditer(text):
        u = owner(m.start())
        if u is None or u.command or _escaped(text, m.start()):
            continue  # outside any figure, or a command panel, whose caption is its argument
        spec, index = CAPTION_ARGS[m.group(1)]
        parsed = _args(text, m.end(), spec)
        caption = _clean_caption(parsed[0][index]) if parsed else None
        u.captions.append((m.start(), caption, m.group(1) == "subcaption"))
    for m in LABEL_RE.finditer(text):
        u = owner(m.start())
        if u is not None:
            u.labels.append((m.start(), m.group(1).strip()))
    for u in units:
        u.captions.sort()
    return units


def _caption_at(u: _Unit, pos: int) -> tuple[str, str, bool, str]:
    """(caption, label, is_sub_caption, note) of unit u for something at `pos` in it. With several
    captions (two figures in one float), the first one after pos, else the last before it. A label
    belongs to the caption it follows (or to the first, if it precedes them all)."""
    if u.malformed:
        return "", "", False, u.malformed
    if not u.captions:
        return "", u.labels[0][1] if u.labels else "", False, ""
    k = next((i for i, c in enumerate(u.captions) if c[0] > pos), len(u.captions) - 1)
    owners = [max((i for i, c in enumerate(u.captions) if c[0] < at), default=0) for at, _ in u.labels]
    label = next((name for (at, name), i in zip(u.labels, owners) if i == k), "")
    _, caption, sub = u.captions[k]
    if caption is None:
        return "", label, sub, f"the caption on line {u.line} could not be parsed"
    return caption, label, sub, ""


def _attach(g: Graphic, pos: int, units: list[_Unit]) -> None:
    """Set g's caption and label from its own unit, and its enclosing figure's separately."""
    chain = sorted((u for u in units if u.contains(pos)), key=lambda u: u.end - u.start)
    # A minipage without a caption only lays things out: the graphic belongs to what encloses it.
    own = next((u for u in chain if u.kind != "box" or u.captions or u.malformed), None)
    if own is None:
        return
    g.caption, g.label, sub, g.note = _caption_at(own, pos)
    g.panel = own.kind == "panel" or sub
    outer = next((u for u in chain if u.kind == "float" and u.start <= own.start and u is not own), None)
    if own.kind == "float":
        g.figure_line = own.line
    elif outer is not None:
        g.figure_line = outer.line
        g.figure_caption, g.figure_label, _, note = _caption_at(outer, own.start)
        g.note = g.note or note


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


# Workspace copies of the pre-registered plan/brief/gap, written once for agents to read
# (execution/orchestrator.py's _write_context) and refreshed every time an execution run
# starts. Nothing downstream re-reads them for verification — report.py and judge.py both
# use the authoritative database rows — but a mismatch is still a legitimate-vs-illegitimate
# signal: an agent (or buggy tool code) silently editing its own copy of the pre-registered
# protocol, e.g. to make an impossible success criterion look already satisfied, is exactly
# the kind of change that must never pass unnoticed.
PROTOCOL_FILES = (("context/plan.json", "plan"), ("context/brief.json", "brief"),
                  ("context/chosen_gap.json", "chosen_gap"))


def protocol_file_tamper(root: Path, project_id: str) -> list[str]:
    """Workspace copies of the pre-registered plan/brief/gap that no longer match what the
    project actually has approved. Soft (non-blocking): it is evidence for the judge, not a
    verdict by itself, since downstream verification never trusts these files anyway."""
    with Session(engine) as s:
        project = s.get(Project, project_id)
    if project is None:
        return []
    authoritative = {"plan": project.plan, "brief": project.brief, "chosen_gap": project.chosen_gap}
    out = []
    for rel, field_name in PROTOCOL_FILES:
        want = authoritative[field_name]
        p = root / rel
        if not want or not p.is_file():
            continue
        try:
            on_disk = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            out.append(f"{rel} could not be parsed as JSON; it may have been altered since it was written.")
            continue
        if json.dumps(on_disk, sort_keys=True, default=str) != json.dumps(want, sort_keys=True, default=str):
            out.append(f"{rel} in the workspace no longer matches the approved {field_name}; it, or the "
                       "experimental protocol it describes, may have been edited after it was written.")
    return out


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


# ── Undisclosed provider mentions ──────────────────────────────────────────
# The platform does not disclose the model or provider behind it (app/llm.py: IDENTITY), and the
# agents write the manuscript and the code themselves, so the prompt rule is not a guarantee. These
# two patterns are deliberately narrow, because AI models are legitimate subjects of research: a
# paper may name, cite, benchmark or compare any model it studies, and that must not be flagged.
# Only the deployment's own identifiers, and this study's work attributed to a named vendor model,
# are reported — as soft facts for the judge, never a hard failure over a word.

_VENDORS = r"claude|anthropic|bedrock|sonnet|opus|haiku"
# An inference-profile id, SDK class or credential name: no subject of research needs the identifiers
# of the deploy that produced the paper.
PROVIDER_ID_RE = re.compile(
    r"\b(?:us|eu|apac)\.anthropic\.[\w.-]+"
    r"|\banthropic\.claude[\w.-]*"
    r"|\bAnthropicBedrock\w*"
    r"|\bbedrock-runtime\b"
    r"|\bANTHROPIC_API_KEY\b",
    re.IGNORECASE)
# "written with Claude", "generated by Anthropic's model", "analysis produced using Sonnet": the
# work of this study credited to a named vendor model.
ATTRIBUTION_RE = re.compile(
    r"\b(?:written|authored|drafted|generated|produced|created|prepared|composed|assisted|powered|built)\b"
    r"[^.\n]{0,60}?\b(?:by|with|using|on)\b"
    rf"[^.\n]{{0,40}}?\b(?:{_VENDORS})\b",
    re.IGNORECASE)

PROVIDER_FACT = (
    "OpenScientist does not disclose the model or provider behind it, and these lines either carry "
    "the deployment's own model identifiers or credit this study's work to a named outside model; "
    "rewrite them to name OpenScientist, or drop them. A line that names a model as a subject of "
    "the research — a system under study, a baseline, or a citation — is correct as written and "
    "needs no change.")


def provider_lines(text: str, limit: int = 20) -> list[int]:
    """1-based line numbers in `text` that disclose the platform's own model or provider."""
    out = [n for n, line in enumerate(text.splitlines(), start=1)
           if PROVIDER_ID_RE.search(line) or ATTRIBUTION_RE.search(line)]
    return out[:limit]


def provider_mentions(tex: str, files: dict[str, Path]) -> list[str]:
    """Soft facts for the manuscript and the workspace's code files. The manuscript is scanned whole,
    comments included: a LaTeX comment never reaches the PDF, but paper.tex is a file the user can
    download. The facts carry line numbers only, so reporting a disclosure does not repeat it."""
    facts = []
    lines = provider_lines(tex)
    if lines:
        facts.append("Manuscript lines " + ", ".join(f"L{n:04d}" for n in lines) + ": " + PROVIDER_FACT)
    flagged = {}
    for rel, p in files.items():
        try:
            found = provider_lines(p.read_text(encoding="utf-8", errors="replace")[:1_000_000], limit=5)
        except OSError:
            continue
        if found:
            flagged[rel] = found
    if flagged:
        where = "; ".join(f"{rel} (line{'s' if len(ns) > 1 else ''} {', '.join(map(str, ns))})"
                          for rel, ns in list(flagged.items())[:10])
        facts.append(f"Code files naming the model or provider behind OpenScientist: {where}. " + PROVIDER_FACT)
    return facts


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
    facts.extend(protocol_file_tamper(root, project_id))
    dangling = sorted(k for k in info.refs if k not in info.labels)
    if dangling:
        facts.append("\\ref targets with no matching \\label: " + ", ".join(dangling[:20]))
    placeholders = [f"L{n}" for n in range(info.body[0] + 1, info.body[1] + 1)
                    if PLACEHOLDER_RE.search(info.lines[n - 1])]
    if placeholders:
        facts.append("Placeholder text (TODO/TBD/??? etc.) on manuscript lines " + ", ".join(placeholders[:20]))
    facts.extend(provider_mentions(tex, files))

    return {"passed": not hard, "hard_failures": hard, "facts": facts, "figures": figures, "tex": info,
            "figure_code": figure_code, "report_run_id": report.id if report else None}
