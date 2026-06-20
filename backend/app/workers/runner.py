"""Wire real providers around RunService — shared by scheduler, routes, and CLI."""

import time
import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import delete, select
from sqlmodel import col

from app.config import get_settings, logger
from app.db import get_sessionmaker
from app.estimators import BASELINE_MODEL_IDS
from app.models import Fixture, Grade, Prediction, Run
from app.providers.claude_batch import ClaudeBatchPredictor
from app.providers.claude_factory import claude_adapters
from app.providers.results import build_results_provider
from app.providers.sports_api import build_fixtures_provider
from app.services import (
    BatchBackfillService,
    CalibrationService,
    EloService,
    FixtureSyncService,
    NaiveService,
    PoissonService,
    PredictionService,
    RunService,
)

# Fixtures with an in-flight per-match predict — surfaced to the UI so it can show
# a "Predicting…" indicator that survives a page refresh (in-process; resets on restart).
_predicting: set[uuid.UUID] = set()


def is_predicting(fixture_id: uuid.UUID) -> bool:
    return fixture_id in _predicting


def predicting_ids() -> set[uuid.UUID]:
    return set(_predicting)


def _cap(cap: int | None) -> int:
    return cap if cap and cap > 0 else get_settings().per_run_fixture_cap


async def predict_one(fixture_id: uuid.UUID) -> dict:
    """Predict a single fixture (used by the per-match 'Predict this match' button)."""
    log = logger.bind(component="predict_one", fixture_id=str(fixture_id))
    _predicting.add(fixture_id)
    started = time.monotonic()
    log.info("predict_one.start — web search + LLM, this can take a few minutes")
    settings = get_settings()
    try:
        async with claude_adapters(settings) as (narrative, model):
            async with get_sessionmaker()() as session:
                result = await PredictionService(session, narrative, model).predict_fixture(
                    fixture_id, model_id=settings.predict_model_id
                )
        log.info(
            "predict_one.done status={} score={} duration_ms={}",
            result.get("status"), result.get("score"), round((time.monotonic() - started) * 1000),
        )
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "predict_one.error duration_ms={} error={}",
            round((time.monotonic() - started) * 1000), str(exc)[:300],
        )
        return {"status": "error", "detail": str(exc)[:300]}
    finally:
        _predicting.discard(fixture_id)


async def run_predict(trigger: str, *, cap: int | None = None) -> dict:
    settings = get_settings()
    async with claude_adapters(settings) as (narrative, model):
        return await RunService(get_sessionmaker()).run_predictions(
            trigger=trigger,
            window_h=settings.prediction_window_hours,
            cap=_cap(cap),
            narrative=narrative,
            model=model,
            model_id=settings.predict_model_id,
        )


async def run_sync(trigger: str, *, cap: int | None = None) -> dict:
    """Sync fixture statuses from the (free) sports API, then grade newly-finished
    matches. No Claude. Records a Run so it shows in the admin table."""
    log = logger.bind(component="run_sync")
    sm = get_sessionmaker()
    async with sm() as session:
        run = Run(type="sync", trigger=trigger, status="running", params={})
        session.add(run)
        await session.commit()
        run_id = run.id

    status = "succeeded"
    summary: dict = {}
    try:
        settings = get_settings()
        async with httpx.AsyncClient(timeout=30.0) as client:
            provider = build_fixtures_provider(settings, client)
            async with sm() as session:
                summary = await FixtureSyncService(session, provider).sync()
    except Exception as exc:  # noqa: BLE001 — record failure on the run row
        log.warning("sync.error: {}", exc)
        summary = {"status": "error", "detail": str(exc)[:300]}
        status = "failed"

    async with sm() as session:
        finished = await session.get(Run, run_id)
        if finished is not None:
            finished.status = status
            finished.finished_at = datetime.now(UTC)
            finished.totals = summary
            await session.commit()

    if status != "failed":
        await run_grade(trigger)  # grade matches that just turned finished
    return summary


async def run_grade(trigger: str, *, cap: int | None = None) -> dict:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=30.0) as client:
        provider = build_results_provider(settings, client)
        return await RunService(get_sessionmaker()).run_grading(
            trigger=trigger, cap=_cap(cap), results=provider
        )


async def run_backfill(trigger: str, *, cap: int | None = None) -> dict:
    settings = get_settings()
    async with claude_adapters(settings) as (narrative, model):
        async with httpx.AsyncClient(timeout=30.0) as client:
            results = build_results_provider(settings, client)
            return await RunService(get_sessionmaker()).run_backfill(
                trigger=trigger,
                cap=_cap(cap),
                narrative=narrative,
                model=model,
                model_id=settings.predict_model_id,
                results=results,
            )


async def run_baselines(trigger: str, *, cap: int | None = None) -> dict:
    """Regenerate every free statistical baseline (Poisson · Elo · Naive) for every
    fixture (upsert + regrade + calibrate).

    No Claude. Records a Run row, then grades the refreshed predictions and recomputes
    calibration. Safe to re-run after a model change.
    """
    log = logger.bind(component="run_baselines")
    sm = get_sessionmaker()
    async with sm() as session:
        run = Run(type="baselines", trigger=trigger, status="running", params={"cap": cap})
        session.add(run)
        await session.commit()
        run_id = run.id

    upserted = 0
    status = "succeeded"
    try:
        async with sm() as session:
            stmt = select(Fixture).order_by(col(Fixture.kickoff_utc))
            if cap:
                stmt = stmt.limit(cap)
            fixtures = (await session.execute(stmt)).scalars().all()
            for fixture in fixtures:
                await PoissonService(session).predict_fixture(fixture)  # each upserts in place
                await EloService(session).predict_fixture(fixture)
                await NaiveService(session).predict_fixture(fixture)
                upserted += 1
            # Drop stale baseline grades (scored the old scoreline) so they re-grade.
            await session.execute(
                delete(Grade).where(
                    col(Grade.prediction_id).in_(
                        select(col(Prediction.id)).where(
                            col(Prediction.model_id).in_(BASELINE_MODEL_IDS)
                        )
                    )
                )
            )
            await session.commit()
        await run_grade(trigger, cap=500)  # grade the refreshed baselines (+ any ungraded)
        async with sm() as session:
            profile = await CalibrationService(session).recompute()
            if profile is not None:
                await session.commit()
    except Exception as exc:  # noqa: BLE001 — record failure on the run row
        log.warning("baselines.error: {}", exc)
        status = "failed"

    async with sm() as session:
        finished = await session.get(Run, run_id)
        if finished is not None:
            finished.status = status
            finished.finished_at = datetime.now(UTC)
            finished.totals = {"succeeded": upserted, "skipped": 0, "failed": 0}
            await session.commit()
    log.info("run_baselines.done fixtures={} status={}", upserted, status)
    return {"status": status, "upserted": upserted}


async def _run_batch(trigger: str, cap: int | None, *, forward: bool, run_type: str) -> dict:
    """Shared driver for batch backfill (finished) + batch predict (upcoming).

    50% off, no web search. Records a Run row; backfill is graded after (forward
    predictions grade later, once the matches are played). Long batches are better
    from the CLI — a free-tier backend can spin down mid-poll and kill the task.
    """
    log = logger.bind(component=run_type)
    sm = get_sessionmaker()
    async with sm() as session:
        run = Run(type=run_type, trigger=trigger, status="running", params={"cap": cap})
        session.add(run)
        await session.commit()
        run_id = run.id

    predictor = ClaudeBatchPredictor(get_settings())
    status = "succeeded"
    try:
        async with sm() as session:
            summary = await BatchBackfillService(session, predictor).run(cap=cap, forward=forward)
        if not summary.get("stored"):
            status = "partial"
    except Exception as exc:  # noqa: BLE001 — surface failure on the run row, don't crash
        log.warning("batch.error: {}", exc)
        summary = {"status": "error", "detail": str(exc)[:300]}
        status = "failed"

    succeeded = int(summary.get("succeeded", 0))
    stored = int(summary.get("stored", 0))
    async with sm() as session:
        finished = await session.get(Run, run_id)
        if finished is not None:
            finished.status = status
            finished.finished_at = datetime.now(UTC)
            finished.totals = {
                "succeeded": succeeded,
                "skipped": 0,
                "failed": stored - succeeded,
                **summary,
            }
            await session.commit()

    if status != "failed" and not forward:
        await run_grade(trigger)  # forward predictions are graded later, when played
    return summary


async def run_batch_backfill(trigger: str, *, cap: int | None = None) -> dict:
    """LLM predictions on PAST matches via one Anthropic batch (labeled, then graded)."""
    return await _run_batch(trigger, cap, forward=False, run_type="batch_backfill")


async def run_batch_predict(trigger: str, *, cap: int | None = None) -> dict:
    """Honest forward LLM predictions on the next UPCOMING matches (cheap, no web search)."""
    return await _run_batch(trigger, cap, forward=True, run_type="batch_predict")
