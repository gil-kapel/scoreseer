"""Offline tests for prediction validation + the repair-retry loop. No network."""

import json

import pytest
from app.models.schemas import PredictionOutput
from app.providers.claude_predict import RawResponse, run_with_repair
from pydantic import ValidationError

_VALID = {
    "home_score": 2,
    "away_score": 1,
    "scorers": [{"player_name": "Messi", "team": "home", "likelihood": 0.6}],
    "match_confidence": 0.55,
    "advancing_team": None,
    "explanation": "Home side in better form and at altitude.",
}


def test_prediction_output_rejects_out_of_range_likelihood() -> None:
    bad = {**_VALID, "scorers": [{"player_name": "X", "team": "home", "likelihood": 1.5}]}
    with pytest.raises(ValidationError):
        PredictionOutput.model_validate(bad)


def _fake_call(responses):
    """Return an async call() that yields the queued RawResponses in order."""
    queue = list(responses)

    async def call(_messages):
        return queue.pop(0)

    return call


async def test_repair_returns_valid_first_try() -> None:
    call = _fake_call([RawResponse(json.dumps(_VALID), "end_turn")])
    attempt = await run_with_repair(call=call, base_messages=[], is_knockout=False)
    assert attempt.output is not None
    assert attempt.attempts == 1
    assert attempt.output.advancing_team is None


async def test_repair_recovers_after_invalid_knockout() -> None:
    invalid = {**_VALID, "advancing_team": None}  # knockout requires advancing_team
    valid = {**_VALID, "advancing_team": "home"}
    call = _fake_call(
        [RawResponse(json.dumps(invalid), "end_turn"), RawResponse(json.dumps(valid), "end_turn")]
    )
    attempt = await run_with_repair(call=call, base_messages=[], is_knockout=True)
    assert attempt.output is not None
    assert attempt.attempts == 2
    assert attempt.output.advancing_team == "home"


async def test_repair_gives_up_after_retries() -> None:
    bad = RawResponse("not json", "end_turn")
    call = _fake_call([bad, bad, bad])
    attempt = await run_with_repair(call=call, base_messages=[], is_knockout=False, max_retries=2)
    assert attempt.output is None
    assert "schema invalid" in (attempt.failure_reason or "")
    assert attempt.attempts == 3


async def test_repair_handles_refusal() -> None:
    call = _fake_call([RawResponse("", "refusal")])
    attempt = await run_with_repair(call=call, base_messages=[], is_knockout=False)
    assert attempt.output is None
    assert attempt.failure_reason == "model refused"
