# Scientific review and refinement

Every paper written for a project with refinement on is reviewed by an independent judge before
it counts as finished. Problems the judge finds go back to the Planning Agent, which decides how
to fix each at its root. Only the invalidated part of the study is re-run, the paper is rewritten,
and a fresh judge reviews it again. The loop ends with an approved paper or an honest
"unresolved" outcome. It never approves on an error.

```
report → review (integrity gates → evidence bundle → judge → verification) → decision
           approved / unresolved / budget used / review failed → finished (stage "complete")
           integrity gates failed → rebuild the paper (no judge or planner call)
           blocking issues → repair: Planning Agent decides → plan revision | blueprint delta
                             | task re-runs | manuscript directives → execute (invalidated tasks
                             only) → report → review (a fresh judge) …
```

Code:

| Area | Where |
|---|---|
| Loop | `backend/app/refine.py` |
| Judge | `backend/app/agents/judge.py` |
| Deterministic checks | `backend/app/integrity.py` |
| Repair decisions and protected plan revision | `RepairPlan` in `backend/app/agents/plan.py` |
| Blueprint delta | `BlueprintDelta` in `backend/app/agents/blueprint.py` |
| Pipeline hooks | `_after_report`, `_after_execution` and `start_execution` in `backend/app/pipeline.py` |

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `REFINEMENT_DEFAULT` | `true` | New projects get `settings.refinement.enabled`. Projects without the key (all older ones) keep the plain pipeline until "Run scientific review" is pressed. |
| `REFINEMENT_MAX_ROUNDS` | `3` | Repair rounds per review session, so at most 4 reviews. |
| `REFINEMENT_MAX_USD` | `12` | LLM + GPU spend after the session started (judge, planner, re-execution, rewrites). |
| `MODEL_JUDGE` | `BEDROCK_MODEL_ID` | The judge's model, Claude Sonnet 4.6 on Bedrock by default. |
| `REVIEW_NUMERIC_CROSSCHECK` | `true` | Heuristic check of reported numbers against the result files. |

Per project: `settings.refinement = {enabled, max_rounds, max_usd, verify}`.

The loop is fully automatic in guided and autonomous projects. Repair executions skip the
blueprint's human checkpoints. A loop still pauses as **attention** when it needs a person: a
`human_required` task, a credential request, a task that keeps failing, or the beta cap.

Database: `projects.review` (jsonb). The backend adds the column on startup.
`supabase/migrations/20261009000000_scientific_review.sql` keeps the schema files in sync; apply
it to Supabase before or with the deploy.

## What the judge sees

Each review is **one fresh model call** with no history.

It receives, as numbered sources it must cite:
- the user's brief and the chosen research gap;
- the pre-registered plan (frozen at the first review) and the current plan, with a diff;
- protocol amendments (instructions only, with review ids stripped);
- platform facts per task: status, attempts, outputs present;
- the line-numbered LaTeX manuscript;
- each figure as an image (or a single-page PDF), with its caption and the code that names it;
- result files with row-count facts;
- analysis and figure code;
- for every citation: the cited paper's abstract and notes, plus the sentences citing it;
- deterministic integrity facts;
- a list of files left out.

It never sees:
- conversation history or earlier reviews;
- repair plans;
- the consolidation scaffold or task summaries;
- verifier verdicts, team notes or the old claims audit.

A test plants sentinel strings in each of these and checks that none reaches the request.

The rubric covers 12 criteria:
- research question validity and alignment with the original question
- experimental design
- controls and confounds
- statistics
- maths and computation
- reproducibility and execution integrity
- literature accuracy
- data integrity
- figures and tables
- whether the claims are supported
- whether novelty claims are substantiated
- internal consistency, including goalpost moves

Issues are FATAL, MAJOR or MINOR, with certainty demonstrated, likely or uncertain. Every
FATAL/MAJOR issue needs quoted evidence, why it matters, a concrete corrective action, its origin
(plan / blueprint / execution / analysis / report / literature) and what it invalidates.

## Validation, false positives and blocking

1. **Schema.** The schema is enforced by structured output and Pydantic. Semantic checks follow:
   every criterion assessed once, evidence present, known categories.
2. **Retries.** One fresh retry with the errors. A `max_tokens` stop retries at medium effort.
   Bedrock failures get one extra retry after the SDK's own. Still failing → `review_failed`.
3. **Grounding.** Every quote is checked against its source (manuscript quotes within the cited
   lines ±3). "X is missing" claims are checked by searching for their terms.
4. **Verification.** FATAL/MAJOR claims get a second, fresh, adversarial verification call.
5. **What blocks.** Only issues the verifier **confirms** block. If verification itself fails, a
   conservative rule applies: demonstrated or likely, and grounded. Uncertain serious issues
   become **open concerns** that the paper must disclose.
6. **Approval** needs all three:
   - a valid review with verdict accept or minor revision;
   - no confirmed blocking issue;
   - every hard integrity gate passing.

   A rejection with no verifiable issue triggers one more fresh review, then `unresolved`.

## Deterministic integrity checks

**Hard gates:**

| Gate | Check |
|---|---|
| H1 | The manuscript exists and the PDF was rebuilt by this report run. Clocks are compared with a 120 s tolerance, because the PDF is built in E2B. |
| H2 | Every citation key is in `references.bib`. |
| H3 | Every included figure exists. |
| H4 | The report stage did not rewrite or delete research files outside `paper/`. A write guard compares file manifests around the Report Agent. |
| H5 | The paper is newer than the latest execution. |

**Soft facts for the judge:**
- reported numbers not found in any result file;
- figures with no provenance, or older than the code that draws them;
- unfinished tasks;
- dangling `\ref`s;
- placeholders.

## Repair

The Planning Agent receives:
- the original objective and the pre-registration;
- the current plan, amendments and task table;
- the blocking issues and open concerns;
- each issue's history (new, persisting, resurfaced, regression), earlier actions and disputes;
- the remaining rounds and budget.

It returns a `RepairPlan`: a disposition for each issue (fix / disclose / dispute / escalate),
with a root-cause stage and the actions.

**Validation in code:**
- A fix can never be applied at a later stage than the issue's origin. An analysis error cannot be
  "fixed" by rewording the paper.
- Each fix needs a matching action.
- Task ids must exist.
- A dispute is allowed once per issue, and never on an issue that resurfaced.
- Disclose and escalate need a directive citing the issue.
- A plan that only disputes ends the loop as `unresolved`.

**Applying it.** Model outputs are saved under `review/iter-n/` before anything changes, so
resuming never pays twice.

| Repair | What happens |
|---|---|
| Plan revision | The research question, hypothesis and null hypothesis are restored in code. Changed metrics, success criteria, validation and baselines are recorded as `objective_changes`; the judge sees them in the plan diff. |
| Blueprint delta | Only new, replaced or removed tasks are listed; the delta is applied to the plain master plan. Unchanged tasks stay byte-identical. Their finished states are **carried over** to the new blueprint run, keyed by a hash of the task spec, agent and datasets. Changed tasks, new tasks and their dependents re-run. |
| Task changes | `orchestrator.request_changes` resets the target and its dependents only, and records the change as a protocol amendment. |
| Unfinished tasks | Tasks unfinished before the review and not selected are recorded as skipped, with the reason kept, instead of being silently retried. |
| Directives | Accumulate across rounds (each round rewrites the paper) until the planner withdraws them. Citation directives carry what the cited papers actually report. |

Literature and gaps are never re-run automatically.

## Stopping and states

`Project.review.status` takes one of these values:
- `reviewing`
- `repairing`
- `attention` (needs you; **Resume** continues)
- `approved`
- `unresolved`
- `budget_exhausted`
- `review_failed` (**Resume** retries)
- `stopped`

The loop stops when:
- the round limit is reached;
- the budget is used (checked before every step; a watcher stops a repair execution at the cap and
  restores the execution budget);
- a FATAL issue survives two fixes;
- two rounds neither reduce nor resolve blocking issues;
- a plan only disputes;
- the reviewer rejects without verifiable issues.

Every finished state sets stage `complete`, and the badge tells reviewed from unreviewed:

| Badge | Meaning |
|---|---|
| "Reviewed ✓" | Approved. |
| "Unresolved issues" | Blocking issues remain. |
| "Changed since review" | A manual report ran after the review finished. It is not re-reviewed automatically. |
| "Unreviewed" | No review has run. |

`REVIEW.md` states the outcome and unresolved issues, together with this limitation: approval
comes from a model reviewer of the same family as the authoring agents, which makes it a quality
gate, not a guarantee.

## Files and API

`backend/data/projects/<id>/review/` holds the review record. This directory is not in the agent
workspace and is included in the research package zip.

| File | Contents |
|---|---|
| `iter-n/mistakes.json` | The review (`openscientist.mistakes/v1`). |
| `iter-n/repair_plan.json` | The Planning Agent's decision. |
| `iter-n/plan_revision.json`, `iter-n/blueprint_delta.json` | Structural changes, when made. |
| `iter-n/bundle.md` | The exact text the judge saw. |
| `iter-n/paper.tex`, `iter-n/paper.pdf` | The reviewed manuscript. |
| `HISTORY.md`, `REVIEW.md` | Summary of all reviews and the final outcome. |

Routes:

| Route | Purpose |
|---|---|
| `GET /api/projects/{id}/review` | Effective state, iterations and issue tracks. |
| `GET /api/projects/{id}/review/file?name=&iteration=` | Allowlisted review files. |
| `POST .../review/start` | Opt in and start a new review session. |
| `POST .../review/resume` | Continue after `attention` or `review_failed`. |
| `POST .../review/stop` | End the loop. |

While a review is active, plan, blueprint and gap changes return 409. While the review or repair
job runs, starting execution and running the report return 409.

## Testing

Offline (no model, E2B or network calls):

```
cd backend && .venv/Scripts/python.exe -m pytest -q
```

| Test file | Covers |
|---|---|
| `test_integrity.py` | The deterministic checks. |
| `test_judge.py` | The judge's request, independence, grounding, blocking and retries. |
| `test_refinement.py` | End-to-end loop scenarios on the real scheduler, with scripted model calls and a fake task agent and report writer. |
| `test_review_routes.py` | Ownership, guards and file allowlist. |

`backend/scripts/judge_dry_run.py` builds the judge's evidence for a real project from a
read-only snapshot of the database and prints sizes, omissions, integrity facts and a cost
estimate. It is offline unless `--call` is given. `--call` makes one real review under
`--max-usd`, and `--from-export` rebuilds finished projects whose database rows are gone.
A Sonnet 4.6 review costs about $0.4–0.8.
