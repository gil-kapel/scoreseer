"""Naive baseline — always predict the designated home side wins 1-0.

The floor the smarter estimators must clear: if Poisson / Elo / the LLM can't beat
"home team wins 1-0 every time", they aren't adding value. PURE: no inputs.
"""

# Roughly the listed-/home-side win rate at a neutral-venue tournament.
HOME_WIN_BASE_RATE = 0.45


def predict_naive() -> tuple[int, int, float]:
    """(home_goals, away_goals, confidence) — constant for every fixture."""
    return 1, 0, HOME_WIN_BASE_RATE
