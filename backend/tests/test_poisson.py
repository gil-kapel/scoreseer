"""Unit tests for the pure Poisson estimator (no DB, no network)."""

from app.estimators.poisson import (
    DEFAULT_LEAGUE_AVG,
    MatchResult,
    estimate_strengths,
    predict_score,
)


def test_no_history_returns_league_default_and_balanced_prediction():
    strengths, league_avg = estimate_strengths([])
    assert strengths == {}
    assert league_avg == DEFAULT_LEAGUE_AVG
    # Unknown teams -> strength 1.0 each; home edge makes a home/draw modal score.
    pred = predict_score("A", "B", strengths, league_avg)
    assert pred.outcome in {"home", "draw"}
    assert 0.0 < pred.confidence <= 1.0
    # Probabilities form a distribution.
    assert abs((pred.p_home + pred.p_draw + pred.p_away) - 1.0) < 1e-6


def test_probabilities_sum_to_one():
    results = [MatchResult("A", "B", 3, 0), MatchResult("C", "A", 1, 2)]
    strengths, league_avg = estimate_strengths(results)
    pred = predict_score("A", "C", strengths, league_avg, n_matches=len(results))
    assert abs((pred.p_home + pred.p_draw + pred.p_away) - 1.0) < 1e-6
    assert pred.n_matches == 2


def test_strong_attack_beats_weak_defense():
    # A scores a lot; D concedes a lot. A (home) vs D should favour A clearly.
    results = [
        MatchResult("A", "X", 4, 0),
        MatchResult("A", "Y", 3, 1),
        MatchResult("Z", "D", 4, 0),
        MatchResult("W", "D", 3, 0),
    ]
    strengths, league_avg = estimate_strengths(results)
    a_atk = strengths["A"].attack
    d_def = strengths["D"].defense
    assert a_atk > 1.0  # above-average attack
    assert d_def > 1.0  # leaky defense
    pred = predict_score("A", "D", strengths, league_avg)
    assert pred.outcome == "home"
    assert pred.home_goals > pred.away_goals
    assert pred.p_home > pred.p_away


def test_home_advantage_breaks_symmetric_matchup():
    # Two identical teams: the home side should be at least as likely to win.
    results = [MatchResult("A", "B", 1, 1), MatchResult("B", "A", 1, 1)]
    strengths, league_avg = estimate_strengths(results)
    pred = predict_score("A", "B", strengths, league_avg)
    assert pred.p_home >= pred.p_away


def test_shrinkage_pulls_sparse_teams_toward_average():
    # One team, one freak 5-0 result. With shrinkage its attack stays moderate,
    # not 5x the league average.
    results = [MatchResult("A", "B", 5, 0)]
    strengths, _ = estimate_strengths(results)
    assert strengths["A"].attack < 3.0
