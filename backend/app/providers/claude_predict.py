"""PredictionModel via Claude structured output (+ repair-retry).

Separate call from web search (no citations here) so `output_config.format` can
constrain the response to strict JSON. The repair loop (`run_with_repair`) is a
pure async function over a `call` callable so it is unit-tested without network.
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from anthropic import AsyncAnthropic
from pydantic import ValidationError

from app.config import Settings, logger
from app.models.schemas import PredictionAttempt, PredictionContext, PredictionOutput
from app.prompts import PREDICTION_JSON_SCHEMA, build_prediction_prompt

_MAX_RETRIES = 2


@dataclass
class RawResponse:
    text: str
    stop_reason: str | None


CallFn = Callable[[list[dict]], Awaitable[RawResponse]]


def _business_rule_error(output: PredictionOutput, is_knockout: bool) -> str | None:
    if is_knockout and output.advancing_team is None:
        return "knockout match requires advancing_team (home or away)"
    return None


async def run_with_repair(
    *, call: CallFn, base_messages: list[dict], is_knockout: bool, max_retries: int = _MAX_RETRIES
) -> PredictionAttempt:
    """Call the model, validate, and retry with a repair prompt on invalid output."""
    messages = list(base_messages)
    last_raw = ""
    for attempt in range(max_retries + 1):
        raw = await call(messages)
        last_raw = raw.text
        if raw.stop_reason == "refusal":
            return PredictionAttempt(None, last_raw, attempt + 1, "model refused")
        try:
            output = PredictionOutput.model_validate(json.loads(raw.text))
            rule_error = _business_rule_error(output, is_knockout)
            if rule_error:
                raise ValueError(rule_error)
            if not is_knockout:
                output = output.model_copy(update={"advancing_team": None})
            return PredictionAttempt(output, last_raw, attempt + 1, None)
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            if attempt >= max_retries:
                return PredictionAttempt(None, last_raw, attempt + 1, f"schema invalid: {exc}")
            messages = messages + [
                {"role": "assistant", "content": raw.text},
                {"role": "user", "content": f"That was invalid ({exc}). Return ONLY valid JSON."},
            ]
    # pragma: no cover — loop always returns inside
    return PredictionAttempt(None, last_raw, max_retries + 1, "exhausted retries")


class ClaudePredictionModel:
    def __init__(self, settings: Settings, client: AsyncAnthropic) -> None:
        self._settings = settings
        self._client = client

    async def predict(self, context: PredictionContext) -> PredictionAttempt:
        base = [{"role": "user", "content": build_prediction_prompt(context)}]
        result = await run_with_repair(
            call=self._call, base_messages=base, is_knockout=context.is_knockout
        )
        logger.bind(component="ClaudePredictionModel").info(
            "predict.done knockout={} ok={} attempts={}",
            context.is_knockout, result.output is not None, result.attempts,
        )
        return result

    async def _call(self, messages: list[dict]) -> RawResponse:
        resp = await self._client.messages.create(
            model=self._settings.predict_model_id,
            max_tokens=2000,
            thinking={"type": "adaptive"},
            # effort=low trims thinking depth — a constrained scoreline prediction
            # doesn't need deep reasoning, and thinking tokens are the priciest output.
            output_config=cast(
                "Any",
                {
                    "format": {"type": "json_schema", "schema": PREDICTION_JSON_SCHEMA},
                    "effort": "low",
                },
            ),
            messages=cast("Any", messages),
        )
        text = next(
            (getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text"), ""
        )
        return RawResponse(text=text, stop_reason=resp.stop_reason)
