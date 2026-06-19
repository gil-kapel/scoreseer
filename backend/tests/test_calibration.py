"""CalibrationService — bias computation, threshold, and prediction injection. No network."""

from datetime import UTC, datetime, timedelta

import pytest
from app.grading import metrics
from app.models import Fixture, Grade, Prediction, Result, Team
from app.models.schemas import PredictionAttempt, PredictionOutput
from app.repositories import PredictionRepository
from app.services import CalibrationService, PredictionService

from tests.test_prediction_service import FakeNarrative, _seed_fixture

_OK = PredictionOutput(
    home_score=2, away_score=1, scorers=[], match_confidence=0.5, explanation="Edge to home.",
)


def _outcome(h: int, a: int) -> str:
    return "home" if h > a else "away" if a > h else "draw"


async def _seed_graded(session, ext: str, pred: tuple[int, int], actual: tuple[int, int]) -> None:
    """One fully-graded match: predicted `pred`, actual `actual` (90')."""
    home = Team(fifa_code=f"H{ext}", name="H")
    away = Team(fifa_code=f"A{ext}", name="A")
    session.add(home)
    session.add(away)
    await session.flush()
    fx = Fixture(
        external_id=ext, provider="fd", stage="group", status="finished",
        home_team_id=home.id, away_team_id=away.id,
        kickoff_utc=datetime.now(UTC) - timedelta(hours=2),
    )
    session.add(fx)
    await session.flush()
    p = Prediction(
        fixture_id=fx.id, home_score=pred[0], away_score=pred[1], scorers=[],
        match_confidence=0.5, explanation="x", model_id="m",
        prompt_version="pred-v1", schema_version="out-v1", calibration_version=0, status="ok",
    )
    session.add(p)
    session.add(Result(
        fixture_id=fx.id, home_score_90=actual[0], away_score_90=actual[1],
        ft_outcome=_outcome(*actual), decided_by="regular", status="final",
    ))
    await session.flush()
    g = metrics.grade(
        metrics.Prediction(pred[0], pred[1], (), 0.5, None),
        metrics.Result(actual[0], actual[1]),
    )
    session.add(Grade(
        prediction_id=p.id, fixture_id=fx.id, exact_hit=g.exact_hit,
        outcome_correct=g.outcome_correct, goals_abs_error=g.goals_abs_error,
        scorer_precision=g.scorer_precision, scorer_recall=g.scorer_recall,
        scorer_brier=g.scorer_brier, confidence_brier=g.confidence_brier,
        advancing_correct=g.advancing_correct,
    ))
    await session.flush()


async def test_recompute_below_threshold_returns_none(session) -> None:
    for i in range(3):
        await _seed_graded(session, f"c{i}", (2, 1), (1, 1))
    await session.commit()
    assert await CalibrationService(session).recompute() is None


async def test_recompute_computes_biases(session) -> None:
    # Always predicted 2-1 (home win) but every match finished 1-1 (draw).
    for i in range(6):
        await _seed_graded(session, f"c{i}", (2, 1), (1, 1))
    await session.commit()

    profile = await CalibrationService(session).recompute()
    assert profile is not None
    assert profile.version == 1 and profile.n_graded == 6
    agg = profile.metric_aggregates
    assert agg["home_score_bias"] == pytest.approx(1.0)  # predicted 2, actual 1
    assert agg["away_score_bias"] == pytest.approx(0.0)
    assert agg["outcome_accuracy"] == pytest.approx(0.0)  # predicted win, actual draw
    assert agg["overconfidence"] == pytest.approx(0.5)  # 0.5 stated vs 0.0 correct
    assert "over-predicted home goals by 1.00" in profile.prompt_snippet


async def test_prediction_injects_latest_calibration(session) -> None:
    for i in range(6):
        await _seed_graded(session, f"c{i}", (2, 1), (1, 1))
    await session.commit()
    profile = await CalibrationService(session).recompute()
    await session.commit()

    fixture = await _seed_fixture(session, "newfx")
    await session.commit()

    captured: dict = {}

    class CaptureModel:
        async def predict(self, context):
            captured["ctx"] = context
            return PredictionAttempt(output=_OK, raw_output="x", attempts=1)

    result = await PredictionService(session, FakeNarrative(), CaptureModel()).predict_fixture(
        fixture.id, model_id="claude-opus-4-8"
    )
    assert result["status"] == "ok"
    assert captured["ctx"].calibration_snippet != ""  # snippet was injected
    pred = await PredictionRepository(session).latest_ok(fixture.id)
    assert pred is not None and pred.calibration_version == profile.version
