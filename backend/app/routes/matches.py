"""Match routes — detail view + trigger a prediction.

POST /predict makes real Claude calls (web search + structured output) and
incurs API cost, so it's a deliberate manual/admin action for now.
"""

import asyncio
import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models.schemas import MatchDetail
from app.providers.results import build_results_provider
from app.services import FixtureService, GradingService
from app.workers.runner import is_predicting, predict_one

router = APIRouter(prefix="/api/matches", tags=["matches"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Hold references to background predict tasks so they aren't garbage-collected.
_PREDICT_TASKS: set[asyncio.Task] = set()


@router.get("/{fixture_id}", response_model=MatchDetail)
async def detail(fixture_id: uuid.UUID, session: SessionDep) -> MatchDetail:
    result = await FixtureService(session).get_detail(fixture_id)
    if result is None:
        raise HTTPException(status_code=404, detail="fixture not found")
    result.predicting = is_predicting(fixture_id)
    return result


@router.post("/{fixture_id}/predict")
async def predict(fixture_id: uuid.UUID) -> dict:
    """Start a real prediction in the background (web search + LLM, ~minutes)."""
    task = asyncio.create_task(predict_one(fixture_id))
    _PREDICT_TASKS.add(task)
    task.add_done_callback(_PREDICT_TASKS.discard)
    return {"status": "started"}


@router.post("/{fixture_id}/grade")
async def grade(fixture_id: uuid.UUID, session: SessionDep) -> dict:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=30.0) as client:
        provider = build_results_provider(settings, client)
        result = await GradingService(session, provider).grade_fixture(fixture_id)
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="fixture not found")
    return result
