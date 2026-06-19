"""Dashboard + history read APIs (no LLM, served from stored grades)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.schemas import CalibrationView, DashboardMetrics, HistoryRow
from app.services import DashboardService

router = APIRouter(prefix="/api", tags=["dashboard"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/dashboard/metrics", response_model=DashboardMetrics)
async def metrics(session: SessionDep) -> DashboardMetrics:
    return await DashboardService(session).metrics()


@router.get("/dashboard/calibration", response_model=CalibrationView)
async def calibration(session: SessionDep) -> CalibrationView:
    return await DashboardService(session).calibration()


@router.get("/history", response_model=list[HistoryRow])
async def history(
    session: SessionDep,
    stage: str | None = None,
    outcome: Literal["hit", "miss"] | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[HistoryRow]:
    return await DashboardService(session).history(stage=stage, outcome=outcome, limit=limit)
