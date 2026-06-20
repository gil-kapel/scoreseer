"""Repository for CalibrationProfile + the graded-history join it's computed from."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.estimators import BASELINE_MODEL_IDS
from app.models import CalibrationProfile, Grade, Prediction, Result


class CalibrationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def latest(self) -> CalibrationProfile | None:
        return (
            await self.session.execute(
                select(CalibrationProfile).order_by(col(CalibrationProfile.version).desc()).limit(1)
            )
        ).scalar_one_or_none()

    async def list_all(self) -> list[CalibrationProfile]:
        return list(
            (
                await self.session.execute(
                    select(CalibrationProfile).order_by(col(CalibrationProfile.version).desc())
                )
            )
            .scalars()
            .all()
        )

    async def next_version(self) -> int:
        current = (
            await self.session.execute(select(func.max(col(CalibrationProfile.version))))
        ).scalar_one()
        return (current or 0) + 1

    async def create(self, **values) -> CalibrationProfile:
        profile = CalibrationProfile(**values)
        self.session.add(profile)
        await self.session.flush()
        return profile

    async def load_graded(self) -> list[tuple[Prediction, Result, Grade]]:
        """Every LLM (prediction, final result, grade) triple — the calibration evidence.

        Calibration tunes the LLM prompt, so backfill (hindsight) predictions AND the
        statistical baselines (Poisson / Elo / Naive) are excluded — only real LLM
        predictions may feed the loop.
        """
        rows = (
            await self.session.execute(
                select(Prediction, Result, Grade)
                .join(Grade, col(Grade.prediction_id) == col(Prediction.id))
                .join(Result, col(Result.fixture_id) == col(Grade.fixture_id))
                .where(
                    col(Result.status) == "final",
                    col(Prediction.is_backfill).is_(False),
                    col(Prediction.model_id).not_in(BASELINE_MODEL_IDS),
                )
            )
        ).all()
        return [(row[0], row[1], row[2]) for row in rows]
