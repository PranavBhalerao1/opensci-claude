"""Pre-execution feasibility of blueprints, offline.

Regression for project d95fb65c9f7a (Fashion-MNIST augmentation, 2026-10-09): its approved
MasterPlan was structurally valid, yet setup task T1.1 (CPU-only, no GPU tool) had to report a
real GPU device name, which only the later Colab GPU task T2.1 could observe. T1.1 failed twice
(the second time with a placeholder name) and all 14 other tasks were blocked. The fixture is a
byte-for-byte copy of that run's plan_exports/master_plan.json; the run's own artifacts under
research/ are not read or touched.

The checks below are generic (hardware evidence, artifacts from tasks not upstream, repairs that
drop requirements); nothing here is specific to that project. A few non-ML blueprints show it.
"""

import asyncio
import copy
import json
from collections import defaultdict
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app import jobs, pipeline
from app.agents import blueprint
from app.agents.blueprint import (REPAIR_INSTRUCTIONS, Contradiction, FeasibilityReview, MasterPlan, Resolution,
                                  ResolvedDataset, lost_requirements, review_feasibility, validate)
from app.beta import BetaLimitReached
from app.db import Project, Run, engine
from app.execution import colab_runner, orchestrator
from app.execution.e2b_sandbox import E2BSandbox
from app.execution.orchestrator import CheckResult, Verdict
from study_fixture import isolate

FIXTURE = Path(__file__).parent / "fixtures" / "fmnist_d95fb65c9f7a_master_plan.json"
# The run's runtime: the E2B sandbox with Google Colab configured (so "cuda_gpu" is a capability,
# reachable only through run_gpu_jobs).
CAPS = set(E2BSandbox.BASE_CAPABILITIES) | {"cuda_gpu"}
BUDGET = {"llm_usd": 15.0, "gpu_hours": 5.0}
GPU_CHECK = ("logs/gpu/fashion_mnist_train.log records torch.cuda.is_available() == True and the actual CUDA "
             "device name reported by torch.cuda.get_device_name(0); a placeholder name fails.")


def fmnist() -> dict:
    """The approved MasterPlan of d95fb65c9f7a as it ran (export-only keys dropped)."""
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return {k: v for k, v in doc.items() if k in MasterPlan.model_fields}


def task(mp: dict, tid: str) -> dict:
    return next(t for t in mp["tasks"] if t["id"] == tid)


def repaired(mp: dict) -> dict:
    """The fix a sound repair makes: T1.1 sets up and records its (CPU) environment honestly; the GPU
    evidence moves to T2.1, the task that trains on Colab, with an output that carries it."""
    mp = copy.deepcopy(mp)
    t1, t2 = task(mp, "T1.1"), task(mp, "T2.1")
    t1["objective"] = ("Install all required packages, create workspace directories, and write "
                       "data/environment_report.txt describing this CPU setup environment.")
    t1["steps"][1] = ("Run python to log the PyTorch version, the CUDA version torch was built with, "
                      "torch.cuda.is_available() (expected False in this CPU-only sandbox) and the Python version.")
    t1["outputs"][0]["description"] = "PyTorch, CUDA build and Python versions; CUDA availability as found"
    t1["acceptance_checks"][0] = ("data/environment_report.txt exists and records the PyTorch version, the CUDA build "
                                  "version and whether CUDA is available.")
    t2["outputs"].append({"path": "logs/gpu/fashion_mnist_train.log", "format": "text",
                          "description": "GPU job log, including the CUDA device name of the Colab GPU"})
    t2["acceptance_checks"].append(GPU_CHECK)
    return mp


def errors_of(mp: dict, caps: set[str] = CAPS) -> list[str]:
    return validate(MasterPlan.model_validate(mp), caps, BUDGET)[0]


# ── Deterministic feasibility ──────────────────────────────────────────────


def test_failed_run_blueprint_was_structurally_valid_but_infeasible(monkeypatch):
    mp = fmnist()
    monkeypatch.setattr(blueprint, "feasibility_errors", lambda mp, caps: [])
    assert validate(MasterPlan.model_validate(mp), CAPS, BUDGET) == ([], [])  # what the old validator saw
    monkeypatch.undo()
    errors = errors_of(mp)
    assert len(errors) == 2 and all(e.startswith("T1.1 runs without a CUDA GPU") for e in errors)
    assert "a GPU device name string" in errors[0]  # the acceptance check
    assert "confirming GPU runtime is ready" in errors[1]  # the output description behind it
    assert all("(T2.1)" in e and "never drop the requirement" in e for e in errors)


def test_gpu_evidence_is_required_at_the_gpu_training_step():
    mp = repaired(fmnist())
    assert errors_of(mp) == []
    plan = MasterPlan.model_validate(mp)
    tasks = {t.id: t for t in plan.tasks}
    assert blueprint._evidence(tasks["T2.1"], "cuda_gpu") and not blueprint._evidence(tasks["T1.1"], "cuda_gpu")
    assert blueprint._reach(tasks["T2.1"], CAPS) == {"cuda_gpu"} and blueprint._reach(tasks["T1.1"], CAPS) == set()


def test_cpu_tasks_downstream_of_the_gpu_step_may_report_its_evidence():
    mp = repaired(fmnist())
    task(mp, "T3.1")["acceptance_checks"].append(
        "analysis/validation_summary.txt quotes the CUDA device name recorded in logs/gpu/fashion_mnist_train.log.")
    assert errors_of(mp) == []


def test_gpu_access_comes_from_the_tool_or_the_compute_kind_not_from_the_runtime():
    mp = repaired(fmnist())
    t2 = task(mp, "T2.1")
    t2["tools"].remove("run_gpu_jobs")  # still cuda_gpu compute: the orchestrator grants run_gpu_jobs
    assert errors_of(mp) == []
    t2["compute"]["kind"] = "cpu"  # now nothing in this task reaches a GPU, though the runtime has one
    errors = errors_of(mp)
    assert errors and all(e.startswith("T2.1 runs without a CUDA GPU") for e in errors)
    assert any("No task in this blueprint runs on a CUDA GPU" in e for e in errors)


def test_without_a_gpu_runner_a_gpu_task_is_still_consistent_and_only_warned_about():
    mp = repaired(fmnist())
    errors, warnings = validate(MasterPlan.model_validate(mp), set(E2BSandbox.BASE_CAPABILITIES), BUDGET)
    assert errors == []  # configuring Colab before execution stays possible
    assert any("T2.1 needs a CUDA GPU" in w or "T2.1 needs tools unavailable" in w for w in warnings)


def test_checks_on_artifacts_of_later_or_parallel_tasks_are_rejected():
    mp = repaired(fmnist())
    task(mp, "T1.1")["acceptance_checks"].append("data/checkpoints/model_seed42_noaug.pt exists.")  # T2.1 makes it
    task(mp, "T1.2")["acceptance_checks"].append("src/model.py defines SmallCNN.")  # T1.3 runs in parallel
    task(mp, "T1.3")["acceptance_checks"].append("data/fashion_mnist/FashionMNIST/raw is present.")  # in T1.2's dir
    errors = errors_of(mp)
    assert len(errors) == 3
    assert any(e.startswith("T1.1 has an acceptance check on data/checkpoints/model_seed42_noaug.pt, which only "
                            "T2.1 produce(s)") for e in errors)
    assert any(e.startswith("T1.2 has an acceptance check on src/model.py, which only T1.3") for e in errors)
    assert any(e.startswith("T1.3 has an acceptance check on data/fashion_mnist/FashionMNIST/raw, which only T1.2")
               for e in errors)


def test_checks_on_upstream_or_own_artifacts_are_fine():
    mp = repaired(fmnist())
    task(mp, "T3.1")["acceptance_checks"].append("data/checkpoints/model_seed42_noaug.pt loads.")  # T2.1 is upstream
    task(mp, "T1.4")["acceptance_checks"].append("src/train.py imports run_training; data/checkpoints/ is used.")
    assert errors_of(mp) == []


@pytest.mark.parametrize("check", [
    "data/environment_report.txt records whether CUDA is available (True or False).",
    "The report gives the GPU device name, or 'none' when no GPU is present.",
    "The setup code falls back to CPU when no GPU is available.",
    "data/environment_report.txt contains 'cuda' (case-insensitive).",
    "The CUDA build version of torch is recorded.",
])
def test_conditional_or_neutral_gpu_mentions_are_not_contradictions(check):
    mp = repaired(fmnist())
    task(mp, "T1.1")["acceptance_checks"].append(check)
    assert errors_of(mp) == []


def _study(tasks: list[dict], tools: list[str]) -> dict:
    return {
        "title": "t", "summary": "s", "python_packages": [], "system_requirements": [],
        "agents": [{"id": "A1", "name": "Scientist", "model_tier": "standard", "tools": tools, "instructions": "i"}],
        "datasets": [], "tasks": tasks, "checkpoints": [], "llm_usd_estimate": 1.0, "compute_hours_estimate": 1.0,
        "execution_notes": [],
    }


def _task(tid: str, deps: list[str], outputs: list[str], checks: list[str], kind: str = "cpu",
          tools: tuple[str, ...] = ("run_python", "run_shell")) -> dict:
    return {"id": tid, "title": tid, "agent": "A1", "objective": "o", "steps": ["s"],
            "inputs": [], "outputs": [{"path": p, "format": "file", "description": "d"} for p in outputs],
            "acceptance_checks": checks, "depends_on": deps, "tools": list(tools), "resources": [],
            "compute": {"kind": kind, "est_minutes": 5, "timeout_minutes": 15}, "max_cost_usd": 0.5,
            "retries": 1, "human_required": False}


def test_contradictions_are_found_outside_machine_learning():
    # Molecular dynamics: the CPU system-preparation step must show the production run used the GPU.
    md = _study([
        _task("T1", [], ["md/system.gro"], ["md/prep.log shows GROMACS ran on the GPU (nvidia-smi output recorded)."]),
        _task("T2", ["T1"], ["md/prod.xtc", "logs/gpu/prod.log"], ["md/prod.xtc covers 100 ns."], kind="cuda_gpu",
              tools=("run_python", "run_shell", "run_gpu_jobs")),
    ], ["run_python", "run_shell", "run_gpu_jobs"])
    errors = errors_of(md)
    assert len(errors) == 1 and errors[0].startswith("T1 runs without a CUDA GPU") and "(T2)" in errors[0]
    # A survey study: data cleaning is checked against a figure the analysis step draws later.
    survey = _study([
        _task("T1", [], ["data/clean/responses.csv"], ["report/figures/regression.png exists."]),
        _task("T2", ["T1"], ["report/figures/regression.png"], ["report/figures/regression.png is a PNG."]),
    ], ["run_python", "run_shell"])
    errors = errors_of(survey)
    assert len(errors) == 1 and errors[0].startswith(
        "T1 has an acceptance check on report/figures/regression.png, which only T2 produce(s)")
    # Apple GPU evidence when no task (and no tool) provides one.
    mps = _study([_task("T1", [], ["bench/mps.json"], ["torch.backends.mps.is_available() returns True."])],
                 ["run_python", "run_shell"])
    errors = errors_of(mps)
    assert len(errors) == 1 and errors[0].startswith("T1 runs without an Apple GPU")
    assert "No task in this blueprint runs on an Apple GPU" in errors[0]


# ── Repairs may move requirements, never drop them ─────────────────────────


def test_moving_the_gpu_requirement_to_the_gpu_task_preserves_everything():
    before, after = MasterPlan.model_validate(fmnist()), MasterPlan.model_validate(repaired(fmnist()))
    assert lost_requirements(before, after) == []
    assert [(t.id, t.depends_on) for t in after.tasks] == [(t.id, t.depends_on) for t in before.tasks]
    assert sum(len(t.acceptance_checks) for t in after.tasks) == sum(len(t.acceptance_checks) for t in before.tasks) + 1


def test_a_repair_that_deletes_the_gpu_check_is_rejected():
    weakened = fmnist()
    t1 = task(weakened, "T1.1")
    t1["acceptance_checks"].pop(0)
    t1["outputs"][0]["description"] = "PyTorch and CUDA versions"
    errors = lost_requirements(MasterPlan.model_validate(fmnist()), MasterPlan.model_validate(weakened))
    assert any("deleted acceptance checks (32 before, 31 after)" in e and "a GPU device name string" in e
               for e in errors)
    assert any("dropped every requirement for CUDA GPU evidence" in e for e in errors)


def test_a_repair_that_rewords_the_gpu_requirement_away_is_rejected():
    weakened = fmnist()
    t1 = task(weakened, "T1.1")
    t1["acceptance_checks"][0] = "data/environment_report.txt exists and contains 'cuda' (case-insensitive)."
    t1["outputs"][0]["description"] = "PyTorch and CUDA versions"
    assert lost_requirements(MasterPlan.model_validate(fmnist()), MasterPlan.model_validate(weakened)) == [
        "The repair dropped every requirement for CUDA GPU evidence; require it of the task that runs on the CUDA "
        "GPU instead"]


def test_a_repair_that_removes_a_task_is_rejected():
    fewer = fmnist()
    fewer["tasks"] = [t for t in fewer["tasks"] if t["id"] != "T5.3"]
    errors = lost_requirements(MasterPlan.model_validate(fmnist()), MasterPlan.model_validate(fewer))
    assert any(e.startswith("The repair removed tasks T5.3") for e in errors)


# ── Feasibility review (model) ─────────────────────────────────────────────


class Scripted:
    """Stands in for blueprint.parse: one queue per schema; records every call."""

    def __init__(self):
        self.queues: dict[str, list] = defaultdict(list)
        self.calls: list[dict] = []

    def add(self, schema, *items) -> "Scripted":
        self.queues[schema.__name__].extend(items)
        return self

    async def parse(self, *, schema, **kw):
        self.calls.append({"schema": schema.__name__, **kw})
        if not self.queues[schema.__name__]:
            raise AssertionError(f"unexpected {schema.__name__} call")
        item = self.queues[schema.__name__].pop(0)
        if isinstance(item, BaseException):
            raise item
        return item if isinstance(item, schema) else schema.model_validate(item)

    def kinds(self) -> list[str]:
        return [c["schema"] for c in self.calls]


@pytest.fixture
def scripted(monkeypatch):
    s = Scripted()
    monkeypatch.setattr(blueprint, "parse", s.parse)
    return s


STEP = "Run python asserting torch.cuda.is_available()==True; if False raise RuntimeError immediately"


def test_review_findings_count_only_when_quoted_from_the_task(scripted):
    scripted.add(FeasibilityReview, FeasibilityReview(contradictions=[
        Contradiction(task_id="T1.1", requirement=STEP, reason="T1.1 runs in a CPU-only sandbox.",
                      satisfiable_in="T2.1"),
        Contradiction(task_id="T1.2", requirement="The GPU is verified before download", reason="paraphrase",
                      satisfiable_in=None),  # not in T1.2: ignored
        Contradiction(task_id="T9.9", requirement=STEP, reason="unknown task", satisfiable_in=None),
    ]))
    errors, warnings = asyncio.run(review_feasibility(MasterPlan.model_validate(fmnist()), CAPS))
    assert warnings == [] and len(errors) == 1
    assert errors[0].startswith(f'T1.1: "{STEP}" cannot be satisfied') and "It belongs in T2.1" in errors[0]
    call = scripted.calls[0]
    assert call["reasoning_effort"] == "medium" and "BLUEPRINT:" in call["messages"][0]["content"]
    assert "a CUDA GPU only through run_gpu_jobs" in call["messages"][0]["content"]


def test_a_failed_review_is_a_warning_and_credit_errors_propagate(scripted):
    plan = MasterPlan.model_validate(repaired(fmnist()))
    scripted.add(FeasibilityReview, RuntimeError("Model returned invalid structured output: x"))
    errors, warnings = asyncio.run(review_feasibility(plan, CAPS))
    assert errors == [] and warnings[0].startswith("Feasibility review unavailable")
    scripted.add(FeasibilityReview, BetaLimitReached())
    with pytest.raises(BetaLimitReached):
        asyncio.run(review_feasibility(plan, CAPS))


# ── The blueprint stage end to end (model calls scripted) ──────────────────


class Handle:
    def __init__(self):
        self.log: list[tuple[str, str | None]] = []

    def phase(self, phase: str, text: str | None = None) -> None:
        self.log.append((phase, text))

    def note(self, text: str) -> None:
        self.log.append(("note", text))

    def counts(self, **counts: int) -> None:
        pass


@pytest.fixture
def stage(tmp_path, monkeypatch, scripted):
    isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(colab_runner, "configured", lambda: True)  # as in the run: Colab is the GPU runner
    plan = {"research_question": "Does simple data augmentation improve CNN test accuracy on Fashion-MNIST?",
            "datasets": [{"name": "Fashion-MNIST"}], "run_id": "plan-run"}
    with Session(engine) as s:
        p = Project(title="feasibility", plan=plan, stage="blueprint")
        s.add(p)
        s.commit()
        s.refresh(p)
    scripted.add(Resolution, Resolution(datasets=[ResolvedDataset(
        name="Fashion-MNIST", url="https://github.com/zalandoresearch/fashion-mnist", access_method="torchvision",
        format="idx", size_estimate="30 MB", license="MIT", notes="")]))
    return p.id


def _run(project_id: str) -> tuple[dict, Handle]:
    h = Handle()
    return asyncio.run(blueprint.run(project_id, h)), h


def test_the_failed_run_blueprint_is_repaired_before_execution(stage, scripted):
    scripted.add(MasterPlan, fmnist(), repaired(fmnist())).add(FeasibilityReview, {"contradictions": []})
    result, h = _run(stage)
    assert scripted.kinds() == ["Resolution", "MasterPlan", "MasterPlan", "FeasibilityReview"]
    compile_, repair = scripted.calls[1], scripted.calls[2]
    # The whole blueprint (thinking + JSON) gets Sonnet 4.6's Bedrock output maximum, at high effort.
    assert compile_["reasoning_effort"] == "high" and compile_["max_tokens"] == 64_000
    assert "a CUDA GPU only through run_gpu_jobs" in compile_["messages"][0]["content"]
    assert repair["instructions"] == REPAIR_INSTRUCTIONS and repair["max_tokens"] == 64_000
    assert "T1.1 runs without a CUDA GPU" in repair["messages"][0]["content"]
    mp = MasterPlan.model_validate(result["master_plan"])
    assert validate(mp, CAPS, BUDGET)[0] == []
    assert GPU_CHECK in task(result["master_plan"], "T2.1")["acceptance_checks"]
    assert ("repairing", "Fixing 2 problems") in h.log and ("note", "Blueprint repaired in 1 round(s)") in h.log


def test_a_repair_that_drops_the_requirement_is_sent_back(stage, scripted):
    weakened = fmnist()
    task(weakened, "T1.1")["acceptance_checks"].pop(0)
    task(weakened, "T1.1")["outputs"][0]["description"] = "PyTorch and CUDA versions"
    scripted.add(MasterPlan, fmnist(), weakened, repaired(fmnist())).add(FeasibilityReview, {"contradictions": []})
    result, _ = _run(stage)
    second = scripted.calls[3]["messages"][0]["content"]
    assert "deleted acceptance checks" in second and "dropped every requirement for CUDA GPU evidence" in second
    assert GPU_CHECK in task(result["master_plan"], "T2.1")["acceptance_checks"]


def test_a_contradiction_only_the_review_sees_is_repaired(stage, scripted):
    subtle = repaired(fmnist())
    impossible = "data/dataset_stats.json reports the final test accuracy of the augmented model."
    task(subtle, "T1.2")["acceptance_checks"].append(impossible)  # results that only T3.1 computes, no path named
    fixed = copy.deepcopy(subtle)
    task(fixed, "T1.2")["acceptance_checks"].remove(impossible)
    task(fixed, "T3.1")["acceptance_checks"].append("analysis/overall_accuracy.csv reports the final test accuracy "
                                                    "of the augmented model.")
    finding = Contradiction(task_id="T1.2", requirement=impossible, reason="Training happens later, in T2.1.",
                            satisfiable_in="T3.1")
    scripted.add(MasterPlan, subtle, fixed)
    scripted.add(FeasibilityReview, FeasibilityReview(contradictions=[finding]), {"contradictions": []})
    result, _ = _run(stage)
    assert scripted.kinds() == ["Resolution", "MasterPlan", "FeasibilityReview", "MasterPlan", "FeasibilityReview"]
    assert impossible in scripted.calls[3]["messages"][0]["content"]
    assert impossible not in task(result["master_plan"], "T1.2")["acceptance_checks"]


def test_a_blueprint_that_cannot_be_repaired_fails_with_an_explanation(stage, scripted):
    scripted.add(MasterPlan, fmnist(), fmnist(), fmnist())  # the repair never fixes it
    with pytest.raises(RuntimeError) as exc:
        _run(stage)
    msg = str(exc.value)
    assert msg.startswith("Blueprint still invalid after 2 repair rounds, so it was not approved and no task ran")
    assert "T1.1 runs without a CUDA GPU" in msg
    assert scripted.kinds() == ["Resolution", "MasterPlan", "MasterPlan", "MasterPlan"]  # bounded


@pytest.mark.parametrize("repairable", [True, False])
def test_invalid_blueprints_never_enter_execution(stage, scripted, monkeypatch, repairable):
    with Session(engine) as s:
        p = s.get(Project, stage)
        p.autonomous = True
        s.add(p)
        s.commit()
    started = []
    monkeypatch.setattr(pipeline, "start_execution", lambda pid: started.append(pid))
    scripted.add(MasterPlan, fmnist(), *([repaired(fmnist())] if repairable else [fmnist(), fmnist()]))
    scripted.add(FeasibilityReview, {"contradictions": []})

    async def go():
        pipeline.start_blueprint(stage)
        await jobs._tasks[f"{stage}:blueprint"]

    asyncio.run(go())
    with Session(engine) as s:
        run = s.exec(select(Run).where(Run.project_id == stage, Run.kind == "blueprint")).one()
        project = s.get(Project, stage)
    if repairable:
        assert run.status == "done" and project.blueprint and project.stage == "ready" and started == [stage]
    else:
        assert run.status == "error" and "not approved and no task ran" in run.error
        assert project.blueprint is None and project.stage == "blueprint" and started == []


# ── Verifier evidence for workspace paths that are not declared outputs ────


def test_verifier_gets_platform_facts_for_paths_the_checks_name(tmp_path, monkeypatch):
    """T1.1's second check named nine directories, none of them an output, so the verifier saw no
    evidence at all and failed it: 'No platform-generated FACTS (e.g., directory listings)'."""
    sb = E2BSandbox("_facts")
    sb.root = tmp_path
    for rel in ("src/model.py", "src/train.py", "data/environment_report.txt", "data/checkpoints/smoke.pt",
                "data/logs/smoke.csv", "data/predictions/.keep", "results/note.md", "scripts/probe.py"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("x")
    (tmp_path / "analysis").mkdir()
    (tmp_path / "figures").mkdir()
    t11 = copy.deepcopy(task(fmnist(), "T1.1"))
    t11["acceptance_checks"].append("No confusion between T-shirt/top and Shirt classes in the train/test split.")
    named = orchestrator._named_paths(sb, t11)
    assert named == ["src", "data/checkpoints", "data/logs", "data/predictions", "analysis", "figures", "tables",
                     "results", "scripts"]  # not the declared output, not "T-shirt/top" or "train/test"
    facts = orchestrator._path_facts(sb, named)
    assert "- src/: directory, 2 file(s) inside; entries: model.py, train.py" in facts
    assert "- analysis/: directory, 0 file(s) inside (empty)" in facts
    assert "- tables: does not exist in the workspace" in facts
    seen = []

    async def fake_parse(**kw):
        seen.append(kw["messages"][0]["content"])
        return Verdict(results=[CheckResult(check=c, passed=True, reason="r") for c in t11["acceptance_checks"]])

    monkeypatch.setattr(orchestrator, "parse", fake_parse)
    asyncio.run(orchestrator._verify(t11, sb, "default"))
    assert "FACTS: other workspace paths named in the acceptance checks" in seen[0]
    assert "- figures/: directory, 0 file(s) inside (empty)" in seen[0]


def test_patterns_in_checks_list_their_fixed_directory(tmp_path):
    sb = E2BSandbox("_facts")
    sb.root = tmp_path
    t = {"outputs": [{"path": "analysis/merged.csv"}],
         "acceptance_checks": ["Load data/logs/train_seed{42,123}_{noaug,aug}.csv and data/raw/*.idx, then "
                               "src/model.py, analysis/merged.csv."]}
    assert orchestrator._named_paths(sb, t) == ["data/logs", "data/raw", "src/model.py"]


def test_empty_directories_created_in_the_sandbox_reach_the_host(tmp_path):
    """The agent's `mkdir -p ... analysis figures tables ...` ran in E2B, but the file-only sync never
    created analysis/, figures/ or tables/ in the host copy that checks and the verifier read."""
    from app.execution import e2b_sandbox
    from app.execution.sandbox import ExecResult

    sb = E2BSandbox("_sync")
    sb.root = tmp_path
    listing = ("./data/x.csv\t3\t1.0\nDIR\t./analysis\nDIR\t./figures/sub\nDIR\t./.venv/lib\nDIR\t./tables\n")
    seen = []

    async def sh(cmd, timeout, cwd=None, envs=None, clip=True):
        seen.append(cmd)
        return ExecResult(0, listing, "")

    sb._sh = sh
    sb._remote_seen = {"data/x.csv": (3, "1.0")}  # unchanged: nothing to download
    asyncio.run(sb._pull())
    assert "-type d -empty" in seen[0] and seen[0] == e2b_sandbox._FIND_ALL
    assert all((tmp_path / d).is_dir() for d in ("analysis", "figures/sub", "tables"))
    assert not (tmp_path / ".venv").exists()  # environments are never synced
    assert e2b_sandbox._parse_listing(listing) == {"data/x.csv": (3, "1.0")}  # file sync unchanged
