"""Poisson goals model — a free, hindsight-free statistical estimator.

This is a NON-LLM baseline for the accuracy lab. Each team gets an attack and a
defense strength (relative to the tournament's average goals/team/match),
estimated from results. A fixture's expected goals are then the product of the
home attack, away defense, league average and a mild home-advantage factor; the
score distribution is the outer product of two independent Poissons, and we
report the modal scoreline plus calibrated outcome probabilities.

PURE: no DB, no network. `PoissonService` feeds it results and persists the
prediction. Because the service estimates strengths from matches played *before*
each fixture's kickoff ("as-of"), a prediction for a finished match never sees
its own result — so unlike the LLM backfill it is an honest forward-equivalent
prediction and can be graded without poisoning the accuracy numbers.
"""

import math
from collections import defaultdict
from dataclasses import dataclass

# Tunables (typical men's World Cup scoring).
DEFAULT_LEAGUE_AVG = 1.35  # goals per team per match when there's no history yet
SHRINK_MATCHES = 2.0  # pseudo-matches of league-average form (shrinks sparse teams)
HOME_ADVANTAGE = 1.08  # "home" is just the fixture's designated side — keep it mild
MAX_GOALS = 8  # truncate the Poisson grid; P(>8) is negligible

Outcome = str  # "home" | "draw" | "away"


@dataclass(frozen=True)
class TeamStrength:
    attack: float  # >1.0 scores more than the average team
    defense: float  # >1.0 concedes more than the average team


@dataclass(frozen=True)
class MatchResult:
    home_id: str
    away_id: str
    home_goals: int
    away_goals: int


@dataclass(frozen=True)
class ScorePrediction:
    home_goals: int
    away_goals: int
    p_home: float
    p_draw: float
    p_away: float
    lambda_home: float
    lambda_away: float
    n_matches: int  # how many prior results informed the strengths

    @property
    def outcome(self) -> Outcome:
        if self.home_goals > self.away_goals:
            return "home"
        if self.home_goals < self.away_goals:
            return "away"
        return "draw"

    @property
    def confidence(self) -> float:
        """Probability mass of the predicted outcome (a real, calibrated number)."""
        return {"home": self.p_home, "draw": self.p_draw, "away": self.p_away}[self.outcome]


def estimate_strengths(
    results: list[MatchResult], *, shrink: float = SHRINK_MATCHES
) -> tuple[dict[str, TeamStrength], float]:
    """Estimate per-team attack/defense + the league average from results."""
    if not results:
        return {}, DEFAULT_LEAGUE_AVG
    league_avg = sum(r.home_goals + r.away_goals for r in results) / (2 * len(results))
    league_avg = max(league_avg, 0.3)  # floor so we never divide by ~0

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
    for tid, n in played.items():
        # Shrink toward the league average with `shrink` pseudo-matches of form.
        attack = (scored[tid] + shrink * league_avg) / (n + shrink) / league_avg
        defense = (conceded[tid] + shrink * league_avg) / (n + shrink) / league_avg
        strengths[tid] = TeamStrength(attack=attack, defense=defense)
    return strengths, league_avg


def _strength(team_id: str, strengths: dict[str, TeamStrength]) -> TeamStrength:
    return strengths.get(team_id, TeamStrength(attack=1.0, defense=1.0))


def _poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * lam**k / math.factorial(k)


def predict_score(
    home_id: str,
    away_id: str,
    strengths: dict[str, TeamStrength],
    league_avg: float,
    *,
    n_matches: int = 0,
    home_advantage: float = HOME_ADVANTAGE,
    max_goals: int = MAX_GOALS,
) -> ScorePrediction:
    """Modal scoreline + outcome probabilities for one fixture."""
    home, away = _strength(home_id, strengths), _strength(away_id, strengths)
    lam_home = _clip(league_avg * home.attack * away.defense * home_advantage, max_goals)
    lam_away = _clip(league_avg * away.attack * home.defense / home_advantage, max_goals)

    ph = [_poisson_pmf(i, lam_home) for i in range(max_goals + 1)]
    pa = [_poisson_pmf(j, lam_away) for j in range(max_goals + 1)]

    p_home = p_draw = p_away = 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = ph[i] * pa[j]
            if i > j:
                p_home += p
            elif i == j:
                p_draw += p
            else:
                p_away += p
    # Renormalize: the grid is truncated at max_goals, so a sliver of mass is lost.
    total = p_home + p_draw + p_away
    p_home, p_draw, p_away = p_home / total, p_draw / total, p_away / total

    # Scoreline = expected goals rounded, NOT the joint mode. The joint mode of two
    # independent Poissons collapses to 1-1 for any ~1-2 xG match regardless of who's
    # stronger (P(1) is the modal count for lambda in [1,2)), so the mode buried all
    # the team-strength signal under a wall of 1-1s. Rounding the expected goals keeps
    # that signal: 1.95 -> 2, 1.13 -> 1 -> a 2-1, not a 1-1.
    home_goals = min(int(lam_home + 0.5), max_goals)
    away_goals = min(int(lam_away + 0.5), max_goals)
    return ScorePrediction(
        home_goals=home_goals,
        away_goals=away_goals,
        p_home=p_home,
        p_draw=p_draw,
        p_away=p_away,
        lambda_home=lam_home,
        lambda_away=lam_away,
        n_matches=n_matches,
    )


def _clip(lam: float, max_goals: int) -> float:
    return min(max(lam, 0.05), float(max_goals))
