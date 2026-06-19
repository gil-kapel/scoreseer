"""RunService — eligibility, isolation, idempotency, advisory lock. Fake providers, real DB."""

from app.db import get_sessionmaker
from app.models import Fixture
from app.models.schemas import PredictionAttempt, PredictionOutput
from app.providers.base import ResultDTO
from app.repositories import GradeRepository, PredictionRepository
from app.services import RunService
from app.services.run_service import _PREDICT_LOCK
from sqlalchemy import text

from tests.test_grading_service import FakeResults
from tests.test_prediction_service import FakeModel, FakeNarrative, _seed_fixture

_OK = PredictionOutput(
    home_score=2, away_score=1, scorers=[], match_confidence=0.5, explanation="Edge to home.",
)


def _model() -> FakeModel:
    return FakeModel(PredictionAttempt(output=_OK, raw_output="{...}", attempts=1))


async def _predict_run() -> dict:
    return await RunService(get_sessionmaker()).run_predictions(
        trigger="manual", window_h=24, cap=10,
        narrative=FakeNarrative(), model=_model(), model_id="claude-opus-4-8",
    )


async def test_run_predictions_processes_then_is_idempotent(session) -> None:
    f1 = await _seed_fixture(session, "r1")
    await _seed_fixture(session, "r2")
    await session.commit()

    first = await _predict_run()
    assert first["status"] == "succeeded"
    assert first["succeeded"] == 2 and first["failed"] == 0

    async with get_sessionmaker()() as s:
        assert await PredictionRepository(s).latest_ok(f1.id) is not None

    # Re-running selects nothing new (eligibility excludes already-predicted fixtures).
    second = await _predict_run()
    assert second["succeeded"] == 0 and second["failed"] == 0


async def test_run_is_busy_when_locked(session) -> None:
    await _seed_fixture(session, "r3")
    await session.commit()
    sm = get_sessionmaker()
    async with sm() as holder:
        await holder.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _PREDICT_LOCK})
        result = await _predict_run()
        assert result["status"] == "busy"
        await holder.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _PREDICT_LOCK})


def test_request_cancel_unknown_returns_false() -> None:
    from app.services.run_service import request_cancel

    assert request_cancel("00000000-0000-0000-0000-000000000000") is False


async def test_run_backfill_flags_and_grades(session) -> None:
    fixture = await _seed_fixture(session, "bf1")
    fixture.status = "finished"
    await session.commit()
    sm = get_sessionmaker()
    dto = ResultDTO(
        external_id="bf1", home_score_90=2, away_score_90=1, decided_by="regular", advanced=None
    )
    result = await RunService(sm).run_backfill(
        trigger="manual", cap=10, narrative=FakeNarrative(), model=_model(),
        model_id="claude-opus-4-8", results=FakeResults(dto),
    )
    assert result["succeeded"] == 1
    async with sm() as s:
        pred = await PredictionRepository(s).latest_ok(fixture.id)
        assert pred is not None and pred.is_backfill is True
        assert await GradeRepository(s).by_fixture(fixture.id) is not None


async def test_run_grading_grades_finished_predicted(session) -> None:
    fixture = await _seed_fixture(session, "r4")  # scheduled when predicted
    await session.commit()
    await _predict_run()

    sm = get_sessionmaker()
    async with sm() as s:  # match has now finished
        fx = await s.get(Fixture, fixture.id)
        fx.status = "finished"
        await s.commit()

    dto = ResultDTO(
        external_id="r4", home_score_90=2, away_score_90=1, decided_by="regular", advanced=None
    )
    result = await RunService(sm).run_grading(trigger="manual", cap=10, results=FakeResults(dto))
    assert result["succeeded"] == 1

    async with sm() as s:
        assert await GradeRepository(s).by_fixture(fixture.id) is not None
