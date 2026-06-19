"""Statistical (non-LLM) estimators — free baselines for the accuracy lab."""

from app.estimators.poisson import (
    MatchResult,
    ScorePrediction,
    TeamStrength,
    estimate_strengths,
    predict_score,
)

__all__ = [
    "MatchResult",
    "ScorePrediction",
    "TeamStrength",
    "estimate_strengths",
    "predict_score",
]
