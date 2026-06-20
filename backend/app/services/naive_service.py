"""NaiveService — persist the naive baseline (always home wins 1-0).

The accuracy floor: a constant prediction that needs no data. If the real
estimators can't beat it, they aren't earning their keep.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import logger
from app.estimators import predict_naive
from app.models import Fixture, Prediction
from app.repositories import PredictionRepository

NAIVE_MODEL_ID = "naive-v1"
NAIVE_VERSION = "naive-v1"
_KNOCKOUT_STAGES = {"r32", "r16", "qf", "sf", "final", "third_place"}


class NaiveService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PredictionRepository(session)

    def _advancing(self, fixture: Fixture):
        # Naive always backs the home side, so in a knockout the home team "advances".
        return fixture.home_team_id if fixture.stage in _KNOCKOUT_STAGES else None

    async def predict_fixture(self, fixture: Fixture) -> Prediction:
        log = logger.bind(component="NaiveService", fixture_id=str(fixture.id))
        home_goals, away_goals, confidence = predict_naive()
        advancing_id = self._advancing(fixture)
        explanation = (
            "Naive baseline: the designated home side wins 1-0 every time "
            f"(fixed P(home)={confidence:.0%}). The floor the other estimators must beat."
        )
        log.info("naive.predict score={}-{}", home_goals, away_goals)
        fields = dict(
            snapshot_id=None,
            home_score=home_goals,
            away_score=away_goals,
            scorers=[],
            match_confidence=confidence,
            advancing_team_id=advancing_id,
            explanation=explanation,
            model_id=NAIVE_MODEL_ID,
            prompt_version=NAIVE_VERSION,
            schema_version=NAIVE_VERSION,
            calibration_version=0,
            is_backfill=False,
            status="ok",
        )
        existing = await self.repo.current(
            fixture_id=fixture.id,
            prompt_version=NAIVE_VERSION,
            model_id=NAIVE_MODEL_ID,
            calibration_version=0,
        )
        if existing is not None:
            for key, value in fields.items():
                setattr(existing, key, value)
            await self.session.flush()
            return existing
        return await self.repo.create_prediction(fixture_id=fixture.id, **fields)
