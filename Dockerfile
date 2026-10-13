# Backend image for Heroku (container stack, built by heroku.yml). Only backend/ is copied;
# the frontend is deployed separately.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/backend/.venv/bin:$PATH"

# Same layout as the repo, so config.py's ROOT_DIR (/app) and BACKEND_DIR (/app/backend) hold.
WORKDIR /app/backend

COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/app ./app
COPY backend/scripts/heroku_start.sh ./scripts/heroku_start.sh

# Heroku runs the container as an arbitrary non-root user, so the dirs the app writes to
# (SQLite fallback + plan exports in backend/data, workspaces and Colab state under HOME)
# must be writable by anyone. They are ephemeral: wiped on every deploy and dyno restart.
RUN mkdir -p /app/backend/data /app/home \
    && chmod -R a+rwX /app/backend/data /app/home \
    && chmod +x scripts/heroku_start.sh

CMD ["/app/backend/scripts/heroku_start.sh"]
