"""Wire real providers around RunService — shared by scheduler, routes, and CLI."""

import time
import uuid
from datetime import UTC, datetime

import httpx

from app.config import get_settings, logger
from app.db import get_sessionmaker
from app.models import Run
from app.providers.claude_batch import ClaudeBatchPredictor
from app.providers.claude_factory import claude_adapters
from app.providers.results import build_results_provider
from app.services import BatchBackfillService, PredictionService, RunService

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


async def run_batch_backfill(trigger: str, *, cap: int | None = None) -> dict:
    """LLM predictions on past matches via one Anthropic batch (50% off, no web search).

    Records a Run row so it shows in the admin table, then grades the new
    predictions. Long batches are better run from the CLI — a free-tier backend can
    spin down mid-poll and kill the background task.
    """
    log = logger.bind(component="run_batch_backfill")
    sm = get_sessionmaker()
    async with sm() as session:
        run = Run(type="batch_backfill", trigger=trigger, status="running", params={"cap": cap})
        session.add(run)
        await session.commit()
        run_id = run.id

    predictor = ClaudeBatchPredictor(get_settings())
    status = "succeeded"
    try:
        async with sm() as session:
            summary = await BatchBackfillService(session, predictor).run(cap=cap)
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

    if status != "failed":
        await run_grade(trigger)
    return summary
