"""FixtureService — read-side use-cases for the API (upcoming fixtures)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.estimators import BASELINE_MODEL_IDS
from app.models import Fixture, Grade, Prediction, Result, Team
from app.models.schemas import (
    FixtureRead,
    GradeRead,
    MatchDetail,
    PredictionRead,
    PredictionSummary,
    ResultRead,
    TeamBrief,
)
from app.repositories import GradeRepository, PredictionRepository, ResultRepository


class FixtureService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_upcoming(self, *, window_h: int) -> list[FixtureRead]:
        now = datetime.now(UTC)
        until = now + timedelta(hours=window_h)
        fixtures = list(
            (
                await self.session.execute(
                    select(Fixture)
                    .where(col(Fixture.kickoff_utc) >= now, col(Fixture.kickoff_utc) <= until)
                    .order_by(col(Fixture.kickoff_utc))
                )
            )
            .scalars()
            .all()
        )
        teams = await self._team_map(fixtures)
        preds = await self._prediction_map([f.id for f in fixtures])
        return [self._to_read(f, teams, preds) for f in fixtures]

    async def get_detail(self, fixture_id: uuid.UUID) -> MatchDetail | None:
        fixture = await self.session.get(Fixture, fixture_id)
        if fixture is None:
            return None
        teams = await self._team_map([fixture])
        preds = await self._prediction_map([fixture.id])
        fixture_read = self._to_read(fixture, teams, preds)

        repo = PredictionRepository(self.session)
        # Feature the real LLM prediction (its scoreline, confidence, explanation, and
        # web-search evidence). Baselines are regenerated often, so the newest overall
        # would otherwise be a Poisson/Elo/Naive row — a stub blurb with no evidence.
        all_ok = await repo.all_ok(fixture.id)
        pred = _primary(all_ok)
        sources: list = []
        quality: str | None = None
        if pred is not None and pred.snapshot_id is not None:
            snap = await repo.get_snapshot(pred.snapshot_id)
            if snap is not None:
                sources, quality = snap.sources, snap.data_quality

        result = await ResultRepository(self.session).get(fixture.id)
        # Grade for the DISPLAYED prediction specifically — a fixture now has one grade
        # per estimator, so by_fixture() would raise (multiple rows).
        grade = (
            await GradeRepository(self.session).by_prediction(pred.id)
            if pred is not None
            else None
        )
        # All estimators' predictions for the side-by-side (LLM + the baselines).
        estimators = [_to_prediction_read(p, fixture) for p in all_ok]
        return MatchDetail(
            fixture=fixture_read,
            prediction=_to_prediction_read(pred, fixture) if pred else None,
            estimators=estimators,
            result=_to_result_read(result) if result else None,
            grade=_to_grade_read(grade) if grade else None,
            sources=sources,
            data_quality=quality,
        )

    async def _team_map(self, fixtures: list[Fixture]) -> dict[uuid.UUID, Team]:
        ids = {f.home_team_id for f in fixtures} | {f.away_team_id for f in fixtures}
        if not ids:
            return {}
        rows = (
            await self.session.execute(select(Team).where(col(Team.id).in_(ids)))
        ).scalars().all()
        return {t.id: t for t in rows}

    async def _prediction_map(
        self, fixture_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, Prediction]:
        """Featured OK prediction per fixture: the latest LLM one, else the latest
        baseline (so the list shows your real prediction, not a freshly-regenerated
        Poisson/Elo/Naive)."""
        if not fixture_ids:
            return {}
        rows = (
            await self.session.execute(
                select(Prediction)
                .where(col(Prediction.fixture_id).in_(fixture_ids), col(Prediction.status) == "ok")
                .order_by(col(Prediction.created_at).desc())
            )
        ).scalars().all()
        out: dict[uuid.UUID, Prediction] = {}
        fallback: dict[uuid.UUID, Prediction] = {}
        for p in rows:  # newest first
            bucket = fallback if p.model_id in BASELINE_MODEL_IDS else out
            bucket.setdefault(p.fixture_id, p)
        for fid, p in fallback.items():
            out.setdefault(fid, p)  # a baseline only when no LLM prediction exists
        return out

    @staticmethod
    def _brief(team: Team | None) -> TeamBrief:
        if team is None:
            return TeamBrief(code="TBD", name="TBD")
        return TeamBrief(
            code=team.fifa_code, name=team.name,
            group_label=team.group_label, crest_url=team.crest_url,
        )

    def _to_read(
        self, f: Fixture, teams: dict[uuid.UUID, Team], preds: dict[uuid.UUID, Prediction]
    ) -> FixtureRead:
        pred = preds.get(f.id)
        summary = (
            PredictionSummary(
                home_score=pred.home_score,
                away_score=pred.away_score,
                match_confidence=pred.match_confidence,
                scorers=pred.scorers,
            )
            if pred is not None
            else None
        )
        return FixtureRead(
            id=f.id,
            external_id=f.external_id,
            provider=f.provider,
            stage=f.stage,
            group_label=f.group_label,
            home=self._brief(teams.get(f.home_team_id)),
            away=self._brief(teams.get(f.away_team_id)),
            kickoff_utc=f.kickoff_utc,
            venue=f.venue,
            status=f.status,
            prediction_status="predicted" if pred is not None else "scheduled",
            prediction=summary,
        )


def _primary(predictions: list[Prediction]) -> Prediction | None:
    """The prediction to feature (scoreline, confidence, explanation, evidence): the
    real LLM one if any exists, else the most recent baseline. Baselines are
    regenerated often, so without this the panel would show a baseline's stub text."""
    if not predictions:
        return None
    llm = [p for p in predictions if p.model_id not in BASELINE_MODEL_IDS]
    return max(llm or predictions, key=lambda p: p.created_at)


def _to_prediction_read(pred: Prediction, fixture: Fixture) -> PredictionRead:
    advancing: Literal["home", "away"] | None = None
    if pred.advancing_team_id == fixture.home_team_id:
        advancing = "home"
    elif pred.advancing_team_id == fixture.away_team_id:
        advancing = "away"
    return PredictionRead(
        id=pred.id,
        home_score=pred.home_score,
        away_score=pred.away_score,
        scorers=pred.scorers,
        match_confidence=pred.match_confidence,
        advancing_team=advancing,
        explanation=pred.explanation,
        status=pred.status,
        failure_reason=pred.failure_reason,
        model_id=pred.model_id,
        prompt_version=pred.prompt_version,
        calibration_version=pred.calibration_version,
        # Only the web-search backfill (saw the result) is hindsight; the as-of batch
        # is honest, so it shouldn't wear the "excluded" badge.
        is_backfill=pred.is_backfill and "batch" not in pred.model_id,
        created_at=pred.created_at,
    )


def _to_result_read(result: Result) -> ResultRead:
    return ResultRead(
        home_score_90=result.home_score_90,
        away_score_90=result.away_score_90,
        ft_outcome=result.ft_outcome,
        decided_by=result.decided_by,
        scorers=result.scorers,
        status=result.status,
    )


def _to_grade_read(grade: Grade) -> GradeRead:
    return GradeRead(
        exact_hit=grade.exact_hit,
        outcome_correct=grade.outcome_correct,
        goals_abs_error=grade.goals_abs_error,
        scorer_precision=grade.scorer_precision,
        scorer_recall=grade.scorer_recall,
        scorer_brier=grade.scorer_brier,
        confidence_brier=grade.confidence_brier,
        advancing_correct=grade.advancing_correct,
        points=grade.points,
    )
