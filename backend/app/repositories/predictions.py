"""Repository for DataSnapshot + Prediction (append-only)."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models import DataSnapshot, Prediction
from app.providers.base import NarrativeBundle


class PredictionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_snapshot(
        self, *, fixture_id: uuid.UUID, bundle: NarrativeBundle
    ) -> DataSnapshot:
        snapshot = DataSnapshot(
            fixture_id=fixture_id,
            evidence=bundle.evidence,
            sources=bundle.sources,
            search_queries=bundle.search_queries,
            data_quality=bundle.data_quality,
            missing_signals=bundle.missing_signals,
        )
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot

    async def create_prediction(self, **values) -> Prediction:
        prediction = Prediction(**values)
        self.session.add(prediction)
        await self.session.flush()
        return prediction

    async def current(
        self, *, fixture_id: uuid.UUID, prompt_version: str, model_id: str, calibration_version: int
    ) -> Prediction | None:
        return (
            await self.session.execute(
                select(Prediction).where(
                    col(Prediction.fixture_id) == fixture_id,
                    col(Prediction.prompt_version) == prompt_version,
                    col(Prediction.model_id) == model_id,
                    col(Prediction.calibration_version) == calibration_version,
                )
            )
        ).scalar_one_or_none()

    async def latest(self, fixture_id: uuid.UUID) -> Prediction | None:
        return (
            await self.session.execute(
                select(Prediction)
                .where(col(Prediction.fixture_id) == fixture_id)
                .order_by(col(Prediction.created_at).desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def latest_ok(self, fixture_id: uuid.UUID) -> Prediction | None:
        return (
            await self.session.execute(
                select(Prediction)
                .where(col(Prediction.fixture_id) == fixture_id, col(Prediction.status) == "ok")
                .order_by(col(Prediction.created_at).desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def latest_ok_for(
        self, fixture_id: uuid.UUID, prompt_version: str, model_id: str
    ) -> Prediction | None:
        """Any OK prediction for this fixture+prompt+model (across calibration versions)."""
        return (
            await self.session.execute(
                select(Prediction)
                .where(
                    col(Prediction.fixture_id) == fixture_id,
                    col(Prediction.status) == "ok",
                    col(Prediction.prompt_version) == prompt_version,
                    col(Prediction.model_id) == model_id,
                )
                .order_by(col(Prediction.created_at).desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def get_snapshot(self, snapshot_id: uuid.UUID) -> DataSnapshot | None:
        return await self.session.get(DataSnapshot, snapshot_id)
