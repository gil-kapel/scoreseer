# ScoreSeer backend — multi-stage: `dev` (debugpy + reload deps) and `prod` (lean).
#   dev :  docker compose (build target: dev) — attach Cursor on 5678
#   prod:  docker compose -f docker-compose.prod.yml (build target: prod)
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/app/.venv/bin:$PATH"

RUN pip install --no-cache-dir uv
WORKDIR /app

# Dependency layer (cached unless pyproject/lock change). Runtime deps only.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-install-project

# Application code + migration entrypoint.
COPY backend ./backend
COPY docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

WORKDIR /app/backend
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# --- dev: extra tooling + debugpy, source is bind-mounted by compose ---
FROM base AS dev
RUN uv sync --frozen --extra dev --no-install-project
EXPOSE 8000 5678
CMD ["python", "-m", "debugpy", "--listen", "0.0.0.0:5678", \
     "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# --- prod: single uvicorn worker (in-process scheduler + predict/cancel
#     registries assume ONE process — do not add --workers). Binds $PORT when the
#     host injects one (Render), else 8000 (Fly / compose). ---
FROM base AS prod
ENV ENVIRONMENT=production
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
