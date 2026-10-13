#!/usr/bin/env bash
# Environment for colab_gpu_probe.py, copied from backend/scripts/colab_gpu_tool_check.sh (WSL only).
set -uo pipefail
cd "/mnt/c/Users/Pranav Bhalerao/desktop/projects/openscientist/opensci-bedrock/backend"
export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/opensci-bedrock" UV_LINK_MODE=copy
export DATABASE_URL="sqlite:////tmp/osci-gpu-probe-$$.db" E2B_API_KEY=""
export AWS_REGION=us-east-1 AWS_ACCESS_KEY_ID=blocked-no-llm-calls AWS_SECRET_ACCESS_KEY=blocked-no-llm-calls TAVILY_API_KEY=""
unset AWS_SESSION_TOKEN AWS_PROFILE BEDROCK_MODEL_ID MODEL_REASONING MODEL_STANDARD MODEL_BULK
export COLAB_MAX_SESSIONS=1 COLAB_CREDENTIALS_FILE="$HOME/.openscientist/colab/credentials.json"
export PYTHONPATH="$PWD"
"$HOME/.local/bin/uv" run --frozen python ../research/fmnist_augmentation_e2e_2026-10-10/preflight/colab_gpu_probe.py </dev/null
rc=$?
rm -f "/tmp/osci-gpu-probe-$$.db"
exit $rc
