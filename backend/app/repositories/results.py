"""Repositories for Result (authoritative) and Grade (append-only, one per prediction)."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models import Grade, Result
from app.providers.base import ResultDTO

_RESULT_MUTABLE = (
    "home_score_90", "away_score_90", "ft_outcome", "decided_by",
    "advanced_team_id", "scorers", "source_refs", "status",
)


class ResultRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, fixture_id: uuid.UUID) -> Result | None:
        return (
            await self.session.execute(
                select(Result).where(col(Result.fixture_id) == fixture_id)
            )
        ).scalar_one_or_none()

    async def upsert(self, *, fixture_id: uuid.UUID, values: dict) -> Result:
        existing = await self.get(fixture_id)
        if existing is not None:
            for field in _RESULT_MUTABLE:
                if field in values:
                    setattr(existing, field, values[field])
            return existing
        result = Result(fixture_id=fixture_id, **values)
        self.session.add(result)
        await self.session.flush()
        return result

    async def mark_void(self, fixture_id: uuid.UUID) -> Result:
        return await self.upsert(
            fixture_id=fixture_id,
            values={"home_score_90": 0, "away_score_90": 0, "ft_outcome": "draw", "status": "void"},
        )


class GradeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def by_prediction(self, prediction_id: uuid.UUID) -> Grade | None:
        return (
            await self.session.execute(
                select(Grade).where(col(Grade.prediction_id) == prediction_id)
            )
        ).scalar_one_or_none()

    async def by_fixture(self, fixture_id: uuid.UUID) -> Grade | None:
        return (
            await self.session.execute(
                select(Grade).where(col(Grade.fixture_id) == fixture_id)
            )
        ).scalar_one_or_none()

    async def create(self, **values) -> Grade:
        grade = Grade(**values)
        self.session.add(grade)
        await self.session.flush()
        return grade


def result_dto_to_values(dto: ResultDTO, *, home_id: uuid.UUID, away_id: uuid.UUID) -> dict:
    """Map a provider ResultDTO into Result column values."""
    if dto.home_score_90 > dto.away_score_90:
        outcome = "home"
    elif dto.home_score_90 < dto.away_score_90:
        outcome = "away"
    else:
        outcome = "draw"
    advanced_id = home_id if dto.advanced == "home" else away_id if dto.advanced == "away" else None
    return {
        "home_score_90": dto.home_score_90,
        "away_score_90": dto.away_score_90,
        "ft_outcome": outcome,
        "decided_by": dto.decided_by,
        "advanced_team_id": advanced_id,
        "scorers": [s.model_dump() for s in dto.scorers],
        "source_refs": dto.source_refs,
        "status": "final",
    }
