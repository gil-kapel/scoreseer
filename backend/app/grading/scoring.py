"""Prediction-league scoring — points per match, weighted by tournament stage.

Tiered: an exact score earns the (higher) exact points; a correct outcome only
earns the outcome points; otherwise zero. Exact does NOT also add the outcome
points. Sum across graded matches = the estimator's headline score.
"""

# Points for a correct outcome (1/X/2 direction) by stage.
OUTCOME_POINTS: dict[str, int] = {
    "group": 1,
    "r32": 2,
    "r16": 2,
    "qf": 4,
    "sf": 5,
    "third_place": 5,
    "final": 8,
}

# Points for an exact 90-minute scoreline by stage.
EXACT_POINTS: dict[str, int] = {
    "group": 3,
    "r32": 5,
    "r16": 5,
    "qf": 8,
    "sf": 10,
    "third_place": 10,
    "final": 15,
}


def match_points(stage: str, *, exact_hit: bool, outcome_correct: bool) -> int:
    """Points earned for one graded match (tiered: exact > outcome > 0)."""
    if exact_hit:
        return EXACT_POINTS.get(stage, EXACT_POINTS["group"])
    if outcome_correct:
        return OUTCOME_POINTS.get(stage, OUTCOME_POINTS["group"])
    return 0


def max_points(stage: str) -> int:
    """The most a single match could score (an exact hit)."""
    return EXACT_POINTS.get(stage, EXACT_POINTS["group"])
