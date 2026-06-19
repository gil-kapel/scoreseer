"""Admin routes — list/inspect runs and trigger predict/grade manually.

Triggering a predict run makes real Claude calls; both share the same advisory
lock as the scheduler, so a manual trigger returns 409 if a run is in progress.
"""

import asyncio
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.schemas import RunDetail, RunItemRead, RunRead
from app.repositories import RunRepository
from app.services.run_service import request_cancel
from app.workers.runner import run_backfill, run_grade, run_predict

router = APIRouter(prefix="/api/admin", tags=["admin"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# Hold references to background run tasks so they aren't garbage-collected.
_RUN_TASKS: set[asyncio.Task] = set()
_RUNNERS = {"predict": run_predict, "grade": run_grade, "backfill": run_backfill}


class TriggerRun(BaseModel):
    type: Literal["predict", "grade", "backfill"]
    count: int | None = Field(default=None, ge=1, le=104)


@router.get("/runs", response_model=list[RunRead])
async def list_runs(session: SessionDep) -> list[RunRead]:
    runs = await RunRepository(session).list_runs()
    return [RunRead.model_validate(r, from_attributes=True) for r in runs]


@router.get("/runs/{run_id}", response_model=RunDetail)
async def run_detail(run_id: uuid.UUID, session: SessionDep) -> RunDetail:
    repo = RunRepository(session)
    runs = {r.id: r for r in await repo.list_runs(limit=500)}
    run = runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    items = await repo.items(run_id)
    return RunDetail(
        run=RunRead.model_validate(run, from_attributes=True),
        items=[RunItemRead.model_validate(i, from_attributes=True) for i in items],
    )


@router.post("/runs")
async def trigger_run(body: TriggerRun) -> dict:
    """Start a run in the background and return immediately (it appears in /runs)."""
    runner = _RUNNERS[body.type]
    task = asyncio.create_task(runner("manual", cap=body.count))
    _RUN_TASKS.add(task)
    task.add_done_callback(_RUN_TASKS.discard)
    return {"status": "started", "type": body.type}


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: uuid.UUID) -> dict:
    """Ask a running run to stop after its current fixture."""
    found = request_cancel(str(run_id))
    if not found:
        raise HTTPException(status_code=404, detail="no active run with that id")
    return {"status": "cancelling", "run_id": str(run_id)}
