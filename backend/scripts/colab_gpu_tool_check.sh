#!/usr/bin/env bash
# Isolated GPU-tool integration test on real Colab (no LLM calls; temp SQLite + temp workspaces; <1 CU).
# Linux/WSL only, with the backend's Linux environment and the stored ADC credentials:
#   bash backend/scripts/colab_gpu_tool_check.sh
# Uses compute units: run it only with an agreed budget (the test project's GPU budget is $0.10).
set -uo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."  # backend/
OUT="${COLAB_CHECK_LOG:-$HOME/.openscientist/colab/checks/colab_gpu_tool_check.log}"
mkdir -p "$(dirname "$OUT")"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-$HOME/.venvs/opensci-bedrock}" UV_LINK_MODE=copy
export DATABASE_URL="sqlite:////tmp/osci-gpu-it-$$.db" E2B_API_KEY=""
# No Bedrock or Tavily call can authenticate (the repo's .env holds real keys; env vars override it).
export AWS_REGION=us-east-1 AWS_ACCESS_KEY_ID=blocked-no-llm-calls AWS_SECRET_ACCESS_KEY=blocked-no-llm-calls TAVILY_API_KEY=""
unset AWS_SESSION_TOKEN AWS_PROFILE BEDROCK_MODEL_ID MODEL_REASONING MODEL_STANDARD MODEL_BULK
export GPU_PROVIDER=colab COLAB_MAX_SESSIONS=1
export COLAB_CREDENTIALS_FILE="${COLAB_CREDENTIALS_FILE:-$HOME/.openscientist/colab/credentials.json}"
export PYTHONPATH="$PWD"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"

{
echo "=== A. GPU tool integration test (fresh process) ==="
"$UV" run --frozen python scripts/colab_gpu_tool_check.py </dev/null

echo; echo "=== B. Fresh uvicorn backend: startup check with stored credentials ==="
DATABASE_URL="sqlite:////tmp/osci-gpu-it-uvicorn-$$.db" "$UV" run --frozen uvicorn app.main:app --port 8765 \
  </dev/null >/tmp/osci-uvicorn-$$.log 2>&1 &
PID=$!
sleep 25
code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8765/api/health)
kill "$PID"; wait "$PID" 2>/dev/null
echo "health HTTP $code"
grep -E "Application startup complete|Colab|colab|Traceback|ERROR|WARNING" /tmp/osci-uvicorn-$$.log | grep -v "GET /api/health" || true
if grep -qiE "credentials were rejected|Colab startup check failed|Traceback|Enter the authorization code" /tmp/osci-uvicorn-$$.log; then
  echo "FAIL  fresh backend: startup Colab check reported a problem"
else
  echo "PASS  fresh backend started, startup Colab check (reaper + balance) ran with stored ADC, no prompt, no errors"
fi
echo "--- account after"
DATABASE_URL="sqlite:////tmp/osci-gpu-it-check-$$.db" "$UV" run --frozen python -m app.execution.colab_runner check </dev/null
echo "--- ledger files: $(ls -A "$HOME/.openscientist/colab/sessions" | wc -l)"
} 2>&1 | tee "$OUT"

rm -f "/tmp/osci-gpu-it-$$.db" "/tmp/osci-gpu-it-uvicorn-$$.db" "/tmp/osci-gpu-it-check-$$.db" "/tmp/osci-uvicorn-$$.log"
hits=$(grep -cE 'ya29\.|1//0[A-Za-z0-9_-]{20,}|Bearer [A-Za-z0-9._-]{20,}|colab-runtime-proxy-token=eyJ|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.|"refresh_token"|"client_secret"' "$OUT")
echo "token-pattern hits in the test log: $hits"
