"""GradingService — fetch authoritative result, grade the prediction, persist.

Imports the pure Slice 3 metrics unchanged; this service only maps DB rows /
provider DTOs into the metric inputs and stores the resulting Grade. One Grade
per prediction (idempotent); postponed/abandoned fixtures are marked void and
excluded from grading.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import logger
from app.grading import metrics, scoring
from app.models import Fixture, Grade, Prediction
from app.providers.base import ResultDTO, ResultsProvider
from app.repositories import (
    GradeRepository,
    PredictionRepository,
    ResultRepository,
    result_dto_to_values,
)

_VOID_STATUSES = {"postponed", "abandoned"}


class GradingService:
    def __init__(self, session: AsyncSession, results: ResultsProvider) -> None:
        self.session = session
        self.results = results
        self.predictions = PredictionRepository(session)
        self.result_repo = ResultRepository(session)
        self.grades = GradeRepository(session)

    async def grade_fixture(self, fixture_id: uuid.UUID) -> dict:
        log = logger.bind(component="GradingService", fixture_id=str(fixture_id))
        log.info("grade.init")
        fixture = await self.session.get(Fixture, fixture_id)
        if fixture is None:
            return {"status": "not_found"}
        if fixture.status in _VOID_STATUSES:
            await self.result_repo.mark_void(fixture_id)
            await self.session.commit()
            return {"status": "void"}

        # Grade EVERY OK prediction for the fixture (one per estimator), not just the
        # latest — so Poisson and the LLM/batch each get their own grade for the bake-off.
        predictions = await self.predictions.all_ok(fixture_id)
        if not predictions:
            return {"status": "no_prediction"}
        ungraded = [
            p for p in predictions if await self.grades.by_prediction(p.id) is None
        ]
        if not ungraded:
            return {"status": "skipped"}

        dto = await self.results.get_result(fixture.external_id)
        if dto is None:
            return {"status": "awaiting_result"}

        values = result_dto_to_values(
            dto, home_id=fixture.home_team_id, away_id=fixture.away_team_id
        )
        await self.result_repo.upsert(fixture_id=fixture_id, values=values)
        for prediction in ungraded:
            await self._grade(fixture, prediction, dto)
        await self.session.commit()
        return {"status": "graded", "n_graded": len(ungraded)}

    async def _grade(self, fixture: Fixture, prediction: Prediction, dto: ResultDTO) -> Grade:
        g = metrics.grade(_to_metric_pred(prediction, fixture), _to_metric_result(dto))
        points = scoring.match_points(
            fixture.stage, exact_hit=g.exact_hit, outcome_correct=g.outcome_correct
        )
        return await self.grades.create(
            prediction_id=prediction.id,
            fixture_id=fixture.id,
            exact_hit=g.exact_hit,
            outcome_correct=g.outcome_correct,
            goals_abs_error=g.goals_abs_error,
            scorer_precision=g.scorer_precision,
            scorer_recall=g.scorer_recall,
            scorer_brier=g.scorer_brier,
            confidence_brier=g.confidence_brier,
            advancing_correct=g.advancing_correct,
            points=points,
        )


def _pred_side(prediction: Prediction, fixture: Fixture) -> str | None:
    if prediction.advancing_team_id == fixture.home_team_id:
        return "home"
    if prediction.advancing_team_id == fixture.away_team_id:
        return "away"
    return None


def _to_metric_pred(prediction: Prediction, fixture: Fixture) -> metrics.Prediction:
    scorers = tuple(
        metrics.PredScorer(s["player_name"], s["team"], float(s["likelihood"]))
        for s in prediction.scorers
    )
    return metrics.Prediction(
        home_score=prediction.home_score,
        away_score=prediction.away_score,
        scorers=scorers,
        match_confidence=prediction.match_confidence,
        advancing_team=_pred_side(prediction, fixture),  # type: ignore[arg-type]
    )


def _to_metric_result(dto: ResultDTO) -> metrics.Result:
    scorers = tuple(
        metrics.ActualScorer(s.player_name, s.team, s.type) for s in dto.scorers
    )
    return metrics.Result(
        home_score_90=dto.home_score_90,
        away_score_90=dto.away_score_90,
        decided_by=dto.decided_by,
        advanced_team=dto.advanced,
        scorers=scorers,
    )
