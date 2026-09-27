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

6. **Execution runtime** (`backend/app/execution/`) — `LocalSandbox` runs agent code in a
   per-project workspace with its own Python env, confined by macOS `sandbox-exec` (writes only in
   the workspace; no access to the repo, `.env`, database or `~/.ssh`; API keys never reach agent
   code; network allowed). A cloud runner can implement the same `Sandbox` interface later.
   Tools: `run_python`, `run_shell`, files, `install_packages` (validated specs), `http_request`
   and `download_file` (private/loopback addresses blocked on every redirect hop),
   `search_papers`, `lookup_resources`, hosted `web_search`, `report_result`. A catalog of
   scientific APIs, data repositories and software across fields (biology, chemistry, earth
   science, engineering/CAD, architecture, economics, social science, math…) tells agents what
   exists and what it requires. `agent.py` is the tool-use loop with step and cost limits.
7. **Blueprint** — after the plan is approved: locate dataset sources (`gpt-6-sol` + web search),
   compile `master_plan.json` (`gpt-6-astra`: agent team, executable tasks with exact inputs/outputs,
   acceptance checks, compute, per-task budget, human checkpoints), then validate in code (tools
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

**Next: Step 3** — consolidation + report agents: turn the executed workspace into a scaffolded
report and a conference-style paper.

Models: `gpt-6-astra` only for heavy reasoning / agentic stages (gaps, plan); `gpt-6-sol` and
`gpt-6-luna` everywhere else.

## Run locally

Put keys in `.env` at the repo root (see `.env.example`), then in two terminals:

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
| `backend/app/pipeline.py` | Stage chaining and autonomous auto-decisions |
| `backend/app/graph.py` | Knowledge graph (papers, methods, datasets, tasks, citations) |
| `backend/app/jobs.py` | Background runs with progress stored in the `Run` table |
| `backend/app/llm.py` | OpenAI Responses API wrapper (streaming + structured outputs) |
| `backend/app/config.py` | Settings and model tiers (`gpt-6-astra` / `gpt-6-sol` / `gpt-6-luna`) |
| `backend/app/db.py` | SQLite via SQLModel (Postgres + pgvector later) |
| `frontend/src/components/` | Workspace, QuestionCards, BriefCard, LiteratureRun, GapsRun, PlanRun, BlueprintRun, ExecutionRun, WorkspaceFiles, Library, KnowledgeGraph, Notebook, … |
| `frontend/src/lib/api.ts` | API client + SSE parser |
