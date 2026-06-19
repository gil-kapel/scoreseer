"""Pure grading metrics — the product's correctness core.

NO database, NO network, NO LLM here: just deterministic functions over plain
data so they can be exhaustively unit-tested. `GradingService` (Slice 5) maps DB
rows / provider DTOs into these inputs and persists the resulting `Grade`.

Conventions (see PRD open questions):
- Score-level metrics use the **90-minute** scoreline, even for matches decided in
  extra time or penalties. ET/penalties only inform `advancing_correct`.
- Goalscorer credit counts goals and penalties; **own goals are excluded** from the
  scorer set (an OG is not "scoring" for grading purposes).
- `confidence_brier` scores the event "the predicted outcome occurs": predicted
  probability = `match_confidence`, realized = 1 if the actual 90' outcome equals
  the predicted outcome else 0.
"""

import unicodedata
from dataclasses import dataclass
from typing import Literal

Side = Literal["home", "away"]
Outcome = Literal["home", "draw", "away"]


@dataclass(frozen=True)
class PredScorer:
    player_name: str
    team: Side
    likelihood: float


@dataclass(frozen=True)
class Prediction:
    home_score: int
    away_score: int
    scorers: tuple[PredScorer, ...] = ()
    match_confidence: float = 0.0
    advancing_team: Side | None = None


@dataclass(frozen=True)
class ActualScorer:
    player_name: str
    team: Side
    type: Literal["goal", "pen", "og"] = "goal"


@dataclass(frozen=True)
class Result:
    home_score_90: int
    away_score_90: int
    decided_by: Literal["regular", "extra_time", "penalties"] = "regular"
    advanced_team: Side | None = None
    scorers: tuple[ActualScorer, ...] = ()


@dataclass(frozen=True)
class Grade:
    exact_hit: bool
    outcome_correct: bool
    goals_abs_error: int
    scorer_precision: float
    scorer_recall: float
    scorer_brier: float
    confidence_brier: float
    advancing_correct: bool | None


# --------------------------------------------------------------------------- #
# Score-level
# --------------------------------------------------------------------------- #
def outcome(home: int, away: int) -> Outcome:
    if home > away:
        return "home"
    if home < away:
        return "away"
    return "draw"


def exact_hit(pred: Prediction, result: Result) -> bool:
    return (pred.home_score, pred.away_score) == (result.home_score_90, result.away_score_90)


def outcome_correct(pred: Prediction, result: Result) -> bool:
    return outcome(pred.home_score, pred.away_score) == outcome(
        result.home_score_90, result.away_score_90
    )


def goals_abs_error(pred: Prediction, result: Result) -> int:
    return abs((pred.home_score + pred.away_score) - (result.home_score_90 + result.away_score_90))


# --------------------------------------------------------------------------- #
# Scorers
# --------------------------------------------------------------------------- #
def _normalize(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.casefold().split())


def _predicted_names(pred: Prediction) -> set[str]:
    return {_normalize(s.player_name) for s in pred.scorers}


def _actual_names(result: Result) -> set[str]:
    return {_normalize(s.player_name) for s in result.scorers if s.type != "og"}


def scorer_precision_recall(pred: Prediction, result: Result) -> tuple[float, float]:
    predicted, actual = _predicted_names(pred), _actual_names(result)
    inter = len(predicted & actual)
    precision = inter / len(predicted) if predicted else (1.0 if not actual else 0.0)
    recall = inter / len(actual) if actual else 1.0
    return precision, recall


def scorer_brier(pred: Prediction, result: Result) -> float:
    if not pred.scorers:
        return 0.0
    actual = _actual_names(result)
    errors = [
        (s.likelihood - (1.0 if _normalize(s.player_name) in actual else 0.0)) ** 2
        for s in pred.scorers
    ]
    return sum(errors) / len(errors)


# --------------------------------------------------------------------------- #
# Confidence + advancing
# --------------------------------------------------------------------------- #
def confidence_brier(pred: Prediction, result: Result) -> float:
    predicted_outcome = outcome(pred.home_score, pred.away_score)
    actual_outcome = outcome(result.home_score_90, result.away_score_90)
    realized = 1.0 if predicted_outcome == actual_outcome else 0.0
    return (pred.match_confidence - realized) ** 2


def advancing_correct(pred: Prediction, result: Result) -> bool | None:
    if pred.advancing_team is None or result.advanced_team is None:
        return None
    return pred.advancing_team == result.advanced_team


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
def grade(pred: Prediction, result: Result) -> Grade:
    precision, recall = scorer_precision_recall(pred, result)
    return Grade(
        exact_hit=exact_hit(pred, result),
        outcome_correct=outcome_correct(pred, result),
        goals_abs_error=goals_abs_error(pred, result),
        scorer_precision=precision,
        scorer_recall=recall,
        scorer_brier=scorer_brier(pred, result),
        confidence_brier=confidence_brier(pred, result),
        advancing_correct=advancing_correct(pred, result),
    )
