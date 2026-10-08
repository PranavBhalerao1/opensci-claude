# Cloud GPUs on Google Colab

`run_gpu_jobs` can run on Google Colab instead of Modal (`GPU_PROVIDER=colab`).
The backend drives Google's official `colab` CLI (google-colab-cli 0.7.4, pinned)
with your own Colab account, authenticated once with Application Default
Credentials (ADC). Code: `backend/app/execution/colab_runner.py`.

## Readiness (keep this section current)

| Level | Status |
|---|---|
| Functionally validated on short jobs (Phase 0: protocol, transfers, T4/L4 CUDA jobs, artifact sync) | **Yes** (2026-10-08) |
| Live suite (`tests/test_colab_integration.py`, core and long tiers) through the runner | **Yes** (2026-10-08). Includes failures, timeouts, lost runtime, cancellation, crash + reaper, and a reference experiment that reproduced Modal's result |
| `run_gpu_jobs` tool handler + workspace/usage routes, isolated, no LLM calls; fresh-process auth | **Yes** (2026-10-08, 34/34 checks; 0.16 CU) |
| Ported into the Bedrock (Claude Sonnet 4.6) version: offline suites on Windows and WSL, no original test changed outcome | **Yes** (2026-10-08) |
| Same isolated handler test (`backend/scripts/colab_gpu_tool_check.sh`) on the Bedrock version | **Yes** (2026-10-08, 34/34 checks; 0.10 CU metered) |
| End-to-end, agent-driven research run through the backend and UI | Not yet |
| Unattended authentication over ≥ 8 days (hourly canary since 2026-10-07 21:22) | **Not yet verified** |
| Long GPU jobs | **45 min validated on T4**; 150 min on a CPU runtime. Jobs up to the tool's 3 h limit are not yet validated on GPU |
| Soak in real research use (Phase 4) | Not yet |

Until these are done, do not treat unattended long-term operation as verified.

## Setup (once)

The CLI supports Linux and macOS only. On Windows, run the backend in WSL2.

1. Install the backend environment (`uv sync` in `backend/`). It includes the
   pinned CLI on non-Windows systems. From a Windows checkout in WSL2, use a
   separate environment so the Windows `backend/.venv` is untouched: prefix
   every `uv` command with `UV_PROJECT_ENVIRONMENT=~/.venvs/opensci-bedrock`.
2. Log in with ADC and approve **every** consent checkbox. In WSL2, add
   `--no-launch-browser` and open the printed URL in your Windows browser:
   ```
   gcloud auth application-default login --scopes=openid,https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/userinfo.email,https://www.googleapis.com/auth/colaboratory
   ```
3. Move the credentials outside the repo and lock them down:
   ```
   mkdir -p ~/.openscientist/colab && chmod 700 ~/.openscientist/colab
   mv ~/.config/gcloud/application_default_credentials.json ~/.openscientist/colab/credentials.json
   chmod 600 ~/.openscientist/colab/credentials.json
   ```
4. Set the following in the environment the backend runs in. Environment
   variables override `.env`; keep them out of the repo's `.env` while a
   Windows-run backend shares that file, since Colab cannot run there:
   ```
   GPU_PROVIDER=colab
   COLAB_CREDENTIALS_FILE=/home/you/.openscientist/colab/credentials.json
   COLAB_MAX_SESSIONS=1
   ```
5. Verify. This call creates no session and uses no compute units:
   ```
   cd backend && uv run python -m app.execution.colab_runner check
   ```

The credentials file holds a refresh token with the broad `cloud-platform` scope.
Never commit it; `.gitignore` covers the default file names. Agents and Colab VMs
never receive it.

## Re-authentication

Each CLI call refreshes the access token from the refresh token, so no login is
needed per job. It stops working when:

- you revoke "Google Cloud SDK" access, or change your password or trigger a
  security event;
- the refresh token goes unused for about 6 months;
- your Workspace (school) admin enforces Google Cloud session control. Then refresh
  fails with `invalid_rapt` after the configured session length (1–24 h), and
  unattended use is not possible with that account.

When it stops working, GPU calls return: *"Colab GPU credentials were rejected …
repeat the setup login"*, and the backend logs an error. Repeat step 2, move the
new file into place (step 3), and run `check`. No restart is needed.

## Cleanup after a crash

An idle Colab VM keeps billing for at least 30 minutes. At startup, the backend
stops sessions that a dead backend process left behind (the ledger lives in
`~/.openscientist/colab/sessions/`). When it does, it:

- kills any `colab` CLI processes the dead backend left working on those sessions;
- bills the unmetered time to the project as an `(orphaned session)` row.

The files in `sessions/` hold short-lived runtime-proxy tokens: never print or share
them. To do the same cleanup by hand:
```
cd backend && uv run python -m app.execution.colab_runner reap
```
The startup check only warns about Colab sessions OpenScientist does not own
(for example your own notebooks); it never stops them. Run a single backend process.

## How it differs from Modal

- **Parallelism:** at most `COLAB_MAX_SESSIONS` GPUs at once, shared by all tasks
  (default 1; Colab does not document its concurrency limit). Further jobs queue,
  and each starts from a fresh copy of the workspace, so a call takes about
  ceil(jobs / sessions) × the job runtime. Per-job timeouts count from each job's
  own start. Total GPU time and cost are about the same as Modal's, plus a session
  start-up of roughly a minute.
- **GPUs:** T4 (1.07 CU/h) and L4 (1.54 CU/h), measured 2026-10-08. A100 and H100
  are not offered until their rates are measured. Availability is not guaranteed:
  Colab answers `503 Service Unavailable` when it has no capacity. The runner backs
  off (30/60/120 s), then reports the job as not run.
- **Environment:** the Colab image (Python 3.13, torch 2.11 + CUDA 13, ~740
  preinstalled packages), with `pip_packages` installed on top. Modal used Debian
  slim, Python 3.12 and only the listed packages. Each call records the exact
  versions in `logs/gpu/_environment.txt`.
- **Transfers:** 32 MB parts at about 6 MB/s each way; the proxy drops requests of
  128 MB. Files over 500 MB are not uploaded (as on Modal) and are listed in
  `skipped_uploads`. There is no persistent per-project volume.
- **Costs:** compute units are converted at $0.10/CU, so budgets, the beta cap and
  the UI stay in USD. One `GpuUsage` row is written per job, plus a
  `(session overhead)` row per session. Calls are refused when the account would
  drop below 10 CU, because Colab disallows automation without a positive balance.
  Compute units expire 90 days after purchase.

## Testing

- Offline, any OS: `cd backend && uv run pytest`. Colab is faked, and the suite
  stays on the Modal path whatever `.env` says.
- On Linux, `tests/test_colab_runner.py::test_remote_steps_locally` also runs the
  VM-side scripts for real. From a Windows checkout, run it in WSL2 with a separate
  environment:
  ```
  cd /mnt/c/…/backend && UV_PROJECT_ENVIRONMENT=~/.venvs/opensci-bedrock uv run pytest tests/test_colab_runner.py
  ```
- Live tests use compute units and need explicit approval for each tier, Linux or
  macOS, and `COLAB_INTEGRATION=1`. Run only `tests/test_colab_integration.py`
  with it: the rest of the suite pins the Modal path.
- Isolated check of the real `run_gpu_jobs` handler, workspace and usage routes
  and a fresh backend start (no LLM calls, temp database, under 1 CU):
  `bash backend/scripts/colab_gpu_tool_check.sh`.

## Future hosting (documented, not implemented)

A Linux host needs:

- Python 3.12 and `uv sync`;
- outbound HTTPS and WebSockets to `colab.research.google.com`, `*.prod.colab.dev`
  (runtime proxy) and `oauth2.googleapis.com`;
- the credentials as a file. On Azure App Service or Container Apps, mount a
  secret file. On Heroku there are no secret files, so writing an env var to a
  0600 file at boot needs a small follow-up change;
- a writable, ideally persistent, `~/.openscientist/colab`. On an ephemeral
  filesystem (Heroku dynos restart daily) the ledger is lost, so orphan reaping is
  degraded;
- a single backend process.
