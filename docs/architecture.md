# Technical Plan: ScoreSeer

> Builds on [docs/prd.md](prd.md), [docs/ux-flows.md](ux-flows.md), [docs/ui-spec.md](ui-spec.md).
> Backend = Python/FastAPI. Frontend = Next.js + shadcn (separate app, talks to the API).

## Assumptions

- **Single user / owner.** No multi-tenant; auth is a single shared secret / owner session, not a user system.
- **Scale is tiny:** ~104 fixtures, a few predictions each, a handful of scheduler runs per day. This is a *correctness & reproducibility* problem, not a throughput problem — design for auditability, not scale.
- **Ground truth split (resolves PRD Open Q4):** a **structured sports-data API** (e.g. football-data.org or API-Football) is authoritative for fixtures, final scores, and goalscorers used in **grading**. **Claude web search** supplies *narrative pre-match signals only* (form notes, injuries, lineups chatter, tactical context) — never the graded ground truth. This removes the "result needs review" ambiguity from being the default path; it becomes a rare fallback when the API lags.
- **Datastore:** local **PostgreSQL via Docker Compose**. SQLModel (SQLAlchemy core + Pydantic) for models, Alembic for migrations.
- **Scheduler:** **APScheduler in the FastAPI process** with a persistent SQLAlchemy job store.
- **Claude:** **Anthropic Python SDK, direct.** Server-side web search tool for narrative fetch; tool-use / structured-output for the prediction schema. Model: default `claude-sonnet-4-6` for fetch/format, `claude-opus-4-8` available for the prediction reasoning step (configurable). *Exact tool identifiers and the structured-output mechanism to be confirmed against the claude-api reference during the dev slice.*
- Append-only: predictions/snapshots/grades are never mutated; re-runs create new versioned rows.

## Data model

Postgres. `id` = UUID PK everywhere. Timestamps UTC. JSONB for evidence/flexible payloads. Append-only tables noted.

```
Team
  id, fifa_code (e.g. "ARG"), name, group_label?, crest_url?

Player
  id, team_id → Team, name, position?, external_ref?   # squad reference for scorer validation

Fixture                                   # synced from the structured fixtures API
  id, external_id (provider fixture id, UNIQUE), stage (group|r32|r16|qf|sf|final),
  group_label?, home_team_id → Team, away_team_id → Team,
  kickoff_utc, venue?, status (scheduled|live|finished|postponed|abandoned),
  synced_at

DataSnapshot                              # APPEND-ONLY — the narrative evidence used for a prediction
  id, fixture_id → Fixture, fetched_at,
  evidence (JSONB: structured signals the model saw),
  sources (JSONB: [{title,url,accessed_at}]),     # web-search citations
  search_queries (JSONB), provider_data (JSONB),  # structured API features merged in
  data_quality (ok|low), missing_signals (JSONB)

Prediction                                # APPEND-ONLY, versioned
  id, fixture_id → Fixture, snapshot_id → DataSnapshot,
  home_score (int), away_score (int),
  scorers (JSONB: [{player_id?, player_name, team_id, likelihood 0..1}]),
  match_confidence (0..1), advancing_team_id?,           # knockouts only
  explanation (text),
  model_id, prompt_version, schema_version, calibration_version,
  status (ok|failed), failure_reason?, raw_output?,      # raw kept on failure for debugging
  created_at
  -- UNIQUE (fixture_id, prompt_version, model_id, calibration_version) → idempotent re-run guard
  -- "current" = latest created_at for a fixture among status=ok

Result                                    # from STRUCTURED API (authoritative)
  id, fixture_id → Fixture UNIQUE,
  home_score_90 (int), away_score_90 (int),
  ft_outcome (home|draw|away), decided_by (regular|extra_time|penalties),
  advanced_team_id?, scorers (JSONB: [{player_id?, player_name, team_id, minute?, type:goal|pen|og}]),
  source_refs (JSONB), status (final|void|needs_review), fetched_at

Grade                                     # APPEND-ONLY, one per (prediction, result)
  id, prediction_id → Prediction UNIQUE, fixture_id → Fixture,
  exact_hit (bool), outcome_correct (bool), goals_abs_error (int),
  scorer_precision (float), scorer_recall (float),
  scorer_brier (float), confidence_brier (float),
  advancing_correct (bool?), graded_at

CalibrationProfile                        # APPEND-ONLY, versioned snapshot of "what we've learned"
  id, version (int, monotonic), computed_at, n_graded,
  metric_aggregates (JSONB), bias_summary (text),
  prompt_snippet (text)                   # compact text injected into prediction prompt

Run                                       # one scheduler/manual invocation
  id, type (predict|grade), trigger (scheduled|manual),
  status (running|succeeded|partial|failed), started_at, finished_at?,
  params (JSONB: window, caps), totals (JSONB: counts, spend_estimate)

RunItem                                   # per-fixture outcome within a Run (isolates failures)
  id, run_id → Run, fixture_id → Fixture,
  status (succeeded|skipped|failed), detail?, duration_ms?, spend_estimate?

Config                                    # singleton row
  id, prediction_window_hours, cadence, per_run_fixture_cap, spend_cap,
  use_odds (bool), updated_at
```

**Relationships:** Team 1:N Player; Fixture N:1 Team (home/away); Fixture 1:N DataSnapshot; Fixture 1:N Prediction; Fixture 1:1 Result; Prediction 1:1 Grade; Run 1:N RunItem. CalibrationProfile is standalone, referenced by `Prediction.calibration_version`.

**State lifecycles:**
- Fixture: `scheduled → live → finished` (or `postponed/abandoned` → Result `void`).
- Prediction: created `ok`, or `failed` (visible). Newer version supersedes for display; old versions retained.
- Result: `needs_review` (rare, on API/web conflict) → `final`, or `void`.
- Run: `running → succeeded | partial | failed`.

## Key patterns (named)

- **Repository** — one per aggregate (`FixtureRepository`, `PredictionRepository`, `ResultRepository`, `GradeRepository`, `CalibrationRepository`, `RunRepository`). All DB access goes through these. Routes never touch the session directly.
- **Service (use-case)** — `PredictionService`, `GradingService`, `CalibrationService`, `FixtureSyncService`, `RunService`. Business logic lives here; call chain is **Route → Service → Repository** (max 2 hops).
- **Strategy / Provider (Ports & Adapters)** — swappable external integrations behind interfaces:
  - `FixturesProvider` / `ResultsProvider` → structured sports API adapter (authoritative truth).
  - `NarrativeProvider` → Claude web-search adapter (pre-match signals).
  - `PredictionModel` → Claude structured-output adapter (score/scorers/confidence/explanation).
  This makes PRD Open Q4 a one-adapter swap and lets tests inject fakes.
- **Command / Worker** — `PredictRunJob`, `GradeRunJob` are idempotent commands the scheduler (or a manual trigger) executes; each writes a `Run` + `RunItem`s.
- **Facade** — `RunService` is the façade the API and scheduler both call (`run_predictions(window)`, `run_grading()`), so manual and scheduled paths share one code path.

## Technical decisions

| Decision | Choice | Why | Trade-off | NOT choosing |
|----------|--------|-----|-----------|--------------|
| Backend framework | FastAPI | Async, Pydantic-native, typed contracts | Need an ASGI server (uvicorn) | Flask/Django |
| ORM / models | SQLModel + Alembic | Pydantic + SQLAlchemy in one; executable contracts | Younger than raw SQLAlchemy | Prisma, raw SQL |
| DB | Postgres (Docker) | JSONB, concurrency-safe, prod-like | Local infra vs SQLite | SQLite (still fine, but chosen Postgres) |
| Ground truth | Structured sports API | Reliable scores/scorers for grading | External dep + key/quota | Web-search-only grading |
| Narrative data | Claude web search (server tool) | Rich, current pre-match context + citations | Cost, variability | Scraping, manual |
| Prediction | Claude structured output (tool-use) | Schema-enforced score/scorers | Token cost, needs repair-retry | Free-text parsing |
| Scheduler | APScheduler + SQLAlchemy job store | In-process, persistent, idempotent | Couples to web process lifetime | Celery/cron-only (overkill/less integrated) |
| Async boundary | Fully async services; providers async; APScheduler async executor | One consistent async path | All adapters must be async | Mixing sync+async |
| Validation | Pydantic at every boundary (API + provider outputs + LLM output) | Contracts enforced, not prose | — | "validate later" |
| Frontend | Next.js + shadcn/ui + React Query | Per [ui-spec.md](ui-spec.md); RQ for server-state | Two apps to run | SSR-only / HTMX |
| Frontend↔API | Typed REST + generated client from OpenAPI | FastAPI emits OpenAPI for free | Build step | tRPC (Python n/a) |
| Auth | Single owner secret / session | Single-user product | Not extensible to multi-user (out of scope) | OAuth/users |
| Logging | **loguru** | Zero-config structured logs | — | print/logging-stdlib sprawl |
| Config/secrets | pydantic-settings + `.env` | Typed env, validated at boot | — | os.environ scatter |

## Logging strategy

- **Logger:** `loguru`, one shared instance in `app/config/logger.py`, imported everywhere. No `print`.
- **Format:** human-readable in dev; JSON sink in prod (`serialize=True`). Rotation on the file sink.
- **Levels:** `debug` (provider payloads, prompt assembly), `info` (lifecycle), `warning` (low-data prediction, result needs_review, retry), `error` (run/fixture failure, schema-validation give-up).
- **Lifecycle events (non-negotiable):** every service/worker logs `init`, `action`, `exit`. Concretely: each `Run` logs start/finish with counts+spend; each `RunItem` logs per-fixture begin/result; provider adapters log request issued + outcome.
- **Redaction:** Anthropic + sports-API keys never logged; redact at logger config. Bind `run_id`/`fixture_id` as structured context on every log line in a run.

## Folder structure

```
backend/
  app/
    main.py                 # FastAPI app factory, router mount, APScheduler startup/shutdown
    config/
      settings.py           # pydantic-settings (keys, db url, model ids, window)
      logger.py             # loguru instance
    models/                 # SQLModel tables + Pydantic schemas (contracts)
      domain.py             # Fixture, Prediction, Result, Grade, ... tables
      schemas.py            # API request/response + PredictionOutput (LLM schema)
    repositories/           # data access only
      fixtures.py  predictions.py  results.py  grades.py  calibration.py  runs.py
    services/               # use-cases (Route→Service→Repo)
      prediction_service.py  grading_service.py  calibration_service.py
      fixture_sync_service.py  run_service.py
    providers/              # Ports & Adapters (Strategy)
      base.py               # FixturesProvider, ResultsProvider, NarrativeProvider, PredictionModel protocols
      sports_api.py         # structured fixtures+results adapter
      claude_search.py      # NarrativeProvider via Anthropic web search
      claude_predict.py     # PredictionModel via Anthropic structured output (+ repair-retry)
    prompts/
      prediction_v1.md      # versioned prompt templates (prompt_version registry)
      registry.py           # prompt_version → (template, schema_version)
    workers/
      jobs.py               # PredictRunJob, GradeRunJob (idempotent commands)
      scheduler.py          # APScheduler config, job registration
    routes/
      fixtures.py  matches.py  dashboard.py  admin.py  health.py
    grading/
      metrics.py            # pure functions: exact_hit, outcome, brier, scorer P/R — unit-tested
    db.py                   # engine/session, Alembic wiring
  alembic/                  # migrations
  tests/
    test_metrics.py  test_idempotency.py  test_repair_retry.py  test_providers_fake.py
  docker-compose.yml        # postgres
  pyproject.toml            # uv-managed (repo already uses uv + .python-version)

frontend/                   # Next.js app (per ui-spec.md) — separate, consumes the API
  app/  components/  components/ui/  lib/api-client.ts  ...
```

## Boundaries and interfaces

**Provider protocols** (`providers/base.py`) — all async:

```python
class FixturesProvider(Protocol):
    async def list_fixtures(self) -> list[FixtureDTO]: ...
    async def get_result(self, external_id: str) -> ResultDTO | None: ...   # None if not final yet

class NarrativeProvider(Protocol):                       # Claude web search
    async def fetch_pre_match(self, fx: Fixture) -> NarrativeBundle: ...    # evidence + sources + data_quality

class PredictionModel(Protocol):                         # Claude structured output
    async def predict(self, ctx: PredictionContext) -> PredictionOutput: ...  # raises SchemaInvalid → repair-retry in adapter
```

**LLM output contract** (`PredictionOutput`, Pydantic — the schema the model must satisfy):
```python
class ScorerPred(BaseModel):
    player_name: str
    team: Literal["home","away"]
    likelihood: float = Field(ge=0, le=1)

class PredictionOutput(BaseModel):
    home_score: int = Field(ge=0, le=20)
    away_score: int = Field(ge=0, le=20)
    scorers: list[ScorerPred]
    match_confidence: float = Field(ge=0, le=1)
    advancing_team: Literal["home","away"] | None = None   # required iff knockout
    explanation: str = Field(min_length=20, max_length=1200)
```
The `claude_predict` adapter forces this schema (tool-use/structured output), validates, and on failure issues up to N **repair prompts**; exhaustion → `Prediction.status=failed` with `raw_output` retained (no silent drop, per PRD AC).

## API / service contracts

REST, all JSON, all reads served from the store (no LLM on page load — NFR <1s).

| Method & path | Service | Response | Errors |
|---|---|---|---|
| `GET /api/fixtures/upcoming?window_h=` | FixtureService | `[FixtureWithPrediction]` | 500 |
| `GET /api/matches/{fixture_id}` | PredictionService | `MatchDetail{fixture, prediction(+versions), result, grade, snapshot}` | 404 |
| `GET /api/history?stage&outcome&from&to` | GradingService | `[GradedMatch]` | — |
| `GET /api/dashboard/metrics` | GradingService | `{outcome_pct, exact_pct, goals_mae, scorer_recall, conf_brier, trend[]}` | — |
| `GET /api/dashboard/calibration` | CalibrationService | `{reliability_curve[], first_half_brier, second_half_brier, bias_summary, versions[]}` | — |
| `GET /api/admin/runs` / `GET /api/admin/runs/{id}` | RunService | `[Run]` / `RunDetail{run, items[]}` | 404 |
| `POST /api/admin/runs` `{type: predict\|grade}` | RunService | `202 {run_id}` | 409 if a run of that type is in progress |
| `POST /api/matches/{id}/predict` | PredictionService | `202 {run_id}` (confirm cost client-side) | 409 if running |
| `POST /api/matches/{id}/grade` | GradingService | `202 {run_id}` | 409 |
| `POST /api/matches/{id}/void` `{void: bool}` | GradingService | `200 {result}` | 404 |
| `GET/PUT /api/admin/config` | (Config) | `Config` | 422 invalid |

Boundary validation: Pydantic request models; config rules match [ux-flows.md](ux-flows.md) (window 1–72, cap ≥1, spend ≥0).

### Scheduler idempotency & isolation (the crux)

- **No overlap:** APScheduler `max_instances=1`, `coalesce=True`, `misfire_grace_time` set. `RunService` also takes a Postgres **advisory lock** per run-type so a manual trigger can't race the scheduled one → returns `409` if already held.
- **Idempotent prediction:** the `Prediction` UNIQUE `(fixture_id, prompt_version, model_id, calibration_version)` means re-running the same fixture with unchanged versions is a no-op `skipped` RunItem. A new prediction is created only when a version changes or the owner forces a re-run (force bypasses the skip and writes a new row — append-only, old kept).
- **Idempotent grading:** `Grade` UNIQUE on `prediction_id`; a fixture already graded → `skipped`. Grading only proceeds when `ResultsProvider.get_result` returns a `final` result.
- **Failure isolation:** each fixture handled in its own transaction inside the run; an exception writes a `failed` RunItem and continues → Run ends `partial`. Persistent job store means a process restart mid-run is recoverable (re-run is safe by idempotency).
- **Selection:** predict run picks fixtures with `kickoff_utc` within `window_h`, `status=scheduled`, and no current-version prediction; grade run picks `finished` fixtures that have a `Prediction` but no `Grade`.

### Prompt & schema versioning

`prompt_version` (e.g. `pred-v1`) and `schema_version` (e.g. `out-v1`) are stored on every Prediction alongside `model_id` and `calibration_version`. A registry (`prompts/registry.py`) resolves a `prompt_version` to its template + expected schema. Changing the prompt or schema bumps the version → new predictions are distinguishable and old ones remain reproducible. CalibrationProfile.`version` is injected as `calibration_version`, so you can always reconstruct exactly which "learned biases" shaped a given prediction.

## Risks and trade-offs

- **Sports API coverage/quota for WC2026** (high) — verify the chosen provider has WC2026 fixtures, finals incl. ET/pens distinction, and scorer data within free/paid tier. Mitigation: `ResultsProvider` interface + `needs_review` fallback to web search if the API lags.
- **APScheduler tied to web-process lifetime** (medium) — if the FastAPI process is down at kickoff window, runs are missed. Mitigation: persistent job store + `misfire_grace_time` + manual trigger; CLI entrypoint as a cron fallback is a small add later.
- **LLM structured-output drift / cost** (medium) — repair-retry caps spend; `spend_cap` in Config; log spend per RunItem.
- **Calibration signal weak over ~104 matches** (medium, from PRD) — `CalibrationProfile` is isolated and versioned so the loop can be evaluated and, if flat, swapped for the deferred Poisson model without schema change.
- **Two-app dev friction** (low) — FastAPI OpenAPI → generated typed client keeps the contract honest.

## Build order (vertical slices)

1. **Foundation:** Docker Postgres, SQLModel models + Alembic migration, loguru, settings, FastAPI skeleton + `/health`. *Demo: tables exist, app boots.*
2. **Fixtures sync:** `FixturesProvider` (sports API) + `FixtureSyncService` + `GET /api/fixtures/upcoming`. *Demo: real WC2026 fixtures listed.*
3. **Grading metrics (pure, test-first):** `grading/metrics.py` + `test_metrics.py` against hand-computed references. *Demo: metrics provably correct in isolation — lowest-risk, highest-leverage first.*
4. **Prediction core:** `NarrativeProvider` (Claude search) + `claude_predict` with schema + repair-retry + `PredictionService` writing DataSnapshot+Prediction. *Demo: one fixture → stored structured prediction with evidence.*
5. **Result + grade:** `ResultsProvider` + `GradingService` → Result + Grade; void handling. *Demo: a finished match graded end-to-end.*
6. **Runs + scheduler:** `RunService` façade, `PredictRunJob`/`GradeRunJob`, APScheduler wiring, idempotency/advisory-lock, `POST /api/admin/runs`, manual triggers. *Demo: scheduled + manual predict/grade with Run/RunItem records.*
7. **Calibration loop:** `CalibrationService` computes profile from rolling Grades, inject `prompt_snippet` into prediction context. *Demo: calibration_version increments, prompt log shows it.*
8. **Read APIs for UI:** match detail, history, dashboard metrics, calibration endpoints.
9. **Frontend:** Next.js shell per [ui-spec.md](ui-spec.md), wire the screens to the read APIs + admin actions.
10. **Hardening:** error/empty states reconciliation, spend caps, backups, tests for idempotency + repair-retry.

Each slice is independently mergeable; slices 1–5 deliver the PRD-critical "predict → store → grade" core before any UI.

---

*Next:* `/dev-composer-agent` to implement slice 1 (foundation) and slice 3 (grading metrics, test-first) as the first mergeable units. The dev step should consult the **claude-api** reference before writing the Anthropic web-search and structured-output adapters (slices 4–5).
