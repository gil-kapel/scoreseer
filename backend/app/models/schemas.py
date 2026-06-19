"""API request/response schemas (Pydantic) — the boundary contracts."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class TeamBrief(BaseModel):
    code: str
    name: str
    group_label: str | None = None
    crest_url: str | None = None


class PredictionSummary(BaseModel):
    home_score: int
    away_score: int
    match_confidence: float
    scorers: list[dict[str, Any]] = Field(default_factory=list)


class FixtureRead(BaseModel):
    id: uuid.UUID
    external_id: str
    provider: str
    stage: str
    group_label: str | None
    home: TeamBrief
    away: TeamBrief
    kickoff_utc: datetime
    venue: str | None
    status: str
    prediction_status: str = "scheduled"
    prediction: PredictionSummary | None = None


class SyncSummary(BaseModel):
    fetched: int
    created: int
    updated: int
    total_fixtures: int


# --------------------------------------------------------------------------- #
# Prediction LLM I/O (client-side validated)
# --------------------------------------------------------------------------- #
class ScorerPredOut(BaseModel):
    player_name: str
    team: Literal["home", "away"]
    likelihood: float = Field(ge=0, le=1)


class PredictionOutput(BaseModel):
    """The strict structured output the prediction LLM must return."""

    home_score: int = Field(ge=0, le=20)
    away_score: int = Field(ge=0, le=20)
    scorers: list[ScorerPredOut] = Field(default_factory=list)
    match_confidence: float = Field(ge=0, le=1)
    advancing_team: Literal["home", "away"] | None = None
    explanation: str = Field(min_length=10, max_length=2000)


@dataclass
class PredictionContext:
    """Everything the prediction step needs — assembled by PredictionService."""

    home_name: str
    away_name: str
    stage: str
    group_label: str | None
    kickoff_utc: datetime
    is_knockout: bool
    narrative_summary: str
    calibration_snippet: str = ""


@dataclass
class PredictionAttempt:
    """Result of a (possibly retried) prediction call."""

    output: PredictionOutput | None
    raw_output: str
    attempts: int
    failure_reason: str | None = None


# --------------------------------------------------------------------------- #
# Read models for the match-detail API
# --------------------------------------------------------------------------- #
class PredictionRead(BaseModel):
    id: uuid.UUID
    home_score: int
    away_score: int
    scorers: list[dict[str, Any]] = Field(default_factory=list)
    match_confidence: float
    advancing_team: Literal["home", "away"] | None
    explanation: str
    status: str
    failure_reason: str | None
    model_id: str
    prompt_version: str
    calibration_version: int
    is_backfill: bool = False
    created_at: datetime


class ResultRead(BaseModel):
    home_score_90: int
    away_score_90: int
    ft_outcome: str
    decided_by: str
    scorers: list[dict[str, Any]] = Field(default_factory=list)
    status: str


class GradeRead(BaseModel):
    exact_hit: bool
    outcome_correct: bool
    goals_abs_error: int
    scorer_precision: float
    scorer_recall: float
    scorer_brier: float
    confidence_brier: float
    advancing_correct: bool | None
    points: int


class MatchDetail(BaseModel):
    fixture: FixtureRead
    prediction: PredictionRead | None = None
    result: ResultRead | None = None
    grade: GradeRead | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    data_quality: str | None = None
    # True while a real LLM prediction is running in the background for this fixture.
    predicting: bool = False


# --------------------------------------------------------------------------- #
# Runs (admin)
# --------------------------------------------------------------------------- #
class RunItemRead(BaseModel):
    fixture_id: uuid.UUID
    status: str
    detail: str | None


class RunRead(BaseModel):
    id: uuid.UUID
    type: str
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    params: dict[str, Any] = Field(default_factory=dict)
    totals: dict[str, Any] = Field(default_factory=dict)


class RunDetail(BaseModel):
    run: RunRead
    items: list[RunItemRead] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Dashboard (read-only aggregates)
# --------------------------------------------------------------------------- #
class TrendPoint(BaseModel):
    date: str
    n: int
    cumulative_outcome: float
    cumulative_exact: float
    cumulative_points: int = 0


class StagePoints(BaseModel):
    stage: str
    points: int
    max_points: int
    n: int


class DashboardMetrics(BaseModel):
    n_graded: int
    outcome_accuracy: float
    exact_rate: float
    goals_mae: float
    scorer_precision: float
    scorer_recall: float
    confidence_brier: float
    total_points: int = 0
    max_points: int = 0
    points_by_stage: list[StagePoints] = Field(default_factory=list)
    backfill_excluded: int = 0  # graded backfill (hindsight) matches kept out of these stats
    trend: list[TrendPoint] = Field(default_factory=list)


class ReliabilityBin(BaseModel):
    bucket: str
    avg_confidence: float
    accuracy: float
    n: int


class CalibrationVersionRead(BaseModel):
    version: int
    computed_at: datetime
    n_graded: int
    bias_summary: str


class CalibrationView(BaseModel):
    current: CalibrationVersionRead | None = None
    prompt_snippet: str | None = None
    metric_aggregates: dict[str, Any] = Field(default_factory=dict)
    versions: list[CalibrationVersionRead] = Field(default_factory=list)
    reliability: list[ReliabilityBin] = Field(default_factory=list)
    first_half_brier: float | None = None
    second_half_brier: float | None = None


class HistoryRow(BaseModel):
    fixture_id: uuid.UUID
    home: str
    away: str
    stage: str
    group_label: str | None
    kickoff_utc: datetime
    predicted: str
    actual: str
    exact_hit: bool
    outcome_correct: bool
    goals_abs_error: int
    points: int
    is_backfill: bool = False
