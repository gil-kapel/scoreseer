# ScoreSeer — World Cup 2026 Match Result Estimator

A personal "accuracy lab" that predicts FIFA World Cup 2026 results (final score,
likely scorers, explanation), then grades itself against real results and calibrates
over time.

- **Data:** structured sports APIs (football-data.org + API-Football, free-first) for
  authoritative fixtures/results; Claude web search for pre-match narrative.
- **Prediction:** Claude structured output (score, scorers + likelihoods, confidence, why).
- **Loop:** scheduled predict → auto-grade after full-time → calibrate.

Planning docs: [docs/prd.md](docs/prd.md) · [docs/ux-flows.md](docs/ux-flows.md) ·
[docs/ui-spec.md](docs/ui-spec.md) · [docs/architecture.md](docs/architecture.md) ·
[docs/dev-plan.md](docs/dev-plan.md)

## Stack

Python 3.12 · FastAPI · SQLModel · Postgres · Alembic · APScheduler · Anthropic SDK ·
loguru · uv. Frontend (later): Next.js + shadcn/ui.

## Quickstart (backend)

```bash
# 1. Install deps (uv fetches Python 3.12 automatically)
uv sync --extra dev

# 2. Start Postgres
docker compose up -d

# 3. Configure env
cp .env.example .env   # fill in keys as you reach the slices that need them

# 4. Apply migrations
cd backend && uv run alembic upgrade head

# 5. Run the API
uv run uvicorn app.main:app --reload   # GET http://localhost:8000/health

# 6. Tests
uv run pytest
```

## Run fully in Docker (with Cursor debug ports)

```bash
cp .env.example .env          # fill in ANTHROPIC_API_KEY + sports keys
docker compose up -d --build  # Postgres + backend (migrates on start) + frontend
curl http://localhost:8000/health
open http://localhost:3000     # the web app
```

Ports — **8000** API · **5678** Python debugger · **3000** web app · **9229** node
debugger. Inside the compose network the backend reaches Postgres at `postgres:5432`
(host `5433`); the frontend reaches the API at `http://backend:8000` (server-side
fetch, no CORS).

**Debug from Cursor/VS Code:** Run & Debug → *"Attach to ScoreSeer backend (Docker
:5678)"* or *"…frontend (Docker :9229)"* ([.vscode/launch.json](.vscode/launch.json)).
Both `./backend` and `./frontend` are volume-mounted, so edits are live (the frontend
hot-reloads; the backend has no `--reload`, so `docker compose restart backend`).

The **scheduler is OFF by default** (`SCHEDULER_ENABLED=false`) so the container
never makes autonomous Claude calls. Set it to `true` in
[docker-compose.yml](docker-compose.yml) to enable scheduled predict/grade runs.

Frontend is a thin slice so far: app shell + **Upcoming** (`/`) and **Dashboard**
(`/dashboard`), Next.js + Tailwind v4 (analyst-dark). More screens to come.

## Management CLI

```bash
cd backend
uv run python -m app.cli sync-fixtures        # sync WC2026 fixtures (cached, free-first)
uv run python -m app.cli predict-fixture      # predict the earliest upcoming fixture
uv run python -m app.cli grade-fixture        # grade one finished, predicted fixture
uv run python -m app.cli run-predict          # predict-run over eligible fixtures (capped)
uv run python -m app.cli run-grade            # grade-run over finished, predicted fixtures
```

## Status

Slices 1–6 complete: foundation, fixtures sync, grading metrics, prediction core
(Claude web search + structured output), result+grade, and runs+scheduler. See
[docs/dev-plan.md](docs/dev-plan.md) for the roadmap.
