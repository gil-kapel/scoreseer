"""FastAPI application factory + lifecycle.

Mounts routers, logs init/shutdown, disposes the DB engine, and (when
SCHEDULER_ENABLED) starts the APScheduler predict/grade jobs.
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from app.auth import require_api_key
from app.config import configure_logging, get_settings, logger
from app.db import dispose_engine
from app.routes import admin, dashboard, fixtures, health, matches
from app.workers.scheduler import build_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(level=settings.log_level, json_logs=settings.is_production)
    logger.bind(component="app").info("app.init: {}", settings.redacted())

    scheduler = None
    if settings.scheduler_enabled:
        scheduler = build_scheduler()
        scheduler.start()
        logger.bind(component="app").info(
            "scheduler.started predict_every={}h grade_every={}h",
            settings.predict_interval_hours, settings.grade_interval_hours,
        )
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)
    await dispose_engine()
    logger.bind(component="app").info("app.shutdown: engine disposed")


def create_app() -> FastAPI:
    app = FastAPI(title="ScoreSeer API", version="0.1.0", lifespan=lifespan)
    # /health stays open for platform probes; everything else requires the API key
    # when one is configured (no-op when api_token is empty — local dev/tests).
    protected = [Depends(require_api_key)]
    app.include_router(health.router)
    app.include_router(fixtures.router, dependencies=protected)
    app.include_router(matches.router, dependencies=protected)
    app.include_router(admin.router, dependencies=protected)
    app.include_router(dashboard.router, dependencies=protected)
    return app


app = create_app()
