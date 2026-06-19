"""RunService — façade for scheduled/manual predict & grade runs.

Both the scheduler and the admin endpoints call this. Guarantees:
- No overlap: a Postgres session-level advisory lock per run type (a manual
  trigger can't race the scheduled one) → returns {"status": "busy"} if held.
- Failure isolation: each fixture is processed in its OWN session, so one
  fixture's error can't poison the others; the failure is recorded as a RunItem.
- Idempotent: selection excludes already-predicted / already-graded fixtures, and
  the underlying services skip duplicates cheaply (no Claude call on skip).
"""

import asyncio
from collections.abc import Awaitable, Callable

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker
from sqlmodel import col

from app.config import logger
from app.db import get_engine
from app.models import Grade
from app.prompts import PROMPT_VERSION
from app.providers.base import NarrativeProvider, PredictionModel, ResultsProvider
from app.repositories import RunRepository
from app.services.calibration_service import CalibrationService
from app.services.grading_service import GradingService
from app.services.prediction_service import PredictionService

_PREDICT_LOCK = 911001
_GRADE_LOCK = 911002

# Service status -> RunItem status.
_ITEM_STATUS = {"ok": "succeeded", "skipped": "skipped", "graded": "succeeded"}

# In-process cooperative cancellation: run_id -> Event. The run loop checks it
# between fixtures; the admin cancel endpoint (same process) sets it.
_cancel_events: dict[str, asyncio.Event] = {}


def request_cancel(run_id: str) -> bool:
    """Signal a running run to stop after its current fixture. Returns True if found."""
    event = _cancel_events.get(run_id)
    if event is None:
        return False
    event.set()
    return True


class RunService:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    async def run_predictions(
        self, *, trigger: str, window_h: int, cap: int,
        narrative: NarrativeProvider, model: PredictionModel, model_id: str,
    ) -> dict:
        async def select(repo: RunRepository) -> list:
            return await repo.eligible_for_prediction(
                window_h=window_h, model_id=model_id, prompt_version=PROMPT_VERSION, cap=cap,
            )

        async def process(fixture_id) -> tuple[str, str | None]:
            async with self._sm() as s:
                try:
                    res = await PredictionService(s, narrative, model).predict_fixture(
                        fixture_id, model_id=model_id
                    )
                    return res["status"], res.get("failure_reason")
                except Exception as exc:  # noqa: BLE001 — isolate per-fixture failure
                    await s.rollback()
                    return "error", str(exc)[:300]

        return await self._run("predict", _PREDICT_LOCK, trigger,
                               {"window_h": window_h, "cap": cap}, select, process)

    async def run_grading(
        self, *, trigger: str, cap: int, results: ResultsProvider
    ) -> dict:
        async def select(repo: RunRepository) -> list:
            return await repo.eligible_for_grading(cap=cap)

        async def process(fixture_id) -> tuple[str, str | None]:
            async with self._sm() as s:
                try:
                    res = await GradingService(s, results).grade_fixture(fixture_id)
                    return res["status"], None
                except Exception as exc:  # noqa: BLE001
                    await s.rollback()
                    return "error", str(exc)[:300]

        result = await self._run("grade", _GRADE_LOCK, trigger, {"cap": cap}, select, process)
        if result.get("succeeded"):
            await self._recompute_calibration()
        return result

    async def run_backfill(
        self, *, trigger: str, cap: int, narrative: NarrativeProvider,
        model: PredictionModel, model_id: str, results: ResultsProvider,
    ) -> dict:
        """Real LLM predictions on past matches (force-overwrite, flagged is_backfill)."""
        async def select(repo: RunRepository) -> list:
            return await repo.eligible_for_backfill(cap=cap)

        async def process(fixture_id) -> tuple[str, str | None]:
            async with self._sm() as s:
                try:
                    await PredictionService(s, narrative, model).predict_fixture(
                        fixture_id, model_id=model_id, is_backfill=True, force=True
                    )
                except Exception as exc:  # noqa: BLE001 — provider error; seed left intact
                    await s.rollback()
                    return "error", str(exc)[:300]
            async with self._sm() as s:  # re-grade against the new backfill prediction
                await s.execute(delete(Grade).where(col(Grade.fixture_id) == fixture_id))
                await s.commit()
            async with self._sm() as s:
                try:
                    res = await GradingService(s, results).grade_fixture(fixture_id)
                    return res["status"], None
                except Exception as exc:  # noqa: BLE001
                    await s.rollback()
                    return "error", str(exc)[:300]

        return await self._run("backfill", _PREDICT_LOCK, trigger, {"cap": cap}, select, process)

    async def _recompute_calibration(self) -> None:
        async with self._sm() as s:
            profile = await CalibrationService(s).recompute()
            if profile is not None:
                await s.commit()

    async def _run(
        self, type_: str, lock_key: int, trigger: str, params: dict,
        select: Callable[[RunRepository], Awaitable[list]],
        process: Callable[[object], Awaitable[tuple[str, str | None]]],
    ) -> dict:
        log = logger.bind(component="RunService", run_type=type_)
        # The session-level advisory lock lives on a dedicated connection for the
        # whole run; bookkeeping commits would otherwise return the session's
        # connection to the pool and silently drop the lock.
        async with get_engine().connect() as lock_conn:
            if not await _try_lock(lock_conn, lock_key):
                log.warning("run.busy")
                return {"status": "busy"}
            try:
                return await self._execute(type_, trigger, params, select, process, log)
            finally:
                await _unlock(lock_conn, lock_key)

    async def _execute(self, type_, trigger, params, select, process, log) -> dict:
        async with self._sm() as rs:
            repo = RunRepository(rs)
            run = await repo.create_run(type_=type_, trigger=trigger, params=params)
            await rs.commit()
            cancel = asyncio.Event()
            _cancel_events[str(run.id)] = cancel
            try:
                fixtures = await select(repo)
                totals = {"succeeded": 0, "skipped": 0, "failed": 0}
                cancelled = False
                for fixture_id in fixtures:
                    if cancel.is_set():
                        cancelled = True
                        break
                    status, detail = await process(fixture_id)
                    item_status = _ITEM_STATUS.get(status, "failed")
                    totals[item_status] += 1
                    await repo.add_item(
                        run_id=run.id, fixture_id=fixture_id, status=item_status, detail=detail
                    )
                    await rs.commit()
                run_status = "cancelled" if cancelled else _run_status(totals)
                await repo.finalize(run, status=run_status, totals=totals)
                await rs.commit()
                log.info("run.done id={} status={} totals={}", run.id, run_status, totals)
                return {"status": run_status, "run_id": str(run.id), **totals}
            finally:
                _cancel_events.pop(str(run.id), None)


def _run_status(totals: dict) -> str:
    if totals["failed"] and (totals["succeeded"] or totals["skipped"]):
        return "partial"
    if totals["failed"]:
        return "failed"
    return "succeeded"


async def _try_lock(conn: AsyncConnection, key: int) -> bool:
    result = await conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key})
    return bool(result.scalar_one())


async def _unlock(conn: AsyncConnection, key: int) -> None:
    await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
    await conn.commit()
