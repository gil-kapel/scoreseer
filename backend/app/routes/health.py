"""Health route — liveness + DB connectivity check."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import logger
from app.db import get_session

router = APIRouter(tags=["health"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/health")
async def health(response: Response, session: SessionDep) -> dict[str, str]:
    """Return ok when the app and database are reachable, 503 otherwise."""
    try:
        await session.execute(text("SELECT 1"))
        return {"status": "ok", "db": "ok"}
    except Exception as exc:  # noqa: BLE001 — health must never raise
        logger.bind(component="health").warning("health.db_unreachable: {}", exc)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "db": "error"}
