"""Repository for Run / RunItem + eligible-fixture selection for runs."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models import Fixture, Grade, Prediction, Run, RunItem


class RunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_run(self, *, type_: str, trigger: str, params: dict) -> Run:
        run = Run(type=type_, trigger=trigger, status="running", params=params)
        self.session.add(run)
        await self.session.flush()
        return run

    async def add_item(
        self, *, run_id: uuid.UUID, fixture_id: uuid.UUID, status: str, detail: str | None = None
    ) -> RunItem:
        item = RunItem(run_id=run_id, fixture_id=fixture_id, status=status, detail=detail)
        self.session.add(item)
        await self.session.flush()
        return item

    async def finalize(self, run: Run, *, status: str, totals: dict) -> None:
        run.status = status
        run.totals = totals
        run.finished_at = datetime.now(UTC)
        await self.session.flush()

    async def list_runs(self, *, limit: int = 50) -> list[Run]:
        return list(
            (
                await self.session.execute(
                    select(Run).order_by(col(Run.started_at).desc()).limit(limit)
                )
            )
            .scalars()
            .all()
        )

    async def items(self, run_id: uuid.UUID) -> list[RunItem]:
        return list(
            (
                await self.session.execute(
                    select(RunItem).where(col(RunItem.run_id) == run_id)
                )
            )
            .scalars()
            .all()
        )

    async def eligible_for_prediction(
        self, *, window_h: int, model_id: str, prompt_version: str, cap: int
    ) -> list[uuid.UUID]:
        now = datetime.now(UTC)
        until = now + timedelta(hours=window_h)
        # Any OK prediction at this prompt+model counts as done (calibration version
        # is recorded for provenance but does not force a re-predict).
        already = select(col(Prediction.fixture_id)).where(
            col(Prediction.status) == "ok",
            col(Prediction.prompt_version) == prompt_version,
            col(Prediction.model_id) == model_id,
        )
        rows = (
            await self.session.execute(
                select(col(Fixture.id))
                .where(
                    col(Fixture.status) == "scheduled",
                    col(Fixture.kickoff_utc) >= now,
                    col(Fixture.kickoff_utc) <= until,
                    ~col(Fixture.id).in_(already),
                )
                .order_by(col(Fixture.kickoff_utc))
                .limit(cap)
            )
        ).scalars().all()
        return list(rows)

    async def eligible_for_backfill(self, *, cap: int) -> list[uuid.UUID]:
        """Finished fixtures not yet backfilled (no is_backfill prediction yet)."""
        backfilled = select(col(Prediction.fixture_id)).where(col(Prediction.is_backfill).is_(True))
        rows = (
            await self.session.execute(
                select(col(Fixture.id))
                .where(col(Fixture.status) == "finished", ~col(Fixture.id).in_(backfilled))
                .order_by(col(Fixture.kickoff_utc))
                .limit(cap)
            )
        ).scalars().all()
        return list(rows)

    async def eligible_for_grading(self, *, cap: int) -> list[uuid.UUID]:
        # Per-estimator: a fixture is eligible if ANY of its OK predictions lacks a grade
        # (by prediction id, not just by fixture) — so a newly-added estimator gets graded
        # even when another estimator on the same fixture already was.
        graded_pred_ids = select(col(Grade.prediction_id))
        with_ungraded = select(col(Prediction.fixture_id)).where(
            col(Prediction.status) == "ok",
            ~col(Prediction.id).in_(graded_pred_ids),
        )
        rows = (
            await self.session.execute(
                select(col(Fixture.id))
                .where(
                    col(Fixture.status) == "finished",
                    col(Fixture.id).in_(with_ungraded),
                )
                .order_by(col(Fixture.kickoff_utc))
                .limit(cap)
            )
        ).scalars().all()
        return list(rows)
