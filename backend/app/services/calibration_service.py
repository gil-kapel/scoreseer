"""CalibrationService — turn rolling grade history into a self-correction snippet.

This is the PRD's "track + calibrate" loop: aggregate every graded prediction
into observed biases (score over/under-prediction, confidence calibration) and a
compact `prompt_snippet` that PredictionService injects into future prompts.
Recomputed after each grading run. No trained model — prompt-level calibration.
"""

from app.config import logger
from app.models import CalibrationProfile
from app.repositories import CalibrationRepository

MIN_GRADED = 5  # below this, signal is too noisy to calibrate on


class CalibrationService:
    def __init__(self, session) -> None:
        self.session = session
        self.repo = CalibrationRepository(session)

    async def recompute(self) -> CalibrationProfile | None:
        log = logger.bind(component="CalibrationService")
        rows = await self.repo.load_graded()
        n = len(rows)
        if n < MIN_GRADED:
            log.info("calibration.skip n={} (min {})", n, MIN_GRADED)
            return None

        outcome_acc = _mean(g.outcome_correct for _, _, g in rows)
        exact_rate = _mean(g.exact_hit for _, _, g in rows)
        goals_mae = _mean(g.goals_abs_error for _, _, g in rows)
        home_bias = _mean(p.home_score - r.home_score_90 for p, r, _ in rows)
        away_bias = _mean(p.away_score - r.away_score_90 for p, r, _ in rows)
        mean_conf = _mean(p.match_confidence for p, _, _ in rows)
        overconfidence = mean_conf - outcome_acc

        aggregates = {
            "n_graded": n,
            "outcome_accuracy": round(outcome_acc, 4),
            "exact_rate": round(exact_rate, 4),
            "goals_mae": round(goals_mae, 4),
            "home_score_bias": round(home_bias, 4),
            "away_score_bias": round(away_bias, 4),
            "mean_confidence": round(mean_conf, 4),
            "overconfidence": round(overconfidence, 4),
        }
        version = await self.repo.next_version()
        profile = await self.repo.create(
            version=version,
            n_graded=n,
            metric_aggregates=aggregates,
            bias_summary=_summary(aggregates),
            prompt_snippet=_snippet(aggregates),
        )
        log.info("calibration.updated version={} n={} biases={}", version, n, aggregates)
        return profile


def _mean(values) -> float:
    items = [float(v) for v in values]
    return sum(items) / len(items) if items else 0.0


def _dir(bias: float) -> str:
    return "over" if bias > 0 else "under"


def _summary(a: dict) -> str:
    return (
        f"{a['n_graded']} graded: outcome {a['outcome_accuracy']:.0%}, "
        f"exact {a['exact_rate']:.0%}, goals MAE {a['goals_mae']:.2f}; "
        f"home {_dir(a['home_score_bias'])}-predicted by {abs(a['home_score_bias']):.2f}, "
        f"away {_dir(a['away_score_bias'])} by {abs(a['away_score_bias']):.2f}; "
        f"{'over' if a['overconfidence'] > 0 else 'under'}confident "
        f"({a['mean_confidence']:.0%} vs {a['outcome_accuracy']:.0%})."
    )


def _snippet(a: dict) -> str:
    over = a["overconfidence"] > 0
    return (
        f"Calibration from {a['n_graded']} graded matches — outcome accuracy "
        f"{a['outcome_accuracy']:.0%}, exact-score {a['exact_rate']:.0%}, mean total-goals "
        f"error {a['goals_mae']:.2f}. You have {_dir(a['home_score_bias'])}-predicted home "
        f"goals by {abs(a['home_score_bias']):.2f} per match and "
        f"{_dir(a['away_score_bias'])}-predicted away goals by {abs(a['away_score_bias']):.2f}; "
        f"adjust scorelines accordingly. Your stated confidence averages "
        f"{a['mean_confidence']:.0%} vs {a['outcome_accuracy']:.0%} actual accuracy, so you "
        f"are {'over' if over else 'under'}-confident — {'lower' if over else 'raise'} confidence."
    )
