"""SQLModel tables — the ScoreSeer data model (architecture §Data model).

Conventions:
- UUID primary keys (except the singleton Config row).
- Timezone-aware UTC timestamps.
- JSONB for evidence / flexible payloads (Postgres).
- Append-only tables (DataSnapshot, Prediction, Grade, CalibrationProfile) are never
  mutated; re-runs create new versioned rows. Idempotency is enforced by the UNIQUE
  constraints declared in __table_args__.

String-enum value sets are documented as module constants for reference; columns store
plain strings and are validated at the API / service boundary (Pydantic).
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

# --- Reference enum value sets (documentation; columns are plain str) ---
STAGES = ("group", "r32", "r16", "qf", "sf", "final")
FIXTURE_STATUS = ("scheduled", "live", "finished", "postponed", "abandoned")
PREDICTION_STATUS = ("ok", "failed")
RESULT_STATUS = ("final", "void", "needs_review")
DECIDED_BY = ("regular", "extra_time", "penalties")
DATA_QUALITY = ("ok", "low")
RUN_TYPE = ("predict", "grade")
RUN_TRIGGER = ("scheduled", "manual")
RUN_STATUS = ("running", "succeeded", "partial", "failed")
RUN_ITEM_STATUS = ("succeeded", "skipped", "failed")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _ts_col(*, nullable: bool = False, index: bool = False) -> Column:
    return Column(DateTime(timezone=True), nullable=nullable, index=index)


def _jsonb(*, nullable: bool = False) -> Column:
    return Column(JSONB, nullable=nullable)


# --------------------------------------------------------------------------- #
# Reference data
# --------------------------------------------------------------------------- #
class Team(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    fifa_code: str = Field(index=True, unique=True)  # e.g. "ARG"
    name: str
    group_label: str | None = None
    crest_url: str | None = None


class Player(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    team_id: uuid.UUID = Field(foreign_key="team.id", index=True)
    name: str = Field(index=True)
    position: str | None = None
    external_ref: str | None = None


class Fixture(SQLModel, table=True):
    """Synced from the structured fixtures API (authoritative).

    Identity is (provider, external_id): the same real match has different ids
    across providers, so uniqueness is provider-scoped. The sync service also
    reconciles by natural key (home, away) to avoid cross-provider duplicates.
    """

    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_fixture_provider_external"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    external_id: str = Field(index=True)
    provider: str = Field(default="football_data", index=True)
    stage: str
    group_label: str | None = None
    home_team_id: uuid.UUID = Field(foreign_key="team.id", index=True)
    away_team_id: uuid.UUID = Field(foreign_key="team.id", index=True)
    kickoff_utc: datetime = Field(sa_column=_ts_col(index=True))
    venue: str | None = None
    status: str = Field(default="scheduled", index=True)
    synced_at: datetime = Field(default_factory=_utcnow, sa_column=_ts_col())


# --------------------------------------------------------------------------- #
# Prediction pipeline (append-only)
# --------------------------------------------------------------------------- #
class DataSnapshot(SQLModel, table=True):
    """Immutable narrative evidence used for a prediction (web search + provider data)."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    fixture_id: uuid.UUID = Field(foreign_key="fixture.id", index=True)
    fetched_at: datetime = Field(default_factory=_utcnow, sa_column=_ts_col())
    evidence: dict[str, Any] = Field(default_factory=dict, sa_column=_jsonb())
    sources: list[dict[str, Any]] = Field(default_factory=list, sa_column=_jsonb())
    search_queries: list[str] = Field(default_factory=list, sa_column=_jsonb())
    provider_data: dict[str, Any] = Field(default_factory=dict, sa_column=_jsonb())
    data_quality: str = "ok"
    missing_signals: list[str] = Field(default_factory=list, sa_column=_jsonb())


class Prediction(SQLModel, table=True):
    """Append-only, versioned by (prompt_version, model_id, calibration_version)."""

    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "prompt_version",
            "model_id",
            "calibration_version",
            name="uq_prediction_version",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    fixture_id: uuid.UUID = Field(foreign_key="fixture.id", index=True)
    snapshot_id: uuid.UUID | None = Field(default=None, foreign_key="datasnapshot.id")

    home_score: int
    away_score: int
    scorers: list[dict[str, Any]] = Field(default_factory=list, sa_column=_jsonb())
    match_confidence: float = 0.0
    advancing_team_id: uuid.UUID | None = Field(default=None, foreign_key="team.id")
    explanation: str = ""

    model_id: str
    prompt_version: str
    schema_version: str
    calibration_version: int = 0
    # Made after the match was played (hindsight-contaminated) — excluded from
    # calibration + headline accuracy, but shown in history with a label.
    is_backfill: bool = Field(default=False, index=True)

    status: str = "ok"  # ok | failed
    failure_reason: str | None = None
    raw_output: str | None = None
    created_at: datetime = Field(default_factory=_utcnow, sa_column=_ts_col(index=True))


# --------------------------------------------------------------------------- #
# Ground truth + grading
# --------------------------------------------------------------------------- #
class Result(SQLModel, table=True):
    """Authoritative result from the structured sports API."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    fixture_id: uuid.UUID = Field(foreign_key="fixture.id", unique=True, index=True)
    home_score_90: int
    away_score_90: int
    ft_outcome: str  # home | draw | away
    decided_by: str = "regular"
    advanced_team_id: uuid.UUID | None = Field(default=None, foreign_key="team.id")
    scorers: list[dict[str, Any]] = Field(default_factory=list, sa_column=_jsonb())
    source_refs: list[dict[str, Any]] = Field(default_factory=list, sa_column=_jsonb())
    status: str = "final"  # final | void | needs_review
    fetched_at: datetime = Field(default_factory=_utcnow, sa_column=_ts_col())


class Grade(SQLModel, table=True):
    """Append-only, one per prediction."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    prediction_id: uuid.UUID = Field(foreign_key="prediction.id", unique=True, index=True)
    fixture_id: uuid.UUID = Field(foreign_key="fixture.id", index=True)

    exact_hit: bool
    outcome_correct: bool
    goals_abs_error: int
    scorer_precision: float
    scorer_recall: float
    scorer_brier: float
    confidence_brier: float
    advancing_correct: bool | None = None
    points: int = 0  # prediction-league points (stage-weighted; see grading/scoring.py)
    graded_at: datetime = Field(default_factory=_utcnow, sa_column=_ts_col())


class CalibrationProfile(SQLModel, table=True):
    """Versioned snapshot of accumulated accuracy/bias, injected into prediction prompts."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    version: int = Field(index=True, unique=True)
    computed_at: datetime = Field(default_factory=_utcnow, sa_column=_ts_col())
    n_graded: int = 0
    metric_aggregates: dict[str, Any] = Field(default_factory=dict, sa_column=_jsonb())
    bias_summary: str = ""
    prompt_snippet: str = ""


# --------------------------------------------------------------------------- #
# Scheduler runs
# --------------------------------------------------------------------------- #
class Run(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    type: str = Field(index=True)  # predict | grade
    trigger: str = "scheduled"  # scheduled | manual
    status: str = Field(default="running", index=True)
    started_at: datetime = Field(default_factory=_utcnow, sa_column=_ts_col(index=True))
    finished_at: datetime | None = Field(default=None, sa_column=_ts_col(nullable=True))
    params: dict[str, Any] = Field(default_factory=dict, sa_column=_jsonb())
    totals: dict[str, Any] = Field(default_factory=dict, sa_column=_jsonb())


class RunItem(SQLModel, table=True):
    """Per-fixture outcome within a run — isolates failures."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    run_id: uuid.UUID = Field(foreign_key="run.id", index=True)
    fixture_id: uuid.UUID = Field(foreign_key="fixture.id", index=True)
    status: str  # succeeded | skipped | failed
    detail: str | None = None
    duration_ms: int | None = None
    spend_estimate: float | None = None


# --------------------------------------------------------------------------- #
# Config (singleton)
# --------------------------------------------------------------------------- #
class Config(SQLModel, table=True):
    id: int = Field(default=1, primary_key=True)
    prediction_window_hours: int = 24
    cadence: str = "daily"
    per_run_fixture_cap: int = 20
    spend_cap: float = 0.0
    use_odds: bool = True
    updated_at: datetime = Field(default_factory=_utcnow, sa_column=_ts_col())
