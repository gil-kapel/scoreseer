"""Read-only join over graded matches for the dashboard + history."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.estimators import BASELINE_MODEL_IDS
from app.models import Fixture, Grade, Prediction, Result, Team

GradedRow = tuple[Fixture, Prediction, Result, Grade]


class DashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def graded(
        self,
        *,
        stage: str | None = None,
        outcome: str | None = None,
        limit: int | None = None,
        include_backfill: bool = True,
        estimator: str | None = None,
    ) -> list[GradedRow]:
        """All (fixture, prediction, final result, grade) rows, ordered by kickoff.

        `include_backfill=False` drops HINDSIGHT predictions (the web-search backfill
        that saw the result); the honest as-of batch-LLM still counts.
        `estimator="llm"` = every model that ISN'T a statistical baseline (Poisson /
        Elo / Naive); any other value filters to that exact model_id.
        """
        stmt = (
            select(Fixture, Prediction, Result, Grade)
            .join(Grade, col(Grade.fixture_id) == col(Fixture.id))
            .join(Prediction, col(Grade.prediction_id) == col(Prediction.id))
            .join(Result, col(Result.fixture_id) == col(Fixture.id))
            .where(col(Result.status) == "final")
            .order_by(col(Fixture.kickoff_utc))
        )
        if not include_backfill:
            # Hindsight = a backfill prediction that ISN'T the as-of batch (i.e. it used
            # web search and saw the result). The honest as-of batch-LLM is kept.
            stmt = stmt.where(
                col(Prediction.is_backfill).is_(False) | col(Prediction.model_id).like("%batch%")
            )
        if estimator == "llm":
            stmt = stmt.where(col(Prediction.model_id).not_in(BASELINE_MODEL_IDS))
        elif estimator is not None:
            stmt = stmt.where(col(Prediction.model_id) == estimator)
        if stage:
            stmt = stmt.where(col(Fixture.stage) == stage)
        if outcome == "hit":
            stmt = stmt.where(col(Grade.outcome_correct).is_(True))
        elif outcome == "miss":
            stmt = stmt.where(col(Grade.outcome_correct).is_(False))
        if limit:
            stmt = stmt.limit(limit)
        rows = (await self.session.execute(stmt)).all()
        return [(r[0], r[1], r[2], r[3]) for r in rows]

    async def recent_llm_predictions(self, limit: int) -> list[tuple[Prediction, Fixture]]:
        """Newest OK LLM predictions with an explanation (the Insights feed source)."""
        stmt = (
            select(Prediction, Fixture)
            .join(Fixture, col(Fixture.id) == col(Prediction.fixture_id))
            .where(
                col(Prediction.status) == "ok",
                col(Prediction.model_id).not_in(BASELINE_MODEL_IDS),
                col(Prediction.explanation) != "",
            )
            .order_by(col(Prediction.created_at).desc())
            .limit(limit * 3)  # over-fetch; the service dedups to one per fixture
        )
        rows = (await self.session.execute(stmt)).all()
        return [(r[0], r[1]) for r in rows]

    async def team_map(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, Team]:
        if not ids:
            return {}
        rows = (
            await self.session.execute(select(Team).where(col(Team.id).in_(ids)))
        ).scalars().all()
        return {t.id: t for t in rows}
