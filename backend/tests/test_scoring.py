"""Scoring tiers per stage. Pure, no network."""

from app.grading.scoring import match_points, max_points


def test_group_stage_tiers() -> None:
    assert match_points("group", exact_hit=True, outcome_correct=True) == 3
    assert match_points("group", exact_hit=False, outcome_correct=True) == 1
    assert match_points("group", exact_hit=False, outcome_correct=False) == 0


def test_exact_does_not_add_outcome() -> None:
    # Exact is the higher tier, not additive.
    assert match_points("final", exact_hit=True, outcome_correct=True) == 15
    assert match_points("final", exact_hit=False, outcome_correct=True) == 8


def test_stage_weights() -> None:
    assert match_points("qf", exact_hit=True, outcome_correct=True) == 8
    assert match_points("sf", exact_hit=False, outcome_correct=True) == 5
    assert match_points("third_place", exact_hit=True, outcome_correct=True) == 10
    assert match_points("r16", exact_hit=False, outcome_correct=True) == 2


def test_max_points() -> None:
    assert max_points("group") == 3
    assert max_points("final") == 15
