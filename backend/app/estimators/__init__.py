"""Statistical (non-LLM) estimators — free baselines for the accuracy lab."""

from app.estimators.elo import EloPrediction, estimate_ratings, predict_elo
from app.estimators.naive import predict_naive
from app.estimators.poisson import (
    MatchResult,
    ScorePrediction,
    TeamStrength,
    estimate_strengths,
    predict_score,
)

# Every non-LLM estimator's model_id. The dashboard "LLM" estimator = everything
# that ISN'T in this set, and the calibration loop excludes these so only real
# (LLM) predictions feed the prompt. Keep in sync with the *_MODEL_ID constants.
BASELINE_MODEL_IDS = frozenset({"poisson-v1", "elo-v1", "naive-v1"})

__all__ = [
    "MatchResult",
    "ScorePrediction",
    "TeamStrength",
    "estimate_strengths",
    "predict_score",
    "EloPrediction",
    "estimate_ratings",
    "predict_elo",
    "predict_naive",
    "BASELINE_MODEL_IDS",
]
