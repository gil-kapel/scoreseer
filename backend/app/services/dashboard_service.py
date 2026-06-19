"""DashboardService — read-only aggregates for the accuracy lab UI.

All metrics derive from stored Grades (no recompute of grading logic here). The
'calibration improving?' signal is the first-half vs second-half confidence Brier.
"""

import uuid
from itertools import groupby

from sqlalchemy.ext.asyncio import AsyncSession

from app.grading import scoring
from app.models.schemas import (
    CalibrationVersionRead,
    CalibrationView,
    DashboardMetrics,
    EstimatorStats,
    HistoryRow,
    ReliabilityBin,
    StagePoints,
    TrendPoint,
)
from app.repositories import CalibrationRepository, DashboardRepository
from app.repositories.dashboard import GradedRow

_BUCKETS = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]
_STAGE_ORDER = ["group", "r32", "r16", "qf", "sf", "third_place", "final"]


class DashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self.repo = DashboardRepository(session)
        self.calib = CalibrationRepository(session)

    async def metrics(self) -> DashboardMetrics:
        rows = await self.repo.graded(include_backfill=False)
        all_graded = await self.repo.graded(include_backfill=True)
        backfill_excluded = len(all_graded) - len(rows)
        n = len(rows)
        if n == 0:
            return DashboardMetrics(
                n_graded=0, outcome_accuracy=0.0, exact_rate=0.0, goals_mae=0.0,
                scorer_precision=0.0, scorer_recall=0.0, confidence_brier=0.0,
                backfill_excluded=backfill_excluded, trend=[],
            )
        grades = [g for _, _, _, g in rows]
        return DashboardMetrics(
            n_graded=n,
            outcome_accuracy=_mean(g.outcome_correct for g in grades),
            exact_rate=_mean(g.exact_hit for g in grades),
            goals_mae=_mean(g.goals_abs_error for g in grades),
            scorer_precision=_mean(g.scorer_precision for g in grades),
            scorer_recall=_mean(g.scorer_recall for g in grades),
            confidence_brier=_mean(g.confidence_brier for g in grades),
            total_points=sum(g.points for g in grades),
            max_points=sum(scoring.max_points(f.stage) for f, _, _, _ in rows),
            points_by_stage=_points_by_stage(rows),
            backfill_excluded=backfill_excluded,
            trend=_trend(rows),
        )

    async def compare(self) -> list[EstimatorStats]:
        """Per-estimator accuracy (Poisson vs LLM) over the same graded fixtures.

        Honest as-of replays count (Poisson + the as-of batch-LLM); only the
        web-search backfill is dropped as hindsight-poisoned (it saw the result).
        """
        rows = await self.repo.graded(include_backfill=True)
        groups: dict[str, list[GradedRow]] = {}
        for row in rows:
            pred = row[1]
            if pred.is_backfill and "batch" not in pred.model_id:
                continue  # hindsight web-search backfill — excluded
            groups.setdefault(_estimator_name(pred.model_id), []).append(row)

        out: list[EstimatorStats] = []
        for estimator, grows in sorted(groups.items()):
            grades = [g for _, _, _, g in grows]
            out.append(
                EstimatorStats(
                    estimator=estimator,
                    n_graded=len(grades),
                    outcome_accuracy=_mean(g.outcome_correct for g in grades),
                    exact_rate=_mean(g.exact_hit for g in grades),
                    goals_mae=_mean(g.goals_abs_error for g in grades),
                    confidence_brier=_mean(g.confidence_brier for g in grades),
                    total_points=sum(g.points for g in grades),
                    max_points=sum(scoring.max_points(f.stage) for f, _, _, _ in grows),
                )
            )
        return out

    async def calibration(self) -> CalibrationView:
        rows = await self.repo.graded(include_backfill=False)
        profiles = await self.calib.list_all()
        latest = profiles[0] if profiles else None
        first_brier, second_brier = _half_briers(rows)
        return CalibrationView(
            current=_version_read(latest) if latest else None,
            prompt_snippet=latest.prompt_snippet if latest else None,
            metric_aggregates=latest.metric_aggregates if latest else {},
            versions=[_version_read(p) for p in profiles],
            reliability=_reliability(rows),
            first_half_brier=first_brier,
            second_half_brier=second_brier,
        )

    async def history(
        self, *, stage: str | None, outcome: str | None, limit: int
    ) -> list[HistoryRow]:
        # One row per fixture: per-estimator grading now creates one grade per
        # estimator (Poisson + LLM), which would otherwise show as duplicate matches.
        # Show the forward baseline (include_backfill=False) — the per-estimator
        # side-by-side comparison lives on the Estimators page.
        all_rows = await self.repo.graded(stage=stage, include_backfill=False)
        latest: dict[uuid.UUID, GradedRow] = {}
        for row in all_rows:
            fid = row[0].id
            if fid not in latest or row[1].created_at > latest[fid][1].created_at:
                latest[fid] = row
        rows = list(latest.values())
        if outcome == "hit":
            rows = [r for r in rows if r[3].outcome_correct]
        elif outcome == "miss":
            rows = [r for r in rows if not r[3].outcome_correct]
        rows.sort(key=lambda r: r[0].kickoff_utc, reverse=True)  # most recent first
        rows = rows[:limit]

        ids = {f.home_team_id for f, _, _, _ in rows} | {f.away_team_id for f, _, _, _ in rows}
        teams = await self.repo.team_map(ids)
        out = []
        for fixture, pred, result, grade in rows:
            out.append(
                HistoryRow(
                    fixture_id=fixture.id,
                    home=_name(teams, fixture.home_team_id),
                    away=_name(teams, fixture.away_team_id),
                    stage=fixture.stage,
                    group_label=fixture.group_label,
                    kickoff_utc=fixture.kickoff_utc,
                    predicted=f"{pred.home_score}-{pred.away_score}",
                    actual=f"{result.home_score_90}-{result.away_score_90}",
                    exact_hit=grade.exact_hit,
                    outcome_correct=grade.outcome_correct,
                    goals_abs_error=grade.goals_abs_error,
                    points=grade.points,
                    is_backfill=pred.is_backfill,
                )
            )
        return out


def _estimator_name(model_id: str) -> str:
    return "Poisson" if model_id == "poisson-v1" else "LLM"


def _mean(values) -> float:
    items = [float(v) for v in values]
    return round(sum(items) / len(items), 4) if items else 0.0


def _name(teams, team_id) -> str:
    team = teams.get(team_id)
    return team.name if team else "TBD"


def _version_read(p) -> CalibrationVersionRead:
    return CalibrationVersionRead(
        version=p.version, computed_at=p.computed_at, n_graded=p.n_graded,
        bias_summary=p.bias_summary,
    )


def _points_by_stage(rows: list[GradedRow]) -> list[StagePoints]:
    agg: dict[str, dict[str, int]] = {}
    for fixture, _, _, grade in rows:
        b = agg.setdefault(fixture.stage, {"points": 0, "max": 0, "n": 0})
        b["points"] += grade.points
        b["max"] += scoring.max_points(fixture.stage)
        b["n"] += 1
    def _rank(stage: str) -> int:
        return _STAGE_ORDER.index(stage) if stage in _STAGE_ORDER else 99

    ordered = sorted(agg.items(), key=lambda kv: _rank(kv[0]))
    return [
        StagePoints(stage=s, points=v["points"], max_points=v["max"], n=v["n"])
        for s, v in ordered
    ]


def _trend(rows: list[GradedRow]) -> list[TrendPoint]:
    points: list[TrendPoint] = []
    n = outcome = exact = pts = 0
    for date, group in groupby(rows, key=lambda r: r[0].kickoff_utc.date()):
        for _, _, _, grade in group:
            n += 1
            outcome += int(grade.outcome_correct)
            exact += int(grade.exact_hit)
            pts += grade.points
        points.append(
            TrendPoint(
                date=str(date), n=n,
                cumulative_outcome=round(outcome / n, 4),
                cumulative_exact=round(exact / n, 4),
                cumulative_points=pts,
            )
        )
    return points


def _reliability(rows: list[GradedRow]) -> list[ReliabilityBin]:
    bins: list[ReliabilityBin] = []
    for low, high in _BUCKETS:
        members = [(p, g) for _, p, _, g in rows if low <= p.match_confidence < high]
        if not members:
            continue
        bins.append(
            ReliabilityBin(
                bucket=f"{low:.1f}-{min(high, 1.0):.1f}",
                avg_confidence=_mean(p.match_confidence for p, _ in members),
                accuracy=_mean(g.outcome_correct for _, g in members),
                n=len(members),
            )
        )
    return bins


def _half_briers(rows: list[GradedRow]) -> tuple[float | None, float | None]:
    if len(rows) < 4:
        return None, None
    mid = len(rows) // 2
    first = _mean(g.confidence_brier for _, _, _, g in rows[:mid])
    second = _mean(g.confidence_brier for _, _, _, g in rows[mid:])
    return first, second
