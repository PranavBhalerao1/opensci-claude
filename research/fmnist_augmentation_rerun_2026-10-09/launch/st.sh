#!/bin/bash
# Read-only status of the rerun project (run from Windows Git Bash).
wsl -d Ubuntu -- bash -lc 'cd "/mnt/c/Users/Pranav Bhalerao/desktop/projects/openscientist/opensci-bedrock/backend" && PYTHONPATH=. UV_PROJECT_ENVIRONMENT=$HOME/.venvs/opensci-bedrock uv run python ../research/fmnist_augmentation_rerun_2026-10-09/launch/status.py 2>&1 | tail -40'
