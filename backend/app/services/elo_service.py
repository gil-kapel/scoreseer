"""EloService — persist Elo-model predictions (a free, non-LLM estimator).

Builds ratings from results that kicked off *before* the target fixture, in
chronological order ("as-of"), so a prediction for a finished match never sees
its own result — an honest, gradeable forward-equivalent like Poisson.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.config import logger
from app.estimators import MatchResult, estimate_ratings, predict_elo
from app.estimators.elo_seeds import DEFAULT_SEED, ELO_SEEDS
from app.models import Fixture, Prediction, Result, Team
from app.repositories import PredictionRepository

ELO_MODEL_ID = "elo-v1"
ELO_VERSION = "elo-v1"
_KNOCKOUT_STAGES = {"r32", "r16", "qf", "sf", "final", "third_place"}


class EloService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PredictionRepository(session)

    async def predict_fixture(self, fixture: Fixture) -> Prediction:
        log = logger.bind(component="EloService", fixture_id=str(fixture.id))
        results = await self._prior_results(fixture.kickoff_utc)
        ratings = estimate_ratings(results, initial=await self._seed_ratings())
        pred = predict_elo(
            str(fixture.home_team_id),
            str(fixture.away_team_id),
            ratings,
            n_matches=len(results),
        )
        advancing_id = self._advancing(fixture, pred.outcome)
        explanation = (
            f"Elo over {pred.n_matches} prior result(s): "
            f"{pred.home_rating:.0f} vs {pred.away_rating:.0f}. "
            f"Most-likely {pred.home_goals}–{pred.away_goals} "
            f"(P({pred.outcome})={pred.confidence:.0%}, "
            f"home/draw/away = {pred.p_home:.0%}/{pred.p_draw:.0%}/{pred.p_away:.0%})."
        )
        log.info("elo.predict score={}-{}", pred.home_goals, pred.away_goals)
        return await self._upsert(
            fixture,
            home_score=pred.home_goals,
            away_score=pred.away_goals,
            confidence=round(pred.confidence, 3),
            advancing_id=advancing_id,
            explanation=explanation,
        )

    def _advancing(self, fixture: Fixture, outcome: str):
        if fixture.stage not in _KNOCKOUT_STAGES or outcome == "draw":
            return None
        return fixture.home_team_id if outcome == "home" else fixture.away_team_id

    async def _upsert(
        self, fixture: Fixture, *, home_score, away_score, confidence, advancing_id, explanation
    ) -> Prediction:
        fields = dict(
            snapshot_id=None,
            home_score=home_score,
            away_score=away_score,
            scorers=[],
            match_confidence=confidence,
            advancing_team_id=advancing_id,
            explanation=explanation,
            model_id=ELO_MODEL_ID,
            prompt_version=ELO_VERSION,
            schema_version=ELO_VERSION,
            calibration_version=0,
            is_backfill=False,
            status="ok",
        )
        existing = await self.repo.current(
            fixture_id=fixture.id,
            prompt_version=ELO_VERSION,
            model_id=ELO_MODEL_ID,
            calibration_version=0,
        )
        if existing is not None:
            for key, value in fields.items():
                setattr(existing, key, value)
            await self.session.flush()
            return existing
        return await self.repo.create_prediction(fixture_id=fixture.id, **fields)

    async def _seed_ratings(self) -> dict[str, float]:
        """Pre-tournament strength per team (team_id -> Elo) so the model isn't cold."""
        teams = (await self.session.execute(select(Team))).scalars().all()
        return {str(t.id): ELO_SEEDS.get(t.fifa_code, DEFAULT_SEED) for t in teams}

    async def _prior_results(self, before: datetime) -> list[MatchResult]:
        rows = (
            await self.session.execute(
                select(Result, Fixture)
                .join(Fixture, col(Fixture.id) == col(Result.fixture_id))
                .where(col(Fixture.kickoff_utc) < before, col(Result.status) == "final")
                .order_by(col(Fixture.kickoff_utc))  # Elo updates are sequential
            )
        ).all()
        return [
            MatchResult(
                home_id=str(fixture.home_team_id),
                away_id=str(fixture.away_team_id),
                home_goals=result.home_score_90,
                away_goals=result.away_score_90,
            )
            for result, fixture in rows
        ]
