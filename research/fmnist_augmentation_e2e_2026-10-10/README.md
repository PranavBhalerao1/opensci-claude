# OpenScientist end-to-end run: Fashion-MNIST data augmentation (2026-10-10)

**Project ID:** `a2794d1959b5` · owner `56ec46c1-…` (pranavrbhalerao@gmail.com) · autonomous mode
**Final status: FAILED at execution: no paper, no scientific review.** Literature, gaps, plan, blueprint and
13 of 14 execution tasks completed. All neural-network training ran on CUDA on a Google Colab **NVIDIA L4**. Task
**T4.1** (figure 1, test-accuracy curves) failed verification on all 3 attempts. The figure exists and is correct
in substance. The verifier rejected it because the agent's line count had no platform-run test behind it. Autonomous
projects write the report only when every task is done or skipped (`backend/app/pipeline.py:128-144`). So the
Report stage (LaTeX/PDF) and the independent scientific review never started.

This is a fresh run of the research question that `../fmnist_augmentation_run_2026-10-09/` and
`../fmnist_augmentation_rerun_2026-10-09/` also studied. Nothing from those projects was fed in.
The only shared state is OpenScientist's own global literature cache; see Observations.

## Validation before launch (`preflight/`)

| Check | Result |
|---|---|
| `preflight.py` (read-only) | Supabase Postgres 17.6; 11 model tables, 0 missing columns; no run marked running in any project; beta approved, $50 cap, $29.69 left; E2B key valid, 0 sandboxes; every model tier = `us.anthropic.claude-sonnet-4-6`; refinement on (3 rounds, $12) |
| `python -m app.execution.colab_runner check` | `Colab OK: 297.92 compute units left, usage 0.00/h, 0 active session(s)` |
| Bedrock live call (`tests/test_bedrock_integration.py::test_live_text_request`, temp DB) | PASSED, $0.0001 |
| `colab_gpu_probe.py`: 1 job through the real `run_gpu_jobs` handler (throwaway SQLite DB and workspace, LLM blocked, E2B off) | **Tesla T4**, torch 2.11.0+cu130, `cuda_available True`, matmul on `cuda:0`; session terminated, ledger empty; $0.0007 (recorded only in the throwaway DB); 0 credential-token patterns in the output |

Code that ran: **HEAD `551300c`** ("changed to always high sonnet 4.6") with a clean tree (`launch/source_state.txt`).
It was unchanged throughout: checked before launch, before the session-2 restart and at the end.

## Outcome by stage

| Stage | Result | Time (UTC) | LLM cost |
|---|---|---|---|
| Clarify (brief, auto-confirmed) | done | 03:47:30–03:47:53 | $0.03 |
| Literature review | done: 381 found, 300 screened, **48 included** (33 read, 15 already in the knowledge base) | 03:47:53–03:59:19 (11.4 m) | $0.70 |
| Gap finding | done: 6 gaps; **g1** auto-chosen | 03:59:19–04:08:14 (8.9 m) | $0.44 |
| Research plan | done, auto-approved | 04:08:14–04:12:53 (4.6 m) | $0.38 |
| Blueprint | done, auto-approved; no repair round; 0 warnings; 4 agents, 14 tasks | 04:12:54–04:20:27 (7.6 m) | $0.76 |
| Execution, session 1 | **13/14 done; T4.1 failed** | 04:20:28–07:53:04 (212.6 m) | $8.92 |
| (pipeline stopped; waited for the user's decision) | | 07:53–09:17 | |
| Execution, session 2 (one user-authorized resume) | T4.1 attempt 3 **failed** again; 13/14 | 09:18:11–09:21:23 (3.2 m) | $0.19 |
| Report (LaTeX + PDF) | **not started** (gated on every task done/skipped) | | |
| Scientific review and refinement | **not started** | | |

- **Wall time:** 5 h 34 min (launch 03:47:18Z → last task 09:21:23Z). 1 h 25 min of that was waiting for the
  user's decision. **Active pipeline time: about 4 h 09 min.** Execution's 3.5 h was dominated by T2.1
  re-running its 44-min GPU job three times (see Failures).
- **Cost: $11.79 total.** LLM $11.43: 326 Bedrock calls (all Claude Sonnet 4.6); 5,025,846 input tokens, of which
  4,160,331 were cached; 404,396 output tokens; 2 web searches. The largest single output was 35,862 tokens.
  GPU $0.36: 8 `GpuUsage` rows, 141.5 L4-minutes including session overhead, ≈3.6 CU at $0.10/CU. The Colab
  balance went 297.92 → 294.45. E2B time is not metered by the app. The preflight cost $0.0008, recorded only in
  temporary DBs.
- Per-task LLM cost: T2.1 $4.40 (3 attempts) was 49% of execution; T1.2 $0.53; T4.4 $0.52; T3.3 $0.50; T4.2 $0.46;
  T4.1 $0.39; the other tasks $0.08–0.37 each.

## Colab GPU training: real, CUDA, traceable

1. **OpenScientist's Colab infrastructure was invoked.** The `run_gpu_jobs` tool was called 4 times: T1.3 once, and
   T2.1 once per attempt (`db_export/task_traces/T1.3_done.json`, `T2.1_done.json`). The runner opened 4 Colab
   sessions owned by the project (ledger `os-a2794d1959b5-*`). `db_export/gpu_usage.json` has 8 rows, all `gpu=L4`:
   `cuda_validate` 25 s; `train_all_runs` 2,560 s, 2,617 s and 2,653 s; plus 4 session-overhead rows.
2. **PyTorch detected a CUDA GPU.** `workspace_copy/logs/gpu/_environment.txt` holds `nvidia-smi` from the
   Colab VM: **NVIDIA L4**, driver 580.82.07, CUDA 13.0, Python 3.13.15.
   `logs/gpu/cuda_validate.log` and `data/gpu_and_data_validation.txt` (T1.3) show `CUDA available: True`,
   `GPU: NVIDIA L4`, torch 2.11.0+cu130, torchvision 0.26.0+cu130, and a forward pass on CUDA.
3. **Training ran on the CUDA device.** `logs/gpu/train_all_runs.log` begins `PyTorch: 2.11.0+cu130 / CUDA available:
   True / GPU: NVIDIA L4`, and each of the 4 runs logs `device=cuda`. Each metrics CSV header records `device=cuda`.
   `logs/gpu/train_all_runs.log.time` (OS start/end 1791615030 → 1791617683 = 2,653 s) matches the last GPU row.
4. **The metrics come from those GPU runs.** `data/metrics_seed{42,123}_{noaug,aug}.csv` (30 epochs each) were
   written by that job and synced back. `analysis/combined_metrics.csv` (120 rows) and every later table and figure
   derive from them. The three GPU runs were **bit-for-bit deterministic**: attempt 2's and the final CSVs'
   data rows are identical, and attempt 1's per-epoch train_loss matches on all 120 epochs (`integrity/postrun_checks.txt`).

The E2B CPU sandbox (`openscientist-cpu`) ran the non-GPU work: spec, script, smoke test, aggregation, statistics,
figures and tables.

## Result (OpenScientist's, not checked further here)

Design (from gap g1): a small CNN (2 conv blocks 32→64, FC 3136→256→10, dropout 0.25, no BatchNorm, 824,458
params); Adam, lr 1e-3, wd 1e-4, batch 64. The validation split is a seeded `random_split` of the training set.
Augmentation is RandomHorizontalFlip(0.5) + RandomCrop(28, pad 3) + RandomRotation(±10°). Seeds 42 and 123,
**30 epochs**, with checkpoints at 5/10/20/30.

| Epoch | No-aug s42 | Aug s42 | No-aug s123 | Aug s123 | Mean gap (aug − no-aug) |
|---|---|---|---|---|---|
| 5 | 91.30 | 89.15 | 91.76 | 88.51 | **−2.70 pp** |
| 10 | 92.18 | 90.27 | 92.04 | 90.10 | −1.93 pp |
| 20 | 92.35 | 90.13 | 92.05 | 91.12 | −1.57 pp |
| 30 | 92.65 | 91.28 | 92.26 | 91.00 | −1.31 pp |

(test accuracy %, `workspace_copy/analysis/table1_checkpoint_summary.csv`)

At the requested ~5-epoch budget, augmentation **lowered** test accuracy for both seeds (−2.15 and −3.25 pp).
OpenScientist classified this as `underfitting-penalty-confirmed`. The gap narrowed with training but was negative
at every one of the 30 epochs, so there was "no crossover within 30 epochs". The gap's prediction that a benefit
would appear after 15–25 epochs was not borne out. `results/SUMMARY.md` (T4.4) states the results with two seeds and
no significance test. Because no paper was written, the claims audit and the scientific review never checked these
statements.

## Failures, retries and verification issues (preserved, not corrected)

| Task | Attempts | Outcome | What happened |
|---|---|---|---|
| T1.2 training script | 2 | done | Attempt 1: "Smoke test (5 epochs) produces a 5-row CSV and at least one checkpoint file: No platform-confirmed output file previews or test-run facts … only the agent's own claim … cannot serve as sole proof." |
| **T2.1** 4 GPU runs × 30 epochs | **3** | done | Attempt 1 (GPU 2,560 s) failed 2 of 5 checks. (a) "each has exactly 30 data rows: FACTS explicitly report 31 data rows". **That is a platform false positive.** Each CSV had a `# seed=… device=cuda …` comment line, then the header, then exactly 30 rows. The verifier's CSV facts treat line 1 as the header and do not skip comment lines (`backend/app/execution/orchestrator.py:258-264`). (b) "test_acc … in the range [50, 99]": the blueprint's own check expected percent, while the agent wrote fractions. Attempt 2 re-trained (2,617 s) with percent values and failed (a) again. Attempt 3 re-trained (2,653 s) and passed: the agent **merged the comment into the header line** (`# seed=42 … start=…,train_loss,train_acc,val_acc,test_acc`), so the `epoch` column is no longer named. That is a malformed header that satisfies the checker. Downstream tasks parsed it without failing. Cost: 2 extra 44-min GPU jobs and ~$3 of LLM. |
| T4.2 gap-trajectory figure | 2 | done | Attempt 1 failed a check. The reason is **not recoverable**: a task's `note`/`events` are overwritten by each attempt, so a later success erases the earlier failure (`db_export/task_traces/T4.2_done.json` holds only the last attempt). |
| **T4.1** test-accuracy figure | **3** (2 + 1 after the resume) | **failed** | Every attempt failed the same check, "Figure has four distinct lines (confirmed by checking matplotlib axes line count)": "the line count of 4 … is reported solely by the agent … with no independent platform-run test result". The PNG/PDF exist and do show 4 lines (`halt_snapshot_after_execution/workspace_copy/figures/` is the session-1 version; `workspace_copy/figures/` the final one). On attempt 3 the agent wrote `figures/fig1_verification.json` and `scripts/plot_fig1.py`. Neither was a declared output, so the verifier never saw them, and its summary calls its own check "platform-run". Separately, the figure's "no crossover" annotation box is hidden behind the legend; no check flagged this. |

There were no infrastructure failures: no Colab 503s, timeouts or lost runtimes, and every GPU job exited with code 0.

## Other observations (not corrected)

- **Brief:** the clarify agent added RandomHorizontalFlip and RandomCrop to the augmentation. The prompt suggested
  only small translations/rotations. The code matches the brief (flip + crop(pad 3) + rotation ±10°).
- **Scope:** the auto-chosen gap g1 extended training from the requested ~5 epochs to 30 epochs (the 4 runs × 30 epochs
  include the 5-epoch comparison as a checkpoint). The other candidates were g3 (augmentation ablation),
  g5 (minimum seeds), g6 (per-class), g2 (data-size threshold) and g4 (hyperparameter grid).
- **Test set evaluated every epoch:** `src/train.py:278` computes test accuracy after each epoch, and the analysis
  selects epochs from the test-accuracy trajectory. Validation correctly uses held-out training data.
- **Silent CPU fallback in code:** `src/train.py:236` uses `cuda if available else cpu`. On Colab CUDA was
  available and the logs prove `device=cuda`, but the script would not have refused CPU.
- The blueprint has verification tasks for 3 of the 4 runs (T2.2 seed42-aug, T2.3 seed123-noaug, T2.4 seed123-aug),
  but none for seed42-noaug. `data/run_checks/` has 3 files.
- **Literature:** Semantic Scholar failed (HTTP errors) for 9 of the 12 queries, and the stage fell back to OpenAlex
  as designed. 15 of the 48 included papers' notes came from OpenScientist's global paper cache. Those notes are
  extracted from published papers. Earlier projects' screening, gaps, plans or results are not shared.
- Long outputs streamed without truncation: the plan was 1 call with 21.8K output tokens, and the blueprint stage
  produced 38.4K output tokens over 4 calls (largest single call 35.9K).

## Operator actions (complete list)

1. **Preflight** (read-only plus the isolated probes above), and checksum snapshots of every pre-existing research
   folder, plan export and WSL workspace (`integrity/`).
2. **Launch:** the real FastAPI app (uvicorn, port 8000, Supabase Postgres) in WSL2, because the Colab CLI is
   Linux-only. `launch/launcher.py` is a byte-identical copy of the previous runs' launcher. It calls the real
   `create_project(autonomous=True)` and `post_turn(<launch/research_prompt.md>)` handlers. Only bearer-token
   verification is skipped; the beta checks are called explicitly. Env: `COLAB_CREDENTIALS_FILE`,
   `COLAB_MAX_SESSIONS=1` (docs/colab-gpu.md, step 4). The research prompt is the user's question and requirements;
   their GPU requirement is stated as a "Compute:" constraint, the system's normal way to pass constraints.
3. **Evidence copies during the run** (read-only; the workspace was not modified). Each T2.1 retry deletes or
   overwrites the previous attempt's outputs, so `t2.1_attempt1_snapshot/` (training log) and
   `t2.1_attempt2_snapshot/` (log + 4 CSVs) were copied before they were overwritten.
4. **One resume, chosen by the user** after the autonomous stop ("Resume once"). The idle backend was stopped
   (SIGINT; no runs or Colab sessions active), and the halted state was exported to `halt_snapshot_after_execution/`.
   `launch/launcher_resume_execution.py` then restarted the backend and called the real `resume_execution`
   handler (the UI's Resume button) once, with a default body (no budget or policy change). It is guarded by
   `launch/intervention_execution_resume.txt`. The orchestrator re-queued only the failed T4.1 (its attempt count was
   kept, so it got exactly one more attempt). T4.1 failed again, and the run stopped there as agreed. No task was marked
   complete or skipped, and no check was overridden.
5. **Stop and export:** the backend was stopped (SIGINT), then `tools/export_project.py` ran (read-only).
6. **Incident, outside the research run:** a post-run status command in WSL ran `uv run` once without
   `UV_PROJECT_ENVIRONMENT`. That replaced the Windows dev venv `backend/.venv` with a Linux one. The process was
   killed, the broken venv removed, and the venv rebuilt on Windows with `uv sync --frozen` from `backend/uv.lock`.
   The offline suite then gave 398 passed, 26 skipped. No source file, DB row, workspace or research artifact was
   involved.

No OpenScientist source, prompt, model setting, config, blueprint, verifier result or task status was changed.
All pre-existing files were byte-identical at the end: `research/` (560), `backend/data/projects/` (51), and other
projects' WSL workspaces (236) (`integrity/postrun_checks.txt`).

**Still running:** this project's 2 E2B sandboxes (`iu7yrdut17pxxqofxfbvr`, session 1; `i2zvu0409dc52t40igxsl`,
session 2). They expire on their own after 24 h and are left for the user to decide on. Colab: 0 sessions.

## Contents

| Path | What |
|---|---|
| `launch/research_prompt.md` | Research question and constraints, submitted verbatim as the first chat message |
| `launch/clarify_events.jsonl` | The clarify SSE stream (prompt, generated brief, project) |
| `plan_exports/vague_research_plan.json` | **ResearchPlan** |
| `plan_exports/master_plan.json` | **MasterPlan** (approved blueprint) |
| `plan_exports/context.json` | Brief, papers + notes, knowledge graph, all gaps, chosen gap |
| `db_export/literature_papers.json` | All 300 screened papers with relevance, reasons, inclusion (48 included) |
| `db_export/runs/` | All 6 stage runs (literature, gaps, plan, blueprint, 2 executions) with logs and results |
| `db_export/task_states.json`, `task_traces/` | Per task: status, attempts, cost, verifier checks, issues, and the full tool-call trace of its last attempt |
| `db_export/usage.json`, `gpu_usage.json` | Every LLM call (tokens, cost) and GPU job |
| `db_export/project*.json`, `messages.json` | Brief, chosen gap, plan, blueprint pointer, settings (`project_review.json` is `null`: no review ran) |
| `workspace_copy/src/train.py`, `docs/architecture_spec.md`, `scripts/` | Experimental code and specification |
| `workspace_copy/data/metrics_*.csv`, `data/checkpoints/` | Raw per-epoch measurements (final GPU run) and model checkpoints |
| `workspace_copy/logs/gpu/` | Colab GPU evidence: `nvidia-smi` environment, CUDA validation log, training log, OS timings |
| `workspace_copy/analysis/` | Merged metrics, gap trajectory, checkpoint statistics, crossover report, Table 1 (CSV and LaTeX) |
| `workspace_copy/figures/` | fig1 (test accuracy, failed task), fig2 (accuracy gap), fig3 (loss/validation curves) |
| `workspace_copy/results/SUMMARY.md` | OpenScientist's results summary (T4.4) |
| `workspace_copy/team/NOTES.md`, `.scratch/` | Agents' shared notes and the code cells they executed |
| `halt_snapshot_after_execution/` | DB, plan and workspace state at the autonomous stop (07:53Z), before the resume; large data/checkpoints listed, not copied |
| `t2.1_attempt1_snapshot/`, `t2.1_attempt2_snapshot/` | T2.1's earlier GPU logs/CSVs, overwritten in the workspace by later attempts |
| `preflight/` | Preflight scripts and outputs (DB/beta/E2B, Colab check, Bedrock call, GPU probe) |
| `launch/` | Launchers, status/watch scripts, backend logs (`*_session1.log`, `*_session2.log`), intervention marker, timestamps |
| `integrity/` | Before/after checksums and post-run checks |
| `tools/export_project.py` | The read-only export |

**Not produced:** paper PDF and LaTeX, `references.bib`, claims audit, judge reports. The Report stage never ran.
**Original locations (untouched):** WSL `~/.openscientist/workspaces/a2794d1959b5`;
`backend/data/projects/a2794d1959b5/`; all project rows in the Supabase DB.
`workspace_copy/` is 327 MB, mostly checkpoints and the dataset; keep that in mind before committing this folder.
