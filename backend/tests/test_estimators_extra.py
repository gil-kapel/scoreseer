"""Unit tests for the Elo + Naive baselines (pure functions, no DB)."""

from app.estimators import MatchResult, estimate_ratings, predict_elo, predict_naive
from app.estimators.elo import _consistent_scoreline


def test_naive_is_constant_home_win() -> None:
    assert predict_naive() == (1, 0, 0.45)


def test_elo_winner_gains_loser_loses_symmetrically() -> None:
    ratings = estimate_ratings([MatchResult("A", "B", 2, 0)])
    assert ratings["A"] > 1500.0 > ratings["B"]
    # Elo is zero-sum: the winner's gain equals the loser's loss.
    assert round((ratings["A"] - 1500.0) + (ratings["B"] - 1500.0), 6) == 0.0


def test_elo_bigger_win_moves_rating_more() -> None:
    small = estimate_ratings([MatchResult("A", "B", 1, 0)])
    big = estimate_ratings([MatchResult("C", "D", 5, 0)])
    assert (big["C"] - 1500.0) > (small["A"] - 1500.0)


def test_elo_stronger_team_predicted_to_win() -> None:
    ratings = estimate_ratings([MatchResult("A", f"T{i}", 3, 0) for i in range(4)])
    pred = predict_elo("A", "Z", ratings)  # Z unseen (1500); A is strong
    assert pred.outcome == "home"
    assert pred.home_goals > pred.away_goals
    assert pred.confidence == pred.p_home
    assert abs(pred.p_home + pred.p_draw + pred.p_away - 1.0) < 1e-9


def test_elo_scoreline_and_outcome_always_agree() -> None:
    for ratings in ({}, {"X": 1800.0}, {"Y": 1800.0}):
        pred = predict_elo("X", "Y", ratings)
        winner = (
            "home"
            if pred.home_goals > pred.away_goals
            else "away" if pred.home_goals < pred.away_goals else "draw"
        )
        assert winner == pred.outcome


def test_consistent_scoreline_enforces_winner() -> None:
    assert _consistent_scoreline("home", 0.4, 0.4, 8) == (1, 0)
    h, a = _consistent_scoreline("away", 0.2, 3.0, 8)
    assert a > h
    assert _consistent_scoreline("draw", 1.4, 0.6, 8) == (1, 1)
