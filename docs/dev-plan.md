# Dev Plan (Composer): ScoreSeer

> Builds on [docs/architecture.md](architecture.md). Repo is uv-managed, **Python 3.14**, deps currently empty. We're in **planning mode** — this details the first mergeable slices and flags exactly where to start coding.
>
> **Compatibility note:** Python 3.14 is new — pin and smoke-test FastAPI/SQLModel/asyncpg/APScheduler versions in Slice 1 before building on them. If any lag 3.14, fall back to 3.12 by editing `.python-version` (low-risk, do it early).

## Slice map (from architecture build order)

| # | Slice | Mergeable outcome | Risk |
|---|-------|-------------------|------|
| **1** | **Foundation** | App boots, DB migrates, `/health` green | low |
| 2 | Fixtures sync | Real WC2026 fixtures listed | med (external API) |
| **3** | **Grading metrics (pure, test-first)** | Provably-correct metrics in isolation | low |
| 4 | Prediction core | One fixture → stored structured prediction + evidence | high (LLM) |
| 5 | Result + grade | A finished match graded end-to-end | med |
| 6 | Runs + scheduler | Idempotent scheduled/manual predict & grade | med |
| 7 | Calibration loop | calibration_version increments, injected into prompt | med |
| 8 | Read APIs | match detail / history / dashboard / calibration | low |
| 9 | Frontend | Screens wired to read APIs + admin actions | med |
| 10 | Hardening | states reconcile, caps, backups, idempotency/retry tests | low |

**Start here:** Slices **1** and **3** are independent, low-risk, and unblock everything. Do them first, in parallel if you like (1 = scaffolding, 3 = pure functions with no infra). Slice 3 first is the highest-leverage: grading correctness is the foundation of the whole "accuracy lab" — proving it in isolation, test-first, de-risks the product's core claim before any LLM or DB cost.

---

## Slice 1 — Foundation

**Restate:**
- **User-visible:** `uv run uvicorn app.main:app` boots; `GET /health` → `{"status":"ok","db":"ok"}`; `alembic upgrade head` creates all tables.
- **Layers touched:** config, logger, db, models, routes (health), migrations, docker, deps.
- **Smallest E2E path:** settings → engine → SQLModel metadata → Alembic migration → health route pings DB.
- **Main risk:** Python 3.14 dependency compatibility; async DB session wiring.

**Change set:**

```
pyproject.toml                 # add deps
docker-compose.yml             # postgres:16 service
.env.example                   # DATABASE_URL, ANTHROPIC_API_KEY, SPORTS_API_KEY, model ids, window
backend/app/__init__.py
backend/app/config/settings.py # pydantic-settings
backend/app/config/logger.py   # loguru instance
backend/app/db.py              # async engine + session dependency
backend/app/models/domain.py   # all SQLModel tables from architecture data model
backend/app/routes/health.py   # GET /health (+ db ping)
backend/app/main.py            # app factory, router mount, startup/shutdown logging
backend/alembic.ini + alembic/env.py + first migration
backend/tests/test_health.py
```

**Dependencies to add:**
`fastapi`, `uvicorn[standard]`, `sqlmodel`, `asyncpg`, `alembic`, `pydantic-settings`, `loguru`, `anthropic`, `apscheduler`, `httpx`; dev: `pytest`, `pytest-asyncio`, `ruff`, `mypy`.

**Contracts:**
- `Settings` (pydantic-settings): `database_url`, `anthropic_api_key`, `sports_api_key`, `predict_model_id="claude-opus-4-8"`, `format_model_id="claude-sonnet-4-6"`, `prediction_window_hours=24`, validated at boot (fail fast on missing keys).
- `GET /health` → `200 {status, db}`; DB unreachable → `503 {status:"degraded", db:"error"}`.
- Tables: exactly the architecture data model (Team, Player, Fixture, DataSnapshot, Prediction, Result, Grade, CalibrationProfile, Run, RunItem, Config) with the UNIQUE constraints called out there (Prediction 4-tuple, Result.fixture_id, Grade.prediction_id, Fixture.external_id).

**Logging (loguru, lifecycle):** `app.init` (config summary, redacted), `db.connected`, `app.shutdown`. Redact all keys.

**Build order within slice:** deps → settings → logger → db → models → migration → health route → main wiring → test.

**Verification / acceptance:**
- [ ] `docker compose up -d` starts Postgres.
- [ ] `uv run alembic upgrade head` creates 11 tables; `downgrade base` is clean.
- [ ] `uv run uvicorn app.main:app` boots; logs show `app.init`.
- [ ] `GET /health` → `200 {"status":"ok","db":"ok"}`; with DB down → `503`.
- [ ] `uv run pytest tests/test_health.py` passes; `ruff` + `mypy` clean.

---

## Slice 3 — Grading metrics (pure, test-first)

**Restate:**
- **User-visible (dev-facing):** a pure module that, given a prediction + actual result, returns the exact grade — no DB, no network. The provable core of the accuracy lab.
- **Layers touched:** `grading/metrics.py` + `tests/test_metrics.py` only. Zero infra.
- **Smallest E2E path:** pure functions over plain dataclasses/Pydantic DTOs.
- **Main risk:** edge-case definitions (knockout 90-min rule, own goals, penalties, scorer matching) — which is exactly why it's test-first.

**Contract (DTOs in, Grade out):**

```python
class ScorerPredDTO(BaseModel): player_name: str; team: Literal["home","away"]; likelihood: float
class PredictionDTO(BaseModel):
    home_score: int; away_score: int; scorers: list[ScorerPredDTO]
    match_confidence: float; advancing_team: Literal["home","away"] | None = None
class ActualScorerDTO(BaseModel): player_name: str; team: Literal["home","away"]; type: Literal["goal","pen","og"]
class ResultDTO(BaseModel):
    home_score_90: int; away_score_90: int
    decided_by: Literal["regular","extra_time","penalties"]
    advanced_team: Literal["home","away"] | None; scorers: list[ActualScorerDTO]
class GradeDTO(BaseModel):
    exact_hit: bool; outcome_correct: bool; goals_abs_error: int
    scorer_precision: float; scorer_recall: float
    scorer_brier: float; confidence_brier: float; advancing_correct: bool | None
```

**Pure functions (each ≤25 lines):**
- `exact_hit(pred, result)` — `(pred.home_score, pred.away_score) == (result.home_score_90, result.away_score_90)`. Always the **90-minute** line, even for ET/penalties (per PRD Open Q1 default).
- `outcome(home, away) -> Literal["home","draw","away"]`; `outcome_correct = outcome(pred) == outcome(result_90)`.
- `goals_abs_error(pred, result)` — `|pred_total - result_total_90|`.
- `scorer_sets(...)` — normalize names (casefold/strip/accents), **exclude own goals** from predicted-scorer credit, count pens as goals; returns predicted set & actual scorer set.
- `scorer_precision_recall(...)` — set precision/recall over normalized names.
- `scorer_brier(...)` — mean over predicted players of `(likelihood - did_score)²`.
- `confidence_brier(pred, result)` — derive predicted P(win for predicted side) from confidence, Brier vs realized outcome (define mapping explicitly in code + docstring).
- `advancing_correct(pred, result)` — only for knockouts (`advancing_team` set), else `None`.
- `grade(pred, result) -> GradeDTO` — orchestrates the above.

**Test plan (`test_metrics.py`) — write these FIRST, then implement to green:**
| Case | Asserts |
|------|---------|
| Exact hit 2–1 vs 2–1 | exact_hit=True, outcome_correct=True, goals_abs_error=0 |
| Right outcome wrong score 2–1 vs 3–1 | exact=False, outcome_correct=True, goals_abs_error=1 |
| Wrong outcome 2–1 vs 1–2 | exact=False, outcome_correct=False |
| Draw 1–1 vs 1–1 | outcome="draw", exact=True |
| Knockout ET: pred 1–0, result 1–1 (90') won on pens | exact graded on 90' (False), advancing_correct per advancing_team |
| Scorers: pred [Messi,Kane], actual [Messi(goal),OG] | precision/recall exclude OG, Messi counted |
| Penalty goal counts | pen-type actual scorer credited |
| Scorer Brier | hand-computed value within 1e-9 |
| Confidence Brier | hand-computed value |
| Name normalization | "Kylian Mbappé" == "kylian mbappe" |

**Verification / acceptance:**
- [ ] `uv run pytest tests/test_metrics.py` all green; every metric matches a hand-computed reference (PRD AC "Grading correctness").
- [ ] Knockout 90-min convention + void/OG/pen rules covered by a test each.
- [ ] No imports of db/network in `grading/` (enforced by keeping the module dependency-free).
- [ ] `ruff` + `mypy` clean.

This module is later imported unchanged by `GradingService` (Slice 5) — pure core, thin service wrapper.

---

## Conventions for every slice (so slices stay consistent)

- **Order:** schema → repository → service → route → validation → tests (architecture §3).
- **Boundaries:** Route → Service → Repository only; providers behind protocols; no business logic in routes/UI.
- **Async:** all-async path; never mix sync/async in one method.
- **Validation:** Pydantic at every boundary (API, provider output, LLM output).
- **Logging:** loguru lifecycle `init`/`action`/`exit` in every service & worker; redact keys; bind `run_id`/`fixture_id`.
- **Functions ≤25 lines**, single-purpose; name the pattern in a docstring.
- **Verify after each layer** with the narrowest test; one verified slice beats three half-wired files.

## Next slices (brief)

- **2 Fixtures sync:** `FixturesProvider` (sports API adapter) + `FixtureSyncService` + `GET /api/fixtures/upcoming`. Verify real WC2026 fixtures land with correct kickoff_utc.
- **4 Prediction core:** `NarrativeProvider` (Claude web search) + `claude_predict` (structured output + repair-retry) + `PredictionService`. **Consult the claude-api reference before writing the Anthropic adapters** (web-search tool + structured-output mechanism + current model IDs).
- **5 Result+grade:** `ResultsProvider` + `GradingService` (imports Slice 3 metrics) + void handling.
- **6 Runs+scheduler:** `RunService` façade + idempotent jobs + APScheduler + advisory lock + manual triggers.

---

## Recommended starting point

**Begin coding with Slice 3 (grading metrics, test-first)** — zero infra, pure logic, and it proves the product's core correctness claim before spending on LLM/API. Then **Slice 1 (foundation)** to stand up DB + app. Both are mergeable on their own.

> Say the word and I'll start writing **Slice 3** (tests first, then implementation to green), or **Slice 1** (scaffold + migration + `/health`) — whichever you want first.
