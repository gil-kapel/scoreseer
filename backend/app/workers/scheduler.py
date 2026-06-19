"""APScheduler wiring — registers predict/grade interval jobs.

Gated by SCHEDULER_ENABLED (off by default) so it never makes autonomous Claude
calls unless explicitly turned on. Jobs are idempotent (RunService dedups), so a
missed run is harmless; first fire is one interval after start.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings, logger
from app.workers.runner import run_grade, run_predict


async def _predict_job() -> None:
    logger.bind(component="scheduler").info("job.predict.start")
    await run_predict("scheduled")


async def _grade_job() -> None:
    logger.bind(component="scheduler").info("job.grade.start")
    await run_grade("scheduled")


def build_scheduler() -> AsyncIOScheduler:
    settings = get_settings()
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        _predict_job, "interval", hours=settings.predict_interval_hours,
        id="predict", max_instances=1, coalesce=True, misfire_grace_time=3600,
    )
    scheduler.add_job(
        _grade_job, "interval", hours=settings.grade_interval_hours,
        id="grade", max_instances=1, coalesce=True, misfire_grace_time=3600,
    )
    return scheduler
