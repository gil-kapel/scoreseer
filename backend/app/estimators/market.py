"""Market estimator — de-vigged bookmaker odds -> outcome probabilities + scoreline.

The "wisdom of the market" baseline: implied 1X2 probabilities mapped to a winner
and a representative scoreline (supremacy from the home/away probability gap, kept
consistent with the most-likely outcome). PURE: `MarketService` fetches the odds.
"""

from dataclasses import dataclass

from app.estimators.elo import _consistent_scoreline

TYPICAL_TOTAL = 2.6
SUPREMACY_SCALE = 2.4  # (p_home - p_away) -> goal supremacy
MAX_GOALS = 8


@dataclass(frozen=True)
class MarketPrediction:
    home_goals: int
    away_goals: int
    p_home: float
    p_draw: float
    p_away: float

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


def predict_market(
    p_home: float,
    p_draw: float,
    p_away: float,
    *,
    typical_total: float = TYPICAL_TOTAL,
    scale: float = SUPREMACY_SCALE,
    max_goals: int = MAX_GOALS,
) -> MarketPrediction:
    total = p_home + p_draw + p_away or 1.0
    p_home, p_draw, p_away = p_home / total, p_draw / total, p_away / total
    probs = {"home": p_home, "draw": p_draw, "away": p_away}
    outcome = max(probs, key=lambda key: probs[key])
    sup = scale * (p_home - p_away)
    h, a = _consistent_scoreline(
        outcome, (typical_total + sup) / 2.0, (typical_total - sup) / 2.0, max_goals
    )
    return MarketPrediction(h, a, p_home, p_draw, p_away)
