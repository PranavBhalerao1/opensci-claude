"""Deterministic manuscript and workspace integrity checks (app/integrity.py), offline."""

import os
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, select

from app import integrity as ig
from app.db import Project, Run, TaskState, engine

TEX = r"""\documentclass[11pt]{article}
\usepackage{graphicx}
\graphicspath{{../figs/}}
\begin{document}
\section{Results}
Accuracy rose to 0.912 (95\% CI 0.88--0.94) over 1,200 samples in 2023 \citep{smith2020data}.
% a commented 0.555 must be ignored \cite{ghost}
The effect was 45.2\% larger than the baseline \citealp[p.~3]{lee2019}; see Fig.~\ref{fig:main} and Table~\ref{tab:x}.
\begin{figure}[t]
  \centering
  \includegraphics[width=0.8\linewidth]{../figures/main}
  \caption{Main effect {\em across} seeds. TODO}
  \label{fig:main}
\end{figure}
\includegraphics{curve.png}
We trained ResNet-50 for 3 epochs on T4.1 outputs; the slope was $-1.31$.
\nocite{extra}
\bibliography{references}
Numbers after the bibliography 9.99 are ignored.
\end{document}
"""


def test_parse_tex_cites_graphics_refs_and_comments():
    info = ig.parse_tex(TEX)
    assert info.cite_keys == {"smith2020data", "lee2019", "extra"}  # \cite{ghost} is commented out
    assert info.graphicspath == ["../figs/"]
    main, curve = info.graphics
    assert (main.target, main.label) == ("../figures/main", "fig:main")
    assert main.caption.startswith("Main effect") and "TODO" in main.caption
    assert curve.target == "curve.png" and curve.caption == ""
    assert "fig:main" in info.labels and set(info.refs) == {"fig:main", "tab:x"}
    line, sentence = info.cites["smith2020data"][0]
    assert line == 6 and "Accuracy rose" in sentence


def test_bibliography_wildcards_macro_graphics_and_multiline_cites():
    tex = ("\\begin{document}\n\\nocite{*}\n\\newcommand{\\fig}[1]{\\includegraphics{#1}}\n"
           "\\includegraphics{\\figdir/x.png}\nAs shown \\citep{alpha2020,\n  beta2021}.\n\\end{document}")
    info = ig.parse_tex(tex)
    assert info.cite_keys == {"alpha2020", "beta2021"} and info.graphics == []
    assert info.cites["beta2021"][0][0] == 5


def test_resolve_graphic_tries_extensions_and_graphicspath(tmp_path):
    (tmp_path / "paper").mkdir()
    (tmp_path / "figures").mkdir()
    (tmp_path / "figs").mkdir()
    (tmp_path / "figures" / "main.png").write_bytes(b"png")
    (tmp_path / "figs" / "curve.png").write_bytes(b"png")
    assert ig.resolve_graphic(tmp_path, "../figures/main", []) == "figures/main.png"
    assert ig.resolve_graphic(tmp_path, "curve.png", ["../figs/"]) == "figs/curve.png"
    assert ig.resolve_graphic(tmp_path, "missing", ["../figs/"]) is None
    assert ig.resolve_graphic(tmp_path, "../../outside", []) is None


def test_numeric_crosscheck_rounding_percentages_and_exclusions():
    info = ig.parse_tex(TEX)
    nums = {n["text"] for n in ig.manuscript_numbers(info)}
    # Decimals, percentages and large integers are checked; years, small integers, widths,
    # identifiers (ResNet-50, T4.1), comments and the bibliography tail are not.
    assert {"0.912", "0.88", "0.94", "1,200", "45.2\\%", "-1.31"} <= nums
    assert not nums & {"2023", "3", "0.8", "50", "4.1", "0.555", "9.99"}
    evidence = ["acc,ci_lo,ci_hi,n\n0.91234,0.8801,0.9399,1200\n", '{"rel_gain": 0.4521, "slope": -1.3104}']
    result = ig.numeric_crosscheck(info, evidence)
    unmatched = {n["text"] for n in result["unmatched"]}
    assert unmatched <= {"95\\%"}  # 95% CI level is not in the evidence; everything else matches
    result = ig.numeric_crosscheck(info, ["0.5"])
    assert "0.912" in {n["text"] for n in result["unmatched"]}


def test_exact_halves_match_either_rounding():
    info = ig.parse_tex("\\begin{document}\nvalue 0.13 and 0.12\n\\end{document}")
    assert ig.numeric_crosscheck(info, ["0.125"])["unmatched"] == []


def test_manifest_violations_ignore_late_sandbox_arrivals(tmp_path):
    started = datetime.now(timezone.utc)
    old = (started - timedelta(hours=1)).timestamp() * 1e9
    new = started.timestamp() * 1e9
    before = {"results/a.csv": (10, old), "figures/f.png": (5, old), "notes/tmp.txt": (1, old)}
    after = {
        "results/a.csv": (12, new),          # rewritten during the report: hard
        "figures/f.png": (5, old),            # unchanged
        "data/late.parquet": (9, old),        # arrived late from the sandbox: soft (new)
        "logs/x.log": (3, old - 1e9),         # changed signature but old mtime (late sync): not hard
    }
    before["logs/x.log"] = (2, old - 2e9)
    v = ig.manifest_violations(before, after, started, protected={"results/", "figures/f.png"})
    assert v["hard"] == ["results/a.csv"]
    assert "data/late.parquet (new)" in v["soft"] and "notes/tmp.txt (deleted)" in v["soft"]
    after.pop("figures/f.png")
    v = ig.manifest_violations(before, after, started, protected={"figures/f.png"})
    assert "figures/f.png (deleted)" in v["hard"]


def test_workspace_manifest_skips_paper_and_hidden(tmp_path):
    for rel in ("paper/paper.tex", ".scratch/c.py", "results/r.csv", "src/__pycache__/x.pyc"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("x")
    assert set(ig.workspace_manifest(tmp_path)) == {"results/r.csv"}


# ── Gates against a project ────────────────────────────────────────────────


def _touch(path, text="x", mtime=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text) if isinstance(text, str) else path.write_bytes(text)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


@pytest.fixture
def project(tmp_path):
    started = datetime.now(timezone.utc) - timedelta(minutes=10)
    mp = {"tasks": [{"id": "T1", "outputs": [{"path": "figures/main.png"}, {"path": "results/"}]},
                    {"id": "T2", "outputs": [{"path": "figures/other.png"}]}]}
    with Session(engine) as s:
        p = Project(title="_integrity")
        s.add(p)
        s.commit()
        s.refresh(p)
        bp = Run(project_id=p.id, kind="blueprint", status="done", result={"master_plan": mp})
        ex = Run(project_id=p.id, kind="execute", status="done", started_at=started - timedelta(hours=1),
                 finished_at=started - timedelta(minutes=5))
        rep = Run(project_id=p.id, kind="report", status="done", started_at=started, finished_at=started,
                  result={"integrity": {"hard": [], "soft": []}})
        s.add_all([bp, ex, rep])
        s.commit()
        s.refresh(bp)
        p.blueprint = {"run_id": bp.id}
        s.add(p)
        s.add(TaskState(project_id=p.id, blueprint_run_id=bp.id, task_id="T1", agent="A1", status="done"))
        s.add(TaskState(project_id=p.id, blueprint_run_id=bp.id, task_id="T2", agent="A1", status="failed"))
        s.commit()
        ids = (p.id, bp.id, ex.id, rep.id)
    tex = ("\\begin{document}\nSee \\citep{a1}. \\ref{fig:none}\n"
           "\\begin{figure}\\includegraphics{../figures/main.png}\\caption{c}\\label{fig:m}\\end{figure}\n"
           "\\end{document}\n")
    now = time.time()
    _touch(tmp_path / "paper" / "paper.tex", tex, now - 60)
    _touch(tmp_path / "paper" / "paper.pdf", b"%PDF", now - 30)
    _touch(tmp_path / "paper" / "references.bib", "@article{a1,\n title={x}\n}\n")
    _touch(tmp_path / "figures" / "main.png", b"png", now - 3600)
    _touch(tmp_path / "scripts" / "plot.py", "plt.savefig('figures/main.png')\n", now - 7200)
    yield ids, tmp_path
    with Session(engine) as s:
        for model in (TaskState, Run):
            for row in s.exec(select(model).where(model.project_id == ids[0])):
                s.delete(row)
        s.delete(s.get(Project, ids[0]))
        s.commit()


def test_clean_manuscript_passes_with_facts(project):
    (pid, *_), root = project
    out = ig.check(pid, root)
    assert out["passed"], out["hard_failures"]
    facts = " ".join(out["facts"])
    assert "T2 [failed]" in facts and "fig:none" in facts
    assert out["figure_code"] == {"figures/main.png": ["scripts/plot.py"]}


def test_gates_h1_to_h5(project):
    (pid, bp, ex, rep), root = project
    now = time.time()
    # H1: PDF older than its source (beyond the clock tolerance); H2 unknown key; H3 missing figure.
    tex = (root / "paper" / "paper.tex").read_text().replace("\\citep{a1}", "\\citep{a1,zz9}")
    tex = tex.replace("main.png}", "main.png}\\includegraphics{../figures/gone}")
    _touch(root / "paper" / "paper.tex", tex, now)
    os.utime(root / "paper" / "paper.pdf", (now - 600, now - 600))
    with Session(engine) as s:
        r = s.get(Run, rep)
        r.result = {"integrity": {"hard": ["results/a.csv"], "soft": []}}  # H4
        s.add(r)
        e = s.get(Run, ex)
        e.finished_at = datetime.now(timezone.utc)  # H5: execution finished after the report started
        s.add(e)
        s.commit()
    gates = {g["gate"] for g in ig.check(pid, root)["hard_failures"]}
    assert gates == {"H1", "H2", "H3", "H4", "H5"}


def test_pdf_within_clock_tolerance_is_fine(project):
    (pid, *_), root = project
    now = time.time()
    os.utime(root / "paper" / "paper.tex", (now, now))
    os.utime(root / "paper" / "paper.pdf", (now - 60, now - 60))  # sandbox clock 60 s behind
    assert ig.check(pid, root)["passed"]


def test_stale_and_unprovenanced_figures_are_facts(project):
    (pid, *_), root = project
    now = time.time()
    os.utime(root / "scripts" / "plot.py", (now, now))  # code changed after the figure was made
    _touch(root / "figures" / "orphan.png", b"png", now)
    tex = (root / "paper" / "paper.tex").read_text().replace(
        "\\end{document}", "\\includegraphics{../figures/orphan.png}\n\\end{document}")
    _touch(root / "paper" / "paper.tex", tex, now - 60)
    facts = " ".join(ig.check(pid, root)["facts"])
    assert "figures/main.png is older than code" in facts
    assert "figures/orphan.png is neither a declared output" in facts


def test_missing_manuscript_is_fatal(project):
    (pid, *_), root = project
    (root / "paper" / "paper.tex").unlink()
    out = ig.check(pid, root)
    assert not out["passed"] and out["hard_failures"][0]["title"] == "Manuscript missing"
