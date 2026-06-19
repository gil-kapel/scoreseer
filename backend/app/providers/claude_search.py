"""NarrativeProvider via Claude server-side web search.

Runs ONE Messages API call with the `web_search_20260209` server tool to gather
pre-match narrative + citations. Web search returns citations, which are
incompatible with structured outputs — so this is kept strictly separate from
the prediction step (`claude_predict.py`).
"""

from datetime import datetime
from typing import Any, Literal, cast

from anthropic import AsyncAnthropic

from app.config import Settings, logger
from app.prompts import build_search_prompt
from app.providers.base import NarrativeBundle

_WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search"}
_MAX_CONTINUATIONS = 4


class ClaudeNarrativeProvider:
    def __init__(self, settings: Settings, client: AsyncAnthropic) -> None:
        self._settings = settings
        self._client = client

    async def fetch_pre_match(
        self, *, home: str, away: str, kickoff_utc: datetime, stage: str = "group"
    ) -> NarrativeBundle:
        log = logger.bind(component="ClaudeNarrativeProvider")
        log.info(
            "search.start home={} away={} model={}", home, away, self._settings.format_model_id
        )
        prompt = build_search_prompt(home=home, away=away, stage=stage, kickoff_utc=kickoff_utc)
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        resp = None
        for i in range(_MAX_CONTINUATIONS):
            resp = await self._client.messages.create(
                model=self._settings.format_model_id,
                max_tokens=4000,
                tools=cast("Any", [_WEB_SEARCH_TOOL]),
                messages=cast("Any", messages),
            )
            if resp.stop_reason != "pause_turn":
                break
            log.info("search.continue iteration={} (model paused to keep searching)", i + 1)
            messages.append({"role": "assistant", "content": resp.content})

        summary = _collect_text(resp.content) if resp else ""
        sources = _collect_sources(resp.content) if resp else []
        quality: Literal["ok", "low"] = "ok" if sources else "low"
        missing = [] if sources else ["no web sources returned"]
        log.info(
            "search.done home={} away={} sources={} quality={}",
            home, away, len(sources), quality,
        )
        return NarrativeBundle(
            evidence={"summary": summary},
            sources=sources,
            search_queries=[],
            data_quality=quality,
            missing_signals=missing,
        )


def _collect_text(content: list) -> str:
    return "\n".join(
        b.text for b in content if getattr(b, "type", "") == "text" and getattr(b, "text", "")
    )


def _collect_sources(content: list) -> list[dict[str, Any]]:
    """Pull source URLs/titles from web_search_tool_result blocks and text citations."""
    sources: list[dict[str, Any]] = []
    for block in content:
        btype = getattr(block, "type", "")
        if btype == "web_search_tool_result":
            for r in getattr(block, "content", None) or []:
                _add(sources, getattr(r, "url", None), getattr(r, "title", None))
        elif btype == "text":
            for c in getattr(block, "citations", None) or []:
                _add(sources, getattr(c, "url", None), getattr(c, "title", None))
    return sources


def _add(sources: list[dict[str, Any]], url: str | None, title: str | None) -> None:
    if url and not any(s["url"] == url for s in sources):
        sources.append({"url": url, "title": title})
