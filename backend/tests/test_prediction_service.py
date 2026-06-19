"""PredictionService with fake providers — stores snapshot+prediction, idempotent. No network."""

from datetime import UTC, datetime, timedelta

from app.models import Fixture, Team
from app.models.schemas import PredictionAttempt, PredictionOutput
from app.providers.base import NarrativeBundle
from app.repositories import PredictionRepository
from app.services import PredictionService

_OUTPUT = PredictionOutput(
    home_score=2,
    away_score=1,
    scorers=[{"player_name": "Messi", "team": "home", "likelihood": 0.6}],
    match_confidence=0.55,
    advancing_team=None,
    explanation="Home side in better form.",
)


class FakeNarrative:
    async def fetch_pre_match(self, *, home, away, kickoff_utc, stage="group") -> NarrativeBundle:
        return NarrativeBundle(
            evidence={"summary": "brief"},
            sources=[{"url": "http://x", "title": "X"}],
            data_quality="ok",
        )


class FakeModel:
    def __init__(self, attempt: PredictionAttempt) -> None:
        self._attempt = attempt

    async def predict(self, context) -> PredictionAttempt:
        return self._attempt


async def _seed_fixture(session, ext_id: str, stage: str = "group") -> Fixture:
    home = Team(fifa_code=f"H{ext_id}", name="Argentina")
    away = Team(fifa_code=f"A{ext_id}", name="Brazil")
    session.add(home)
    session.add(away)
    await session.flush()
    fixture = Fixture(
        external_id=ext_id,
        provider="football_data",
        stage=stage,
        home_team_id=home.id,
        away_team_id=away.id,
        kickoff_utc=datetime.now(UTC) + timedelta(hours=5),
    )
    session.add(fixture)
    await session.flush()
    return fixture


async def test_predict_stores_snapshot_and_prediction_and_is_idempotent(session) -> None:
    fixture = await _seed_fixture(session, "p1")
    attempt = PredictionAttempt(output=_OUTPUT, raw_output="{...}", attempts=1)
    service = PredictionService(session, FakeNarrative(), FakeModel(attempt))

    result = await service.predict_fixture(fixture.id, model_id="claude-opus-4-8")
    assert result["status"] == "ok"
    assert result["score"] == "2-1"

    pred = await PredictionRepository(session).latest(fixture.id)
    assert pred is not None
    assert pred.status == "ok"
    assert pred.snapshot_id is not None
    assert pred.scorers[0]["player_name"] == "Messi"

    # Re-running with the same versions is a no-op.
    again = await service.predict_fixture(fixture.id, model_id="claude-opus-4-8")
    assert again["status"] == "skipped"


async def test_failed_prediction_is_stored_visibly(session) -> None:
    fixture = await _seed_fixture(session, "p2")
    attempt = PredictionAttempt(
        output=None, raw_output="garbage", attempts=3, failure_reason="schema invalid: boom"
    )
    service = PredictionService(session, FakeNarrative(), FakeModel(attempt))

    result = await service.predict_fixture(fixture.id, model_id="claude-opus-4-8")
    assert result["status"] == "failed"

    pred = await PredictionRepository(session).latest(fixture.id)
    assert pred is not None
    assert pred.status == "failed"
    assert pred.failure_reason == "schema invalid: boom"
    assert pred.raw_output == "garbage"


async def test_failed_prediction_is_overwritten_on_retry(session) -> None:
    fixture = await _seed_fixture(session, "p3")
    failed = PredictionAttempt(output=None, raw_output="garbage", attempts=3, failure_reason="boom")
    await PredictionService(session, FakeNarrative(), FakeModel(failed)).predict_fixture(
        fixture.id, model_id="claude-opus-4-8"
    )
    # Retry now succeeds — must overwrite the failed row, not violate the unique key.
    ok = PredictionAttempt(output=_OUTPUT, raw_output="{...}", attempts=1)
    result = await PredictionService(session, FakeNarrative(), FakeModel(ok)).predict_fixture(
        fixture.id, model_id="claude-opus-4-8"
    )
    assert result["status"] == "ok"
    pred = await PredictionRepository(session).latest(fixture.id)
    assert pred is not None and pred.status == "ok"
    assert pred.failure_reason is None
