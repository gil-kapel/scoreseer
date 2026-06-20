"""DixonColesService — persist Dixon-Coles predictions (a free, seeded estimator).

Estimates seeded attack/defense from results that kicked off *before* the target
fixture ("as-of"), so it never sees its own result — an honest, gradeable
forward-equivalent like Poisson/Elo.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.config import logger
from app.estimators.dixon_coles import estimate_strengths_seeded, predict_dc, seed_factors
from app.estimators.elo_seeds import DEFAULT_SEED, ELO_SEEDS
from app.estimators.poisson import MatchResult
from app.models import Fixture, Prediction, Result, Team
from app.repositories import PredictionRepository

DC_MODEL_ID = "dc-v1"
DC_VERSION = "dc-v1"
_KNOCKOUT_STAGES = {"r32", "r16", "qf", "sf", "final", "third_place"}


class DixonColesService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PredictionRepository(session)

    async def predict_fixture(self, fixture: Fixture) -> Prediction:
        log = logger.bind(component="DixonColesService", fixture_id=str(fixture.id))
        results = await self._prior_results(fixture.kickoff_utc)
        seed_attack, seed_defense = await self._seed_factors()
        strengths, league_avg = estimate_strengths_seeded(results, seed_attack, seed_defense)
        pred = predict_dc(
            str(fixture.home_team_id),
            str(fixture.away_team_id),
            strengths,
            league_avg,
            n_matches=len(results),
        )
        advancing_id = self._advancing(fixture, pred.outcome)
        explanation = (
            f"Dixon-Coles (seeded) over {pred.n_matches} prior result(s): "
            f"expected {pred.lambda_home:.2f}–{pred.lambda_away:.2f} goals, low-score "
            f"corrected. Most-likely {pred.home_goals}–{pred.away_goals} "
            f"(P({pred.outcome})={pred.confidence:.0%}, "
            f"home/draw/away = {pred.p_home:.0%}/{pred.p_draw:.0%}/{pred.p_away:.0%})."
        )
        log.info("dc.predict score={}-{}", pred.home_goals, pred.away_goals)
        fields = dict(
            snapshot_id=None,
            home_score=pred.home_goals,
            away_score=pred.away_goals,
            scorers=[],
            match_confidence=round(pred.confidence, 3),
            advancing_team_id=advancing_id,
            explanation=explanation,
            model_id=DC_MODEL_ID,
            prompt_version=DC_VERSION,
            schema_version=DC_VERSION,
            calibration_version=0,
            is_backfill=False,
            status="ok",
        )
        existing = await self.repo.current(
            fixture_id=fixture.id,
            prompt_version=DC_VERSION,
            model_id=DC_MODEL_ID,
            calibration_version=0,
        )
        if existing is not None:
            for key, value in fields.items():
                setattr(existing, key, value)
            await self.session.flush()
            return existing
        return await self.repo.create_prediction(fixture_id=fixture.id, **fields)

    def _advancing(self, fixture: Fixture, outcome: str):
        if fixture.stage not in _KNOCKOUT_STAGES or outcome == "draw":
            return None
        return fixture.home_team_id if outcome == "home" else fixture.away_team_id

    async def _seed_factors(self) -> tuple[dict[str, float], dict[str, float]]:
        teams = (await self.session.execute(select(Team))).scalars().all()
        attack: dict[str, float] = {}
        defense: dict[str, float] = {}
        for t in teams:
            a, d = seed_factors(ELO_SEEDS.get(t.fifa_code, DEFAULT_SEED))
            attack[str(t.id)] = a
            defense[str(t.id)] = d
        return attack, defense

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
