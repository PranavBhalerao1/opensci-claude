# OpenScientist rerun: Fashion-MNIST data augmentation (2026-10-09/10)

**Project ID:** `6d8c3c93c209` · owner `56ec46c1-…` (pranavrbhalerao@gmail.com) · autonomous mode
**Final status: pipeline COMPLETE; scientific review UNRESOLVED.** Every stage ran, all 11 tasks passed
verification on their first attempt, real CUDA training ran on a Colab NVIDIA L4, and a full paper (PDF + LaTeX)
was produced. The independent review ended `unresolved` after 3 repair rounds. One blocking issue remained, and it
is a **false positive caused by a platform bug** (see below), not a defect in the paper.

This reruns the failed project `d95fb65c9f7a` (`../fmnist_augmentation_run_2026-10-09/`) with the same
research prompt (byte-identical, `launch/research_prompt.md`) and the same project settings. Nothing from that
project was fed in. Its files were verified byte-identical (96/96 sha256) before and after this run.

## Validation before launch

| Check | Result |
|---|---|
| `BEDROCK_INTEGRATION=1 uv run pytest tests/test_bedrock_integration.py -k long_output -v` (WSL) | **PASSED**, live: `POST …/us.anthropic.claude-sonnet-4-6/invoke-with-response-stream → 200 OK` at `max_tokens=64000`, not refused, no fallback to 32K |
| Offline suite (WSL) | 363 passed, 21 skipped (the gated live tests); `test_blueprint_feasibility.py` 28 passed |
| Supabase Postgres 17.6 | all 11 model tables, 0 missing columns, so `init_db()` altered nothing (no migration) |
| Beta allowance | approved, $50 cap, $44.03 remaining |
| E2B | key valid, 0 sandboxes running, template `openscientist-cpu` |
| Colab | `Colab OK: 298.20 compute units left … 0 active session(s)` |
| Feasibility code | `feasibility_errors`, `review_feasibility`, `lost_requirements`, `_checked` present; `REPAIR_ROUNDS=2`; `LONG_MAX_TOKENS=64000` |

Script: `launch/preflight.py` (read-only). The code that ran is HEAD `d5538a0` plus the uncommitted reliability fixes
(`launch/source_state.txt`, `launch/source_uncommitted.diff`). It was unchanged during the run, re-checked at the end.

## Outcome by stage

| Stage | Result | Time (UTC) | LLM cost |
|---|---|---|---|
| Clarify (brief, auto-confirmed) | done | 22:36:45–22:37:10 | $0.03 |
| Literature review | done: 300 papers screened, 55 included | 22:37:10–22:47:01 (9.9 m) | $0.80 |
| Gap finding | done; gap **g2** auto-chosen | 22:47:02–22:55:13 (8.2 m) | $0.43 |
| Research plan | done (64K streamed, freeform JSON) | 22:55:14–22:57:50 (2.6 m) | $0.21 |
| Blueprint | **done with no intervention**: compile → feasibility review found 1 contradiction → 1 repair round → auto-approved, 0 warnings | 22:57:51–23:09:24 (11.6 m) | $1.11 |
| Execution | **11/11 tasks done, each on attempt 1**, all acceptance checks passed | 23:09:24–23:35:43 (26.3 m) | $2.38 |
| Report (LaTeX + PDF) | done | 23:35:44–23:44:26 (8.7 m) | $3.16 (4 reports) |
| Scientific review and refinement | 4 reviews, 3 repair rounds → **unresolved** | 23:44:28–02:49:13 | $6.07 review + $0.14 repair |

- **Wall time:** 4 h 12.6 min (22:36:37 → 02:49:13). Of that, 1 h 50.9 min (00:30:08 → 02:21:02) was an operator
  budget pause (see Operator actions). **Active pipeline time was about 2 h 22 min.**
- **Cost: $14.35 total.** LLM $14.32: 249 Bedrock calls (Claude Sonnet 4.6), 3,327,598 input tokens (1,836,720
  cached), 515,228 output tokens, 3 web searches. GPU $0.03: 0.28 Colab CU (298.20 → 297.92). E2B time is not metered
  by the app; 2 sandboxes ran for about 3.8 h and 0.6 h. The pre-launch live test cost about $0.0002 and was
  recorded only in the test suite's temporary DB.
- Largest single output: 41,180 tokens (the blueprint compile). Without the 64K budget it would have hit the old
  32K ceiling.

## Blueprint feasibility validation: worked

- The deterministic checks passed the compiled blueprint. The new **model feasibility review** then caught
  one real contradiction: *T4.3: "read gpu_log_seed42.txt and gpu_log_seed123.txt for device names" cannot be
  satisfied: T4.3 lists only analysis/… as inputs*.
- The bounded repair fixed it in 1 round without dropping the requirement. The repaired T4.3 reads
  `analysis/gpu_device_info.txt`, which upstream T3.1 produces from the GPU logs. Re-validation and re-review
  passed: `Blueprint repaired in 1 round(s)`.
- **CUDA evidence checks sit only on the GPU tasks** (T2.1, T2.2: `compute=cuda_gpu`, `run_gpu_jobs`). The CPU setup
  tasks T1.1 and T1.2 have no hardware checks. This is the exact contradiction that killed the previous run, and
  it is gone.
- Blueprint: 5 agents and 11 tasks. Design: 7 training sizes (500 … 60,000) × {noaug, aug} × seeds {42, 123},
  5 epochs, giving 28 runs.

## Colab GPU training: real, CUDA, traceable

- `logs/gpu/_environment.txt` holds `nvidia-smi` from the Colab VM: **NVIDIA L4**, driver 580.82.07, CUDA 13.0, Python 3.13.15.
- `logs/gpu/seed42_train.log` and `seed123_train.log` begin with `Using device: NVIDIA L4`. `results/gpu_log_seed*.txt`:
  `device: NVIDIA L4`, `torch version: 2.11.0+cu130`.
- `db_export/gpu_usage.json` has 4 rows: seed42_train 206.0 s, seed123_train 209.0 s, and 2 session-overhead rows
  (L4, $0.0299 in total). The OS timestamps in `logs/gpu/*.time` match these durations.
- Raw measurements: `results/results_seed{42,123}.csv`, 70 rows each (14 runs × 5 epochs), merged into
  `analysis/results_all.csv`.

**Result (OpenScientist's, not checked further here):** under the 5-epoch budget, augmentation *lowered* test
accuracy at every size. Mean Δ ranged from −8.05 pp (N=500) to −2.81 pp (N=60,000; noaug 91.40/91.57 %,
aug 88.52/88.84 %). The pre-registered hypothesis, a positive benefit at small N, was not supported.

## Why the review ended `unresolved` (preserved as evidence)

| Review | Verdict | Blocking issues | Cost |
|---|---|---|---|
| 1 | major_revision | T-001, T-002: two citations mischaracterised (kang2024game, kumar2025enhancing), both **real**, fixed by the report repair | $2.53 |
| 2 | major_revision | T-004: "Sub-figure caption for N=60,000 incorrectly reads N=500" | $1.32 |
| 3 | major_revision | T-004 (evidence unchanged, so the previous review was reused at no cost) | $0.00 |
| 4 | major_revision → **unresolved** (3 rounds used) | T-004 | $2.21 |

**T-004 is a false positive.** In every iteration's `paper.tex` (`plan_exports/review/iter-*/paper.tex`, L336–337)
the subfigure that includes `curves_size60000.png` carries `\caption{$N{=}60{,}000$.}`. The judge's evidence bundle
(`iter-*/bundle.md`, L1030) says otherwise:
`SOURCE id=figure:figures/curves_size60000.png label=fig:curves500 … Caption: $N{=}500$.` The judge and its
adversarial verifier trusted that metadata and marked the issue "confirmed". The report agent correctly found
nothing to change; round 2's rewrite was byte-identical.

**Root cause (not fixed, per instructions): `backend/app/integrity.py:158-169`.** The figure-environment regex uses
non-overlapping `re.finditer`, so it matches the outer `figure` and never the nested `subfigure` environments.
Every graphic in a subfigure group therefore gets the **first** `\caption` and `\label` of the whole figure.

Other review observations:
- **The judge's structured output hit `max_tokens` 4 times** (reviews 1 ×2, 2, 4). Each time, the built-in single
  retry recovered. The judge still uses the 32K non-streaming ceiling, since the 64K fix covers only plan and
  blueprint. Each truncation wasted about 32K output tokens (~$0.50).
- The judge raised T-003 and T-005 (test set used as validation) and then refuted them correctly: validation uses
  training-set indices (`src/gpu_train_seed*.py`).

## Other observations (not corrected)

- **Brief:** as in the previous run, the clarify agent added *RandomHorizontalFlip* to the augmentation
  (flip + RandomAffine ±10°, ±10 % translation). The prompt only suggested translations/rotations. Code and paper
  agree with the brief.
- **Gap g2** ("Training set size modulates augmentation benefit") widened the study from 4 runs to 28 runs over 7
  subset sizes. The core comparison (full data, seeds 42/123, 5 epochs) is included.
- `results/SUMMARY.md` (T4.3) describes the augmentation as "random crop + horizontal flip". That is wrong: the
  code is flip + RandomAffine. Neither the task verifier nor the judge caught it.
- Semantic Scholar returned HTTP 429 repeatedly during literature search; the backend retried. ResearchPlan and MasterPlan
  fell back to freeform JSON because their schemas are too large for constrained decoding. This is the logged,
  designed behaviour.

## Operator actions (complete list)

1. **Launch:** the real FastAPI app (uvicorn, port 8000, Supabase Postgres) ran in WSL2 through `launch/launcher.py`,
   a byte-identical copy of the previous run's launcher. It calls the real `create_project(autonomous=True)` and
   `post_turn(<research_prompt.md>)` handlers. Only bearer-token verification is skipped; the beta checks are
   called explicitly.
2. **Budget pause:** the user's rule was to pause for approval if spend was projected to exceed $15. The read-only
   `launch/budget_guard.py` sent SIGINT to the backend at 00:30:08, when the 3rd review asked for a 3rd repair
   round, with $11.26 spent (`launch/budget_guard.log`). The in-flight repair run is marked "Interrupted by a server
   restart" (`db_export/runs/13_repair_error_…`).
3. **One resume, authorized by the user:** `launch/launcher_resume_review.py` restarted the backend and called the
   real `resume_review` handler once (the UI's Resume button), guarded by `launch/intervention_review_resume.txt`.
   The loop continued from its saved `repair` step to the end.
4. **Cleanup, authorized by the user:** both of this project's E2B sandboxes were terminated after their
   `/home/user/workspace` was compared with `workspace_copy/` (`launch/e2b_cleanup.txt`):
   - `idvr8s9zefod5k7lgo0fs`: 116 files. 3 paper files differed because the host held the newer, final version.
     The sandbox's older copies are kept in `e2b_remote_stale_copies/idvr8s9zefod5k7lgo0fs/`.
   - `iz7ai44kjj9lclru6liwf`, created by the resumed session: 116 files, identical.

   Afterwards: 0 sandboxes, 0 Colab sessions, no backend process (`launch/postrun_checks.txt`).

No OpenScientist source, prompt, model setting, config, blueprint, verifier result or review was changed.

## Contents

| Path | What |
|---|---|
| `workspace_copy/paper/paper.pdf`, `paper.tex`, `references.bib`, `table_results.tex` | **Final paper** (= `plan_exports/review/iter-4/`, the last reviewed version) |
| `plan_exports/vague_research_plan.json` | **ResearchPlan** |
| `plan_exports/master_plan.json` | **MasterPlan** (approved, repaired blueprint) |
| `plan_exports/context.json` | Brief, papers and notes, knowledge graph, all gaps, chosen gap |
| `plan_exports/review/REVIEW.md`, `HISTORY.md`, `iter-1…4/` | Judge reports: per iteration the reviewed paper, evidence bundle, issues (`mistakes.json`) and repair plan |
| `db_export/literature_papers.json` | All 300 screened papers with relevance, reasons and inclusion (55 included) |
| `db_export/runs/` | All 17 stage runs: logs, results, errors (literature overview, gaps, plan, blueprint with repair log, execution, reports, reviews, repairs) |
| `db_export/task_states.json`, `task_traces/` | Per task: verifier checks, issues and the full agent tool-call trace |
| `db_export/usage.json`, `gpu_usage.json` | Every LLM call (tokens, cost) and GPU job |
| `db_export/project*.json`, `messages.json` | Brief, chosen gap, plan, blueprint pointer, review state, settings, chat |
| `workspace_copy/src/`, `config/`, `scripts/` | Experimental code and configuration |
| `workspace_copy/results/`, `analysis/` | Raw per-epoch measurements, merged table, Δ statistics, regression, bootstrap N*, trend diagnostics |
| `workspace_copy/logs/gpu/` | GPU training logs, `nvidia-smi` environment, job timings |
| `workspace_copy/figures/` | All figures |
| `workspace_copy/.scratch/` | Code cells the agents executed |
| `launch/` | Prompt, launchers, preflight, status/guard scripts, backend logs (session 1: `*_session1.log`; session 2: `stdout.log`, `backend.log`), clarify SSE stream, source state |
| `tools/export_project.py`, `tools/e2b_compare_and_kill.py` | The read-only export, and the sandbox comparison/cleanup |

**Original locations (untouched):** WSL `~/.openscientist/workspaces/6d8c3c93c209`;
`backend/data/projects/6d8c3c93c209/`; all project rows in the Supabase DB.
