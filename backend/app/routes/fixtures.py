"""Fixtures routes — list upcoming + trigger a sync (admin convenience).

The scheduler (Slice 6) will call the same FixtureSyncService; for now sync is
manual via POST or the CLI to keep API/quota usage deliberate.
"""

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models.schemas import FixtureRead, SyncSummary
from app.providers.sports_api import build_fixtures_provider
from app.services import FixtureService, FixtureSyncService

router = APIRouter(prefix="/api/fixtures", tags=["fixtures"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/upcoming", response_model=list[FixtureRead])
async def upcoming(
    session: SessionDep,
    window_h: int = Query(default=24, ge=1, le=720, description="Look-ahead window in hours."),
) -> list[FixtureRead]:
    return await FixtureService(session).list_upcoming(window_h=window_h)


@router.post("/sync", response_model=SyncSummary)
async def sync(session: SessionDep) -> SyncSummary:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=30.0) as client:
        provider = build_fixtures_provider(settings, client)
        summary = await FixtureSyncService(session, provider).sync()
    return SyncSummary(**summary)
