"""APScheduler wiring — FREE jobs only (sync + grade), so SCHEDULER_ENABLED can be
turned on without ever spending Claude.

The lab self-updates: sync pulls new fixture statuses + the grade job scores
newly-finished matches (Poisson + LLM each) and recomputes calibration — all from
the free sports API, no LLM calls. Predictions stay manual (the paid step is always
a deliberate button press). Jobs are idempotent, so a missed run is harmless.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings, logger
from app.workers.runner import run_grade, run_sync


async def _sync_job() -> None:
    logger.bind(component="scheduler").info("job.sync.start")
    await run_sync("scheduled")


async def _grade_job() -> None:
    logger.bind(component="scheduler").info("job.grade.start")
    await run_grade("scheduled")  # also recomputes calibration


def build_scheduler() -> AsyncIOScheduler:
    settings = get_settings()
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        _sync_job, "interval", hours=settings.grade_interval_hours,
        id="sync", max_instances=1, coalesce=True, misfire_grace_time=3600,
    )
    scheduler.add_job(
        _grade_job, "interval", hours=settings.grade_interval_hours,
        id="grade", max_instances=1, coalesce=True, misfire_grace_time=3600,
    )
    return scheduler
