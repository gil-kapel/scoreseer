"""Elo rating model — a free, rating-based estimator (distinct from Poisson).

Each team carries an Elo rating, updated after every result with a goal-difference
multiplier (World-Football-Elo style). A fixture's prediction comes from the
rating gap: outcome probabilities (with a gap-aware draw band) and a scoreline
from the implied goal supremacy, kept consistent with the most-likely outcome so
grading never sees a 1-1 "draw" that the model actually thinks is a home win.

PURE: no DB, no network. `EloService` feeds it results ordered by kickoff
("as-of"), so a prediction for a finished match never sees its own result — an
honest forward-equivalent prediction that can be graded without poisoning.
"""

from dataclasses import dataclass

from app.estimators.poisson import MatchResult  # (home_id, away_id, home_goals, away_goals)

BASE_RATING = 1500.0
K_FACTOR = 40.0  # high — few, high-stakes WC matches should move ratings
HOME_FIELD = 35.0  # Elo points for the designated "home" side (venues are ~neutral)
ELO_PER_GOAL = 250.0  # rating gap that maps to ~1 goal of supremacy
TYPICAL_TOTAL = 2.6  # typical total goals per match
MAX_GOALS = 8


@dataclass(frozen=True)
class EloPrediction:
    home_goals: int
    away_goals: int
    p_home: float
    p_draw: float
    p_away: float
    home_rating: float
    away_rating: float
    n_matches: int

    @property
    def outcome(self) -> str:
        if self.home_goals > self.away_goals:
            return "home"
        if self.home_goals < self.away_goals:
            return "away"
        return "draw"

    @property
    def confidence(self) -> float:
        return {"home": self.p_home, "draw": self.p_draw, "away": self.p_away}[self.outcome]


def _goal_multiplier(goal_diff: int) -> float:
    """World-Football-Elo margin-of-victory multiplier."""
    gd = abs(goal_diff)
    if gd <= 1:
        return 1.0
    if gd == 2:
        return 1.5
    return (11 + gd) / 8.0


def estimate_ratings(
    results: list[MatchResult],
    *,
    base: float = BASE_RATING,
    k: float = K_FACTOR,
    home_field: float = HOME_FIELD,
) -> dict[str, float]:
    """Sequential Elo over results in CHRONOLOGICAL order (caller must sort)."""
    ratings: dict[str, float] = {}
    for r in results:
        rh = ratings.get(r.home_id, base)
        ra = ratings.get(r.away_id, base)
        exp_home = 1.0 / (1.0 + 10 ** ((ra - rh - home_field) / 400.0))
        if r.home_goals > r.away_goals:
            s_home = 1.0
        elif r.home_goals < r.away_goals:
            s_home = 0.0
        else:
            s_home = 0.5
        delta = k * _goal_multiplier(r.home_goals - r.away_goals) * (s_home - exp_home)
        ratings[r.home_id] = rh + delta
        ratings[r.away_id] = ra - delta
    return ratings


def _round(x: float) -> int:
    return int(max(0.0, x) + 0.5)


def _consistent_scoreline(
    outcome: str, raw_home: float, raw_away: float, max_goals: int
) -> tuple[int, int]:
    """A scoreline whose winner matches `outcome` (so the graded result agrees)."""
    h = min(max_goals, _round(raw_home))
    a = min(max_goals, _round(raw_away))
    if outcome == "home":
        h = max(h, 1)
        a = min(a, h - 1)
    elif outcome == "away":
        a = max(a, 1)
        h = min(h, a - 1)
    else:  # draw — equal goals
        g = min(max_goals, _round((raw_home + raw_away) / 2.0))
        h = a = g
    return h, a


def predict_elo(
    home_id: str,
    away_id: str,
    ratings: dict[str, float],
    *,
    n_matches: int = 0,
    base: float = BASE_RATING,
    home_field: float = HOME_FIELD,
    elo_per_goal: float = ELO_PER_GOAL,
    typical_total: float = TYPICAL_TOTAL,
    max_goals: int = MAX_GOALS,
) -> EloPrediction:
    """Outcome probabilities + a consistent scoreline for one fixture."""
    rh = ratings.get(home_id, base)
    ra = ratings.get(away_id, base)
    dr = rh + home_field - ra
    we = 1.0 / (1.0 + 10 ** (-dr / 400.0))  # expected score for home (win + ½·draw)

    # Draw band: widest when teams are even, vanishing when lopsided.
    p_draw = max(0.0, 0.28 * (1.0 - abs(2 * we - 1.0)))
    p_home = max(0.0, we - p_draw / 2.0)
    p_away = max(0.0, (1.0 - we) - p_draw / 2.0)
    total = p_home + p_draw + p_away or 1.0
    p_home, p_draw, p_away = p_home / total, p_draw / total, p_away / total

    probs = {"home": p_home, "draw": p_draw, "away": p_away}
    outcome = max(probs, key=lambda key: probs[key])
    sup = max(-float(max_goals), min(float(max_goals), dr / elo_per_goal))
    home_goals, away_goals = _consistent_scoreline(
        outcome, (typical_total + sup) / 2.0, (typical_total - sup) / 2.0, max_goals
    )
    return EloPrediction(
        home_goals=home_goals,
        away_goals=away_goals,
        p_home=p_home,
        p_draw=p_draw,
        p_away=p_away,
        home_rating=rh,
        away_rating=ra,
        n_matches=n_matches,
    )
