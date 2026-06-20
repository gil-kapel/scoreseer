"""Dixon-Coles goals model — Poisson with two improvements that matter for sparse,
short-tournament data:

  1. seeded attack/defense priors (pre-tournament strength) so it isn't cold like
     the plain Poisson baseline, and
  2. the Dixon-Coles low-score correction (tau), which fixes independent Poisson's
     well-known under-prediction of draws and low scores.

PURE: no DB/network. `DixonColesService` feeds it as-of results + per-team seeds.
Returns a `ScorePrediction` (same shape as Poisson) so grading/serialisation reuse.
"""

import math
from collections import defaultdict

from app.estimators.poisson import (
    DEFAULT_LEAGUE_AVG,
    HOME_ADVANTAGE,
    MAX_GOALS,
    MatchResult,
    ScorePrediction,
    TeamStrength,
    _clip,
    _poisson_pmf,
)

RHO = -0.13  # DC low-score correlation: < 0 lifts 0-0 / 1-1, trims 1-0 / 0-1
SHRINK = 2.0  # pseudo-matches of the seed prior (shrinks sparse teams toward strength)
_AVG_SEED = 1750.0
_SEED_SPREAD = 300.0
_SEED_COEF = 0.35


def seed_factors(seed: float) -> tuple[float, float]:
    """Pre-tournament Elo seed -> (attack, defense) priors (multipliers around 1.0).

    Stronger teams score more and concede less; the factor is clamped so a single
    outlier seed can't produce a degenerate prior.
    """
    f = max(-1.5, min(1.5, (seed - _AVG_SEED) / _SEED_SPREAD))
    return math.exp(_SEED_COEF * f), math.exp(-_SEED_COEF * f)


def estimate_strengths_seeded(
    results: list[MatchResult],
    seed_attack: dict[str, float],
    seed_defense: dict[str, float],
    *,
    shrink: float = SHRINK,
) -> tuple[dict[str, TeamStrength], float]:
    """Attack/defense from results, shrunk toward each team's SEED prior (not the
    league mean), so a team with no games yet starts at its pre-tournament strength."""
    league_avg = DEFAULT_LEAGUE_AVG
    if results:
        league_avg = max(
            sum(r.home_goals + r.away_goals for r in results) / (2 * len(results)), 0.3
        )
    scored: dict[str, float] = defaultdict(float)
    conceded: dict[str, float] = defaultdict(float)
    played: dict[str, int] = defaultdict(int)
    for r in results:
        scored[r.home_id] += r.home_goals
        conceded[r.home_id] += r.away_goals
        played[r.home_id] += 1
        scored[r.away_id] += r.away_goals
        conceded[r.away_id] += r.home_goals
        played[r.away_id] += 1

    strengths: dict[str, TeamStrength] = {}
    for tid, a_prior in seed_attack.items():
        n = played.get(tid, 0)
        d_prior = seed_defense.get(tid, 1.0)
        attack = (scored.get(tid, 0.0) + shrink * league_avg * a_prior) / (n + shrink) / league_avg
        defense = (
            conceded.get(tid, 0.0) + shrink * league_avg * d_prior
        ) / (n + shrink) / league_avg
        strengths[tid] = TeamStrength(attack=attack, defense=defense)
    return strengths, league_avg


def _tau(x: int, y: int, lam: float, mu: float, rho: float) -> float:
    """Dixon-Coles low-score adjustment to the independent-Poisson joint pmf."""
    if x == 0 and y == 0:
        return max(0.0, 1.0 - lam * mu * rho)
    if x == 0 and y == 1:
        return max(0.0, 1.0 + lam * rho)
    if x == 1 and y == 0:
        return max(0.0, 1.0 + mu * rho)
    if x == 1 and y == 1:
        return max(0.0, 1.0 - rho)
    return 1.0


def predict_dc(
    home_id: str,
    away_id: str,
    strengths: dict[str, TeamStrength],
    league_avg: float,
    *,
    n_matches: int = 0,
    rho: float = RHO,
    home_advantage: float = HOME_ADVANTAGE,
    max_goals: int = MAX_GOALS,
) -> ScorePrediction:
    """Scoreline (rounded expected goals) + tau-corrected outcome probabilities."""
    home = strengths.get(home_id, TeamStrength(1.0, 1.0))
    away = strengths.get(away_id, TeamStrength(1.0, 1.0))
    lam_home = _clip(league_avg * home.attack * away.defense * home_advantage, max_goals)
    lam_away = _clip(league_avg * away.attack * home.defense / home_advantage, max_goals)

    ph = [_poisson_pmf(i, lam_home) for i in range(max_goals + 1)]
    pa = [_poisson_pmf(j, lam_away) for j in range(max_goals + 1)]
    p_home = p_draw = p_away = 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = ph[i] * pa[j] * _tau(i, j, lam_home, lam_away, rho)
            if i > j:
                p_home += p
            elif i == j:
                p_draw += p
            else:
                p_away += p
    total = p_home + p_draw + p_away or 1.0
    p_home, p_draw, p_away = p_home / total, p_draw / total, p_away / total

    return ScorePrediction(
        home_goals=min(int(lam_home + 0.5), max_goals),
        away_goals=min(int(lam_away + 0.5), max_goals),
        p_home=p_home,
        p_draw=p_draw,
        p_away=p_away,
        lambda_home=lam_home,
        lambda_away=lam_away,
        n_matches=n_matches,
    )
