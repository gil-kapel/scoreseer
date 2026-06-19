"""Provider ports (Strategy / Ports & Adapters).

External integrations live behind these protocols so they are swappable and
fakeable in tests. Two structured sports-data providers are used together,
**free-first**: the composite adapter (Slice 2) tries `football_data` then
`api_football` per `Settings.provider_order`, so a free-tier gap or rate limit
in one falls back to the other. Concrete adapters land in Slices 2 / 4 / 5.
"""

from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from app.models.schemas import PredictionAttempt, PredictionContext


# --------------------------------------------------------------------------- #
# DTOs (provider-neutral shapes; adapters normalize each API into these)
# --------------------------------------------------------------------------- #
class FixtureDTO(BaseModel):
    external_id: str
    provider: str
    stage: str
    group_label: str | None = None
    home_code: str
    away_code: str
    home_name: str
    away_name: str
    home_crest: str | None = None
    away_crest: str | None = None
    kickoff_utc: datetime
    venue: str | None = None
    status: str = "scheduled"


class ActualScorerDTO(BaseModel):
    player_name: str
    team: Literal["home", "away"]
    type: Literal["goal", "pen", "og"] = "goal"
    minute: int | None = None


class ResultDTO(BaseModel):
    external_id: str
    home_score_90: int
    away_score_90: int
    decided_by: Literal["regular", "extra_time", "penalties"] = "regular"
    advanced: Literal["home", "away"] | None = None
    scorers: list[ActualScorerDTO] = Field(default_factory=list)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)


class NarrativeBundle(BaseModel):
    """Pre-match narrative evidence from Claude web search (never graded truth)."""

    evidence: dict[str, Any] = Field(default_factory=dict)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    data_quality: Literal["ok", "low"] = "ok"
    missing_signals: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Protocols
# --------------------------------------------------------------------------- #
@runtime_checkable
class FixturesProvider(Protocol):
    async def list_fixtures(self) -> list[FixtureDTO]: ...


@runtime_checkable
class ResultsProvider(Protocol):
    async def get_result(self, external_id: str) -> ResultDTO | None:
        """Return the final result, or None if the match isn't final yet."""
        ...


@runtime_checkable
class NarrativeProvider(Protocol):
    async def fetch_pre_match(
        self, *, home: str, away: str, kickoff_utc: datetime, stage: str = "group"
    ) -> NarrativeBundle: ...


@runtime_checkable
class PredictionModel(Protocol):
    async def predict(self, context: PredictionContext) -> PredictionAttempt:
        """Return a validated prediction (or a failure) — adapter handles repair-retry."""
        ...
