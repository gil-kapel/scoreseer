"""Statistical (non-LLM) estimators — free baselines for the accuracy lab."""

from app.estimators.dixon_coles import estimate_strengths_seeded, predict_dc, seed_factors
from app.estimators.elo import EloPrediction, estimate_ratings, predict_elo
from app.estimators.market import MarketPrediction, predict_market
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
BASELINE_MODEL_IDS = frozenset({"poisson-v1", "elo-v1", "naive-v1", "dc-v1", "market-v1"})

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
    "estimate_strengths_seeded",
    "predict_dc",
    "seed_factors",
    "MarketPrediction",
    "predict_market",
    "BASELINE_MODEL_IDS",
]
