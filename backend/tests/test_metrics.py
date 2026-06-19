"""Slice 3 — grading metrics. Test-first; every value hand-computed.

Pure functions: no DB, no network. These pin the product's core correctness
claim (the "accuracy lab" only means anything if grading is exactly right).
"""

import pytest
from app.grading.metrics import (
    ActualScorer,
    Prediction,
    PredScorer,
    Result,
    confidence_brier,
    exact_hit,
    goals_abs_error,
    grade,
    outcome,
    outcome_correct,
    scorer_brier,
    scorer_precision_recall,
)


def _pred(h, a, scorers=(), confidence=0.5, advancing=None):
    return Prediction(
        home_score=h, away_score=a, scorers=tuple(scorers),
        match_confidence=confidence, advancing_team=advancing,
    )


def _res(h, a, scorers=(), decided_by="regular", advanced=None):
    return Result(
        home_score_90=h, away_score_90=a, scorers=tuple(scorers),
        decided_by=decided_by, advanced_team=advanced,
    )


# --- score-level metrics ---------------------------------------------------- #
def test_exact_hit_and_outcome() -> None:
    p, r = _pred(2, 1), _res(2, 1)
    assert exact_hit(p, r) is True
    assert outcome_correct(p, r) is True
    assert goals_abs_error(p, r) == 0


def test_right_outcome_wrong_score() -> None:
    p, r = _pred(2, 1), _res(3, 1)
    assert exact_hit(p, r) is False
    assert outcome_correct(p, r) is True
    assert goals_abs_error(p, r) == 1


def test_wrong_outcome() -> None:
    p, r = _pred(2, 1), _res(1, 2)
    assert exact_hit(p, r) is False
    assert outcome_correct(p, r) is False


def test_draw() -> None:
    p, r = _pred(1, 1), _res(1, 1)
    assert outcome(1, 1) == "draw"
    assert exact_hit(p, r) is True
    assert outcome_correct(p, r) is True


def test_knockout_graded_on_90_minutes_plus_advancing() -> None:
    # 1-0 predicted, but match was 1-1 at 90' and decided on penalties (home advanced).
    p = _pred(1, 0, advancing="home")
    r = _res(1, 1, decided_by="penalties", advanced="home")
    assert exact_hit(p, r) is False  # graded on the 90' line
    assert outcome_correct(p, r) is False  # 90' outcome was a draw
    g = grade(p, r)
    assert g.advancing_correct is True


# --- scorer metrics --------------------------------------------------------- #
def test_scorer_precision_recall_excludes_own_goals() -> None:
    p = _pred(2, 1, scorers=[PredScorer("Messi", "home", 0.6), PredScorer("Kane", "away", 0.6)])
    r = _res(
        2, 1, scorers=[ActualScorer("Messi", "home", "goal"), ActualScorer("Smith", "away", "og")]
    )
    precision, recall = scorer_precision_recall(p, r)
    assert precision == pytest.approx(0.5)  # Messi hit, Kane missed -> 1/2
    assert recall == pytest.approx(1.0)  # only real scorer (Messi) was predicted; OG excluded


def test_penalty_goals_count() -> None:
    p = _pred(1, 0, scorers=[PredScorer("Ronaldo", "home", 0.7)])
    r = _res(1, 0, scorers=[ActualScorer("Ronaldo", "home", "pen")])
    precision, recall = scorer_precision_recall(p, r)
    assert (precision, recall) == (pytest.approx(1.0), pytest.approx(1.0))


def test_scorer_brier_hand_computed() -> None:
    # A predicted 0.8 and scored; B predicted 0.3 and did not.
    p = _pred(1, 0, scorers=[PredScorer("A", "home", 0.8), PredScorer("B", "home", 0.3)])
    r = _res(1, 0, scorers=[ActualScorer("A", "home", "goal")])
    # ((0.8-1)^2 + (0.3-0)^2)/2 = (0.04 + 0.09)/2 = 0.065
    assert scorer_brier(p, r) == pytest.approx(0.065)


def test_name_normalization_matches_accents_and_case() -> None:
    p = _pred(1, 0, scorers=[PredScorer("Kylian Mbappé", "home", 1.0)])
    r = _res(1, 0, scorers=[ActualScorer("kylian mbappe", "home", "goal")])
    precision, recall = scorer_precision_recall(p, r)
    assert (precision, recall) == (pytest.approx(1.0), pytest.approx(1.0))
    assert scorer_brier(p, r) == pytest.approx(0.0)


# --- confidence brier ------------------------------------------------------- #
def test_confidence_brier_hand_computed() -> None:
    # Predicted home win with 0.7 confidence; home actually won -> realized 1.
    p = _pred(2, 1, confidence=0.7)
    r = _res(2, 1)
    assert confidence_brier(p, r) == pytest.approx(0.09)  # (0.7-1)^2
    # Same confidence, but outcome missed -> realized 0.
    assert confidence_brier(_pred(2, 1, confidence=0.7), _res(0, 1)) == pytest.approx(0.49)


# --- orchestrator ----------------------------------------------------------- #
def test_grade_aggregates_all_fields() -> None:
    p = _pred(2, 1, scorers=[PredScorer("Messi", "home", 0.9)], confidence=0.8)
    r = _res(2, 1, scorers=[ActualScorer("Messi", "home", "goal")])
    g = grade(p, r)
    assert g.exact_hit is True
    assert g.outcome_correct is True
    assert g.goals_abs_error == 0
    assert g.scorer_precision == pytest.approx(1.0)
    assert g.scorer_recall == pytest.approx(1.0)
    assert g.scorer_brier == pytest.approx(pytest.approx((0.9 - 1) ** 2))
    assert g.confidence_brier == pytest.approx(0.04)  # (0.8-1)^2
    assert g.advancing_correct is None  # not a knockout prediction
