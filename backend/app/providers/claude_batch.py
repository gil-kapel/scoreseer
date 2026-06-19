"""Batch predictions via the Anthropic Message Batches API — 50% cheaper, async.

Each request is ONE self-contained prediction with NO web search: web search is
agentic (pause_turn continuations) and can't run inside a batch, and for past
matches it would just leak the result. The brief is built locally from stored
results, so these predictions are hindsight-free. Output is plain JSON (the prompt
asks for it) parsed defensively — structured-output enforcement isn't relied on.
"""

import asyncio
import json
import re

from anthropic import AsyncAnthropic

from app.config import Settings, logger
from app.models.schemas import PredictionContext, PredictionOutput
from app.prompts import build_prediction_prompt

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class ClaudeBatchPredictor:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    @property
    def model_id(self) -> str:
        return self._settings.predict_model_id

    async def predict_many(
        self, items: list[tuple[str, PredictionContext]], *, poll_interval: float = 15.0
    ) -> dict[str, PredictionOutput | None]:
        """items = [(custom_id, context)] -> {custom_id: parsed output or None}."""
        log = logger.bind(component="ClaudeBatchPredictor")
        requests = [
            {
                "custom_id": cid,
                "params": {
                    "model": self._settings.predict_model_id,
                    "max_tokens": 1500,
                    "messages": [{"role": "user", "content": build_prediction_prompt(ctx)}],
                },
            }
            for cid, ctx in items
        ]
        batch = await self._client.messages.batches.create(requests=requests)  # type: ignore[arg-type]
        log.info("batch.submitted id={} requests={}", batch.id, len(requests))
        await self._await_end(batch.id, poll_interval)
        return await self._collect(batch.id)

    async def _await_end(self, batch_id: str, interval: float) -> None:
        log = logger.bind(component="ClaudeBatchPredictor")
        while True:
            batch = await self._client.messages.batches.retrieve(batch_id)
            if batch.processing_status == "ended":
                log.info("batch.ended id={} counts={}", batch_id, batch.request_counts)
                return
            log.info("batch.processing id={} status={}", batch_id, batch.processing_status)
            await asyncio.sleep(interval)

    async def _collect(self, batch_id: str) -> dict[str, PredictionOutput | None]:
        out: dict[str, PredictionOutput | None] = {}
        async for entry in await self._client.messages.batches.results(batch_id):
            out[entry.custom_id] = parse_batch_entry(entry)
        return out


def parse_batch_entry(entry: object) -> PredictionOutput | None:
    """Pull the JSON prediction out of one batch result entry (None if unusable)."""
    result = getattr(entry, "result", None)
    if result is None or getattr(result, "type", "") != "succeeded":
        return None
    message = getattr(result, "message", None)
    if message is None:
        return None
    text = "".join(
        b.text
        for b in message.content
        if getattr(b, "type", "") == "text" and getattr(b, "text", "")
    )
    match = _JSON_RE.search(text)
    if not match:
        return None
    try:
        return PredictionOutput.model_validate(json.loads(match.group(0)))
    except Exception:  # noqa: BLE001 — any malformed output is just a failed item
        return None
