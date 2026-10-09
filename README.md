# OpenScientist

Vibe-science: ask a question in plain words and run a real investigation, no PhD required.

```
Prompt → Planning Agent → Blueprint Agent → Execution (Orchestrator + agents) → Consolidation → Report
```

Step 1 · Planning Agent — complete:

1. App shell — chat, projects, streaming.
2. **Clarify** — the model asks up to 2 rounds of multiple-choice questions (cards, with a
   "Not sure — decide for me" option), then writes a `research_brief`. The user revises it by
   replying, or confirms it with a literature depth (Quick / Standard / Deep). In Autonomous
   mode the questions are answered by a proxy call and the brief is confirmed automatically.
3. **Literature review** (background job, polled by the UI) — search Semantic Scholar
   (OpenAlex fallback) → merge & pre-rank → screen with `gpt-6-luna` → optional citation hop
   (Deep) → extract structured notes with `gpt-6-sol` → link citations → overview with themes and
   open problems. Papers, notes, citation links and searches are cached globally, so the
   knowledge graph grows across projects and repeat reviews in a field are ~3× faster.

4. **Gap finding** (starts automatically after the literature review) — `gpt-6-astra` reads every
   paper's notes plus the themes and open problems and proposes 5–6 candidate gaps with a
   hypothesis, approach and scores; each gap's novelty is re-checked against targeted Semantic
   Scholar searches (`gpt-6-sol` judges overlap); gaps are ranked by novelty 30% · feasibility 30% ·
   impact 25% · testability 15%. Guided users pick (or steer and regenerate); autonomous mode takes
   the top pick. Stage chaining lives in `backend/app/pipeline.py`.
5. **Plan** (starts when a gap is chosen) — `gpt-6-astra` drafts `vague_research_plan.json`
   (phases → tasks with inputs/outputs/dependencies, datasets, methods, baselines, metrics with
   success thresholds, validation, compute, risks, deliverables, open questions). The task graph is
   validated in code (unique ids, known deps, no cycles) with one repair pass. Revise by chatting
   (`gpt-6-sol`) or by editing the JSON (validated); approve to export
   `backend/data/projects/<id>/vague_research_plan.json` and `context.json` (brief, clarification,
   papers + notes, knowledge graph, all gaps, chosen gap). Autonomous mode approves automatically.

Step 2 · Blueprint & execution:

6. **Execution runtime** (`backend/app/execution/`) — `E2BSandbox` runs agent code in an E2B
   cloud sandbox (`E2B_API_KEY`, template `E2B_TEMPLATE`, default `openscientist-cpu`) with its own
   Python and conda envs. The per-project workspace on this machine stays the source of truth:
   changed files are pushed before each command and results pulled back after it (and before
   verification, reports, the workspace browser and package export). API keys never reach agent
   code; only the project's own credentials do. Explicit CUDA work goes to Google Colab (`run_gpu_jobs`).
   There is no local execution: without E2B, code-running tools fail with a clear error.
   Tools: `run_python`, `run_shell`, files, `install_packages` (validated specs), `http_request`
   and `download_file` (private/loopback addresses blocked on every redirect hop),
   `search_papers`, `lookup_resources`, hosted `web_search`, `report_result`. A catalog of
   scientific APIs, data repositories and software across fields (biology, chemistry, earth
   science, engineering/CAD, architecture, economics, social science, math…) tells agents what
   exists and what it requires. `agent.py` is the tool-use loop with step and cost limits.
7. **Blueprint** — after the plan is approved: locate dataset sources (`gpt-6-sol` + web search),
   compile `master_plan.json` (`gpt-6-astra`: agent team, executable tasks with exact inputs/outputs,
   acceptance checks, compute, per-task cost estimate, human checkpoints), then validate in code (tools
   exist and run here, inputs trace to upstream outputs or datasets, no cycles, budget) with one
   repair pass; dataset URLs are checked for reachability. What cannot run locally (CUDA, human
   steps, missing API keys) is flagged, not hidden. Guided users revise by chat and approve;
   autonomous mode approves itself.

Every model call's cost is recorded (`Usage` table) and shown per project in the Notebook.

8. **Execution** (`backend/app/execution/orchestrator.py`) — runs `master_plan.json`: tasks in
   dependency order, up to 3 in parallel, each by its agent in the sandbox. After each task, code
   checks the declared outputs exist and a verifier model checks the acceptance criteria against
   file previews (CSV row counts and head/tail are computed exactly); failures retry with the
   verifier's feedback, then block only their branch. Human-required tasks wait for you (mark done
   / skip); you can also accept a failed task's output. Guided mode pauses at checkpoints; every run
   pauses at the budget. Pause / resume / cancel; state survives server restarts. Per-project model
   policy: `default` (flagship for hard reasoning), `economy` (no flagship), `minimal` (cheapest).
   The UI shows agent lanes with live steps, a task table with checks and full agent logs, and a
   workspace browser with CSV/image/text previews.

9. **Open-ended agents & swarms** — agents are not limited to a tool list: they find services with
   `web_search`, read docs with `read_webpage`, and call them via `http_request` or their own client
   code; install software via pip or `install_conda_packages` (private micromamba, conda-forge /
   bioconda, shared package cache); run long jobs with `start_process` / `check_process` / `wait`;
   edit code precisely with `edit_file`; fan out with `spawn_subagents` (parallel sub-agents sharing
   the workspace); share findings via `post_note` / `read_notes`; and ask the user for a key with
   `request_credential` (stored per project, exposed only to that sandbox). Blueprints may use
   2–12 agents and up to 4 tasks run at once. Verified end to end: a 4-agent swarm implemented and
   tested a novel attention mechanism and trained it against a baseline in parallel sub-agents on
   the Apple GPU ($0.11); a single agent chose a COX-2 structure, installed AutoDock Vina via conda,
   docked ibuprofen and validated the pose by re-docking (0.44 Å RMSD) ($0.36).

Step 3 · Consolidation & report:

10. **Report** (`backend/app/agents/report.py`) — after execution: the Consolidation Agent turns
    the brief, gap, plan, every task's outcome/checks/issues, team notes and result files into a
    scaffold (findings with evidence, hypothesis verdict, success-criteria status, figures,
    limitations, deviations, section outline). The Report Agent writes a conference-style LaTeX
    paper from it, installs Tectonic via conda and compiles the PDF itself. `references.bib` is
    generated by code from the literature stage (no invented citations); unknown `\cite` keys are
    flagged and a claims audit compares the paper with the evidence. The UI shows the verdict,
    findings, criteria, integrity checks and the PDF, with downloads including a zip of the whole
    research package. Autonomous projects run this automatically after execution.

Models: `gpt-6-astra` only for heavy reasoning / agentic stages (gaps, plan); `gpt-6-sol` and
`gpt-6-luna` everywhere else.

## Reliability

- **Model escalation**: a failed task retries on the next model tier (Luna → Sol → Astra), so most
  work stays cheap and only hard tasks pay for a stronger model.
- **Platform-verified checks**: the orchestrator runs produced tests itself and gives the verifier
  exact file facts; agents cut off by their step limit are still verified if their outputs exist.
- **Autonomous safety**: the report is written only when every task finished; any stage can be
  stopped (header "Stop" button) and retried; execution pauses at the budget.
- Workspaces live in `~/.openscientist/workspaces` (outside the repo, so tools like pytest/git work).
- Tests: `cd backend && uv run pytest` (offline regression suite).

## Auth & multi-user

Every project belongs to a signed-in user (Supabase Auth: email/password + Google).
The frontend never talks to the database directly — it calls FastAPI with the
user's Supabase access token, and FastAPI verifies that token and derives the
user id itself before touching the database; it never trusts a user id from the
client. Postgres (the Supabase project's own, not local SQLite) enforces Row
Level Security so a user's data is scoped to them even if an app-layer check is
ever missed. See `supabase/migrations/` for the schema and policies, and
`backend/app/auth.py` for token verification.

## Run locally

Put keys in `.env` at the repo root and `frontend/.env.local` (see the two
`.env.example` files), then in two terminals:

```bash
cd backend && uv run uvicorn app.main:app --reload --reload-dir app --port 8000
cd frontend && npm run dev          # http://localhost:3000
```

## Layout

| Path | What |
|---|---|
| `backend/app/main.py` | FastAPI app, CORS, health |
| `backend/app/routes/projects.py` | Projects + messages, SSE streaming chat |
| `backend/app/agents/clarify.py` | Clarify stage: schemas, prompts, question/brief loop |
| `backend/app/agents/literature.py` | Literature pipeline (search, screen, extract, overview) |
| `backend/app/sources/` | Semantic Scholar + OpenAlex clients with rate limiting and backoff |
| `backend/app/agents/gaps.py` | Gap finding: propose, novelty check, rank, choose |
| `backend/app/agents/plan.py` | Plan: draft, validate DAG, revise, approve, export |
| `backend/app/agents/blueprint.py` | Blueprint: resolve data, compile, validate, approve |
| `backend/app/execution/` | Sandbox, tool registry, resource catalog, agent loop, orchestrator |
| `backend/app/agents/report.py` | Consolidation, report writing, citation & claims audit, package |
| `backend/app/pipeline.py` | Stage chaining and autonomous auto-decisions |
| `backend/app/graph.py` | Knowledge graph (papers, methods, datasets, tasks, citations) |
| `backend/app/jobs.py` | Background runs with progress stored in the `Run` table |
| `backend/app/llm.py` | OpenAI Responses API wrapper (streaming + structured outputs) |
| `backend/app/config.py` | Settings and model tiers (`gpt-6-astra` / `gpt-6-sol` / `gpt-6-luna`) |
| `backend/app/db.py` | SQLite via SQLModel (Postgres + pgvector later) |
| `frontend/src/components/` | Workspace, QuestionCards, BriefCard, LiteratureRun, GapsRun, PlanRun, BlueprintRun, ExecutionRun, ReportRun, WorkspaceFiles, Library, KnowledgeGraph, Notebook, … |
| `frontend/src/lib/api.ts` | API client + SSE parser |
