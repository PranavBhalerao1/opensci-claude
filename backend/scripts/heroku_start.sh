#!/bin/sh
# Heroku web process entrypoint (see Dockerfile). Heroku sets $PORT.
set -e

# Workspaces (~/.openscientist/workspaces) and Colab state live under HOME; point it at a
# directory the image made writable for Heroku's non-root user.
export HOME=/app/home

# Colab GPU jobs need the ADC credentials as a file. On Heroku, store the JSON in the
# COLAB_CREDENTIALS_JSON config var and it is written here at boot.
if [ -n "$COLAB_CREDENTIALS_JSON" ]; then
    mkdir -p "$HOME/.openscientist/colab"
    chmod 700 "$HOME/.openscientist/colab"
    umask 077
    printf '%s' "$COLAB_CREDENTIALS_JSON" > "$HOME/.openscientist/colab/credentials.json"
    export COLAB_CREDENTIALS_FILE="$HOME/.openscientist/colab/credentials.json"
fi

# One process only: background jobs run inside it (app/jobs.py), so extra workers or dynos
# would not see each other's runs.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
    --proxy-headers --forwarded-allow-ips='*'
