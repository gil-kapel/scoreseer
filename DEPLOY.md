# Deploying ScoreSeer

ScoreSeer is two services (FastAPI backend + Next.js frontend) and a Postgres DB.
The **browser only ever talks to the Next.js frontend**; the frontend talks to the
backend server-side (adding the API key). So there's no CORS to configure and the
backend never needs to be public.

## Security model (build it once, before any public deploy)

| Layer | Env var(s) | Effect |
|-------|-----------|--------|
| Backend API key | `API_TOKEN` | When set, every API route except `/health` requires header `X-API-Key`. The frontend injects it from its server env. |
| Owner-only UI gate | `BASIC_AUTH_USER` + `BASIC_AUTH_PASSWORD` | HTTP Basic auth on the entire frontend (Next.js middleware). |
| Scheduler | `SCHEDULER_ENABLED` | Keep `false` unless you want autonomous Claude spend. |

All three are **off when their env vars are empty**, so local dev stays open. Set them in production.

Generate secrets:
```bash
openssl rand -hex 32   # API_TOKEN
openssl rand -hex 16   # POSTGRES_PASSWORD, BASIC_AUTH_PASSWORD
```

> Single-process note: the backend runs **one** uvicorn worker on purpose — the
> APScheduler jobs and the in-process predict/cancel registries assume a single
> process. Do not add `--workers N` or run multiple backend replicas.

---

## Option A — One host, all-in-one (simplest)

Any VPS/box with Docker (Fly.io, a small DigitalOcean/Hetzner droplet, etc.).

```bash
cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, FOOTBALL_DATA_API_KEY, API_TOKEN,
#          BASIC_AUTH_USER, BASIC_AUTH_PASSWORD, POSTGRES_PASSWORD
docker compose -f docker-compose.prod.yml up -d --build
```

This builds the lean `prod` images (no debug ports, no source mounts), runs
migrations on boot, and publishes **only** the frontend on `WEB_PORT` (default 3000).
Put a TLS reverse proxy (Caddy/nginx/Traefik) in front for HTTPS.

Post-deploy checks:
```bash
curl -fsS http://localhost:8000/health        # from the host: {"status":"ok","db":"ok"}
curl -fsS -o /dev/null -w '%{http_code}\n' http://localhost:3000   # 401 until you send Basic auth
```

Seed data once it's up (free, no Claude):
```bash
docker compose -f docker-compose.prod.yml exec backend python -m app.cli sync-fixtures
docker compose -f docker-compose.prod.yml exec backend python -m app.cli poisson
```

---

## Option B — Vercel (frontend) + Fly.io (backend + Postgres)

This is the path the project is wired for (`fly.toml` at the repo root, Vercel via MCP).

### B1. Backend on Fly.io (deploys from local source — no GitHub needed)

```bash
# one-time
brew install flyctl          # or: curl -L https://fly.io/install.sh | sh
fly auth login               # opens a browser; needs a Fly account (+ card on hobby plan)

# from the repo root (fly.toml is here)
fly launch --no-deploy --copy-config --name scoreseer-api   # claim the app name
fly postgres create --name scoreseer-db                     # managed Postgres
fly postgres attach scoreseer-db                            # prints + sets DATABASE_URL

# IMPORTANT: the app uses the asyncpg driver. Take the attached connection string
# and re-set DATABASE_URL with the +asyncpg scheme (replace `postgres://`):
fly secrets set DATABASE_URL="postgresql+asyncpg://<user>:<pass>@scoreseer-db.flycast:5432/scoreseer"

# app secrets
fly secrets set API_TOKEN="$(openssl rand -hex 32)" \
                ANTHROPIC_API_KEY="..." \
                FOOTBALL_DATA_API_KEY="..."

fly deploy                   # builds the Dockerfile `prod` target, runs migrations on boot
fly logs                     # watch boot + migrations
curl -fsS https://scoreseer-api.fly.dev/health   # {"status":"ok","db":"ok"}
```

Seed data (free, no Claude):
```bash
fly ssh console -C "python -m app.cli sync-fixtures"
fly ssh console -C "python -m app.cli poisson"
```

### B2. Frontend on Vercel

Set these env vars on the Vercel project (Production + Preview), then deploy:
- `API_BASE` = `https://scoreseer-api.fly.dev`
- `API_TOKEN` = the **same** value set on Fly
- `BASIC_AUTH_USER`, `BASIC_AUTH_PASSWORD` = your owner login

Vercel runs the Next.js server, so server components + the `/api/*` proxy routes
reach the backend with the key attached. No `NEXT_PUBLIC_*` secrets exist.

> Note `API_TOKEN` must match on both sides — it's how the Vercel frontend proves
> itself to the Fly backend.

---

## Environment variable reference

See `.env.example`. Production-relevant:

| Var | Required (prod) | Notes |
|-----|-----------------|-------|
| `DATABASE_URL` | yes | `postgresql+asyncpg://…` |
| `ANTHROPIC_API_KEY` | for LLM predicts | Poisson runs without it |
| `FOOTBALL_DATA_API_KEY` | yes | free tier; fixtures + results |
| `API_TOKEN` | yes | backend API key (frontend injects it) |
| `BASIC_AUTH_USER` / `BASIC_AUTH_PASSWORD` | recommended | owner-only UI gate |
| `ENVIRONMENT` | yes | `production` → JSON logs |
| `SCHEDULER_ENABLED` | no | `false` (default) avoids autonomous spend |
| `POSTGRES_PASSWORD` | Option A | used by `docker-compose.prod.yml` |
| `WEB_PORT` | no | published frontend port (default 3000) |

## Rollback / logs
```bash
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml down            # stop (keeps the pgdata volume)
```
