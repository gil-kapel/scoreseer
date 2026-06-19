"""GradingService with a fake ResultsProvider — wiring, awaiting, void, idempotency. No network."""


from app.models import Prediction
from app.models.schemas import PredictionAttempt, PredictionOutput
from app.providers.base import ActualScorerDTO, ResultDTO
from app.repositories import GradeRepository, PredictionRepository
from app.services import GradingService, PredictionService

from tests.test_prediction_service import FakeModel, FakeNarrative, _seed_fixture

_PRED = PredictionOutput(
    home_score=2,
    away_score=1,
    scorers=[{"player_name": "Messi", "team": "home", "likelihood": 0.6}],
    match_confidence=0.7,
    advancing_team=None,
    explanation="Home edge expected.",
)


class FakeResults:
    def __init__(self, dto: ResultDTO | None) -> None:
        self._dto = dto

    async def get_result(self, external_id: str) -> ResultDTO | None:
        return self._dto


async def _seed_prediction(session, fixture) -> Prediction:
    attempt = PredictionAttempt(output=_PRED, raw_output="{...}", attempts=1)
    await PredictionService(session, FakeNarrative(), FakeModel(attempt)).predict_fixture(
        fixture.id, model_id="claude-opus-4-8"
    )
    return await PredictionRepository(session).latest_ok(fixture.id)


def _result(home: int, away: int, scorers=()) -> ResultDTO:
    return ResultDTO(
        external_id="x",
        home_score_90=home,
        away_score_90=away,
        decided_by="regular",
        advanced=None,
        scorers=list(scorers),
    )


async def test_grade_exact_hit_and_idempotent(session) -> None:
    fixture = await _seed_fixture(session, "g1")
    fixture.status = "finished"
    await _seed_prediction(session, fixture)
    dto = _result(2, 1, scorers=[ActualScorerDTO(player_name="Messi", team="home", type="goal")])
    service = GradingService(session, FakeResults(dto))

    result = await service.grade_fixture(fixture.id)
    assert result["status"] == "graded"
    assert result["n_graded"] == 1

    grade = await GradeRepository(session).by_fixture(fixture.id)
    assert grade is not None
    assert (grade.exact_hit, grade.outcome_correct, grade.goals_abs_error) == (True, True, 0)
    assert grade.scorer_recall == 1.0

    # Re-grading is a no-op.
    again = await service.grade_fixture(fixture.id)
    assert again["status"] == "skipped"


async def test_grade_wrong_outcome(session) -> None:
    fixture = await _seed_fixture(session, "g2")
    fixture.status = "finished"
    await _seed_prediction(session, fixture)  # predicted 2-1 (home win)
    result = await GradingService(session, FakeResults(_result(0, 3))).grade_fixture(fixture.id)
    assert result["status"] == "graded"
    grade = await GradeRepository(session).by_fixture(fixture.id)
    assert grade is not None
    assert grade.exact_hit is False
    assert grade.outcome_correct is False
    assert grade.goals_abs_error == 0  # both totals are 3


async def test_awaiting_result_when_none(session) -> None:
    fixture = await _seed_fixture(session, "g3")
    fixture.status = "finished"
    await _seed_prediction(session, fixture)
    result = await GradingService(session, FakeResults(None)).grade_fixture(fixture.id)
    assert result["status"] == "awaiting_result"


async def test_void_postponed_fixture(session) -> None:
    fixture = await _seed_fixture(session, "g4")
    fixture.status = "postponed"
    await session.flush()
    result = await GradingService(session, FakeResults(_result(1, 1))).grade_fixture(fixture.id)
    assert result["status"] == "void"


async def test_no_prediction(session) -> None:
    fixture = await _seed_fixture(session, "g5")
    fixture.status = "finished"
    await session.flush()
    result = await GradingService(session, FakeResults(_result(1, 0))).grade_fixture(fixture.id)
    assert result["status"] == "no_prediction"
