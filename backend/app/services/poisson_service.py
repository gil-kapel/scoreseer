"""PoissonService — persist Poisson-model predictions (a free, non-LLM estimator).

Estimates team strengths from results that kicked off *before* the target
fixture ("as-of"), so a prediction for a finished match never sees its own
result. That makes it an honest forward-equivalent prediction: unlike the LLM
backfill it can be graded and counted in headline accuracy without poisoning.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.config import logger
from app.estimators import MatchResult, estimate_strengths, predict_score
from app.models import Fixture, Prediction, Result
from app.repositories import PredictionRepository

POISSON_MODEL_ID = "poisson-v1"
POISSON_VERSION = "poisson-v1"
_KNOCKOUT_STAGES = {"r32", "r16", "qf", "sf", "final", "third_place"}


class PoissonService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PredictionRepository(session)

    async def predict_fixture(self, fixture: Fixture) -> Prediction:
        log = logger.bind(component="PoissonService", fixture_id=str(fixture.id))
        results = await self._prior_results(fixture.kickoff_utc)
        strengths, league_avg = estimate_strengths(results)
        pred = predict_score(
            str(fixture.home_team_id),
            str(fixture.away_team_id),
            strengths,
            league_avg,
            n_matches=len(results),
        )
        advancing_id = self._advancing(fixture, pred.outcome)
        explanation = (
            f"Poisson model over {pred.n_matches} prior result(s): "
            f"expected {pred.lambda_home:.2f}–{pred.lambda_away:.2f} goals. "
            f"Most-likely scoreline {pred.home_goals}–{pred.away_goals} "
            f"(P({pred.outcome})={pred.confidence:.0%}, "
            f"home/draw/away = {pred.p_home:.0%}/{pred.p_draw:.0%}/{pred.p_away:.0%})."
        )
        log.info("poisson.predict score={}-{}", pred.home_goals, pred.away_goals)
        return await self.repo.create_prediction(
            fixture_id=fixture.id,
            snapshot_id=None,
            home_score=pred.home_goals,
            away_score=pred.away_goals,
            scorers=[],  # Poisson is a score model — no player-level prediction
            match_confidence=round(pred.confidence, 3),
            advancing_team_id=advancing_id,
            explanation=explanation,
            model_id=POISSON_MODEL_ID,
            prompt_version=POISSON_VERSION,
            schema_version=POISSON_VERSION,
            calibration_version=0,
            is_backfill=False,
            status="ok",
        )

    def _advancing(self, fixture: Fixture, outcome: str):
        if fixture.stage not in _KNOCKOUT_STAGES or outcome == "draw":
            return None
        return fixture.home_team_id if outcome == "home" else fixture.away_team_id

    async def _prior_results(self, before: datetime) -> list[MatchResult]:
        rows = (
            await self.session.execute(
                select(Result, Fixture)
                .join(Fixture, col(Fixture.id) == col(Result.fixture_id))
                .where(col(Fixture.kickoff_utc) < before, col(Result.status) == "final")
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
