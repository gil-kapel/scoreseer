"""BatchBackfillService — LLM predictions on all finished fixtures, in ONE batch.

No web search: the per-fixture brief is each team's as-of form (computed from
results before kickoff), so predictions are hindsight-free and cheap. They're
stored is_backfill=True with their own model id, so they COEXIST with the free
Poisson baseline (different version key) and are excluded from the headline
accuracy — you get an LLM column to compare against Poisson + the real result
without polluting the lab.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.config import logger
from app.models import Fixture, Result, Team
from app.models.schemas import PredictionContext, PredictionOutput
from app.prompts import PROMPT_VERSION, SCHEMA_VERSION
from app.providers.claude_batch import ClaudeBatchPredictor
from app.repositories import CalibrationRepository, PredictionRepository

_KNOCKOUT = {"r32", "r16", "qf", "sf", "final", "third_place"}
# (kickoff, home_team_id, away_team_id, home_goals, away_goals) for every final result.
_History = list[tuple[datetime, uuid.UUID, uuid.UUID, int, int]]


class BatchBackfillService:
    def __init__(self, session: AsyncSession, predictor: ClaudeBatchPredictor) -> None:
        self.session = session
        self.predictor = predictor
        self.repo = PredictionRepository(session)

    async def run(self, *, cap: int | None) -> dict:
        log = logger.bind(component="BatchBackfillService")
        fixtures = await self._finished(cap)
        if not fixtures:
            return {"status": "no_fixtures", "submitted": 0, "stored": 0, "succeeded": 0}
        teams = await self._team_map(fixtures)
        history = await self._all_results()
        profile = await CalibrationRepository(self.session).latest()
        calib_snippet = profile.prompt_snippet if profile else ""
        calib_version = profile.version if profile else 0

        items: list[tuple[str, PredictionContext]] = []
        for fx in fixtures:
            items.append((str(fx.id), self._context(fx, teams, history, calib_snippet)))
        log.info("batch_backfill.submit n={} model={}", len(items), self.predictor.model_id)
        outputs = await self.predictor.predict_many(items)

        model_id = f"{self.predictor.model_id}-batch"
        by_id = {f.id: f for f in fixtures}
        stored = succeeded = 0
        for cid, out in outputs.items():
            fixture = by_id.get(uuid.UUID(cid))
            if fixture is None:
                continue
            home, away = teams[fixture.home_team_id], teams[fixture.away_team_id]
            await self._store(fixture, home, away, out, model_id, calib_version)
            stored += 1
            succeeded += int(out is not None)
        await self.session.commit()
        log.info("batch_backfill.done stored={} ok={}", stored, succeeded)
        return {"status": "done", "submitted": len(items), "stored": stored, "succeeded": succeeded}

    # --- selection / data ---------------------------------------------------
    async def _finished(self, cap: int | None) -> list[Fixture]:
        stmt = (
            select(Fixture)
            .where(col(Fixture.status) == "finished")
            .order_by(col(Fixture.kickoff_utc))
        )
        if cap:
            stmt = stmt.limit(cap)
        return list((await self.session.execute(stmt)).scalars().all())

    async def _team_map(self, fixtures: list[Fixture]) -> dict[uuid.UUID, Team]:
        ids = {f.home_team_id for f in fixtures} | {f.away_team_id for f in fixtures}
        rows = (
            await self.session.execute(select(Team).where(col(Team.id).in_(ids)))
        ).scalars().all()
        return {t.id: t for t in rows}

    async def _all_results(self) -> _History:
        rows = (
            await self.session.execute(
                select(Result, Fixture)
                .join(Fixture, col(Fixture.id) == col(Result.fixture_id))
                .where(col(Result.status) == "final")
            )
        ).all()
        return [
            (fx.kickoff_utc, fx.home_team_id, fx.away_team_id, res.home_score_90, res.away_score_90)
            for res, fx in rows
        ]

    # --- prompt context -----------------------------------------------------
    def _context(
        self, fixture: Fixture, teams: dict[uuid.UUID, Team], history: _History, calib: str
    ) -> PredictionContext:
        home, away = teams[fixture.home_team_id], teams[fixture.away_team_id]
        brief = (
            "Pre-match form in this tournament (only matches before kickoff):\n"
            f"- {self._form_line(home, history, fixture.kickoff_utc)}\n"
            f"- {self._form_line(away, history, fixture.kickoff_utc)}\n"
            "No live web data — base the prediction on this form and the teams' known strength."
        )
        return PredictionContext(
            home_name=home.name,
            away_name=away.name,
            stage=fixture.stage,
            group_label=fixture.group_label,
            kickoff_utc=fixture.kickoff_utc,
            is_knockout=fixture.stage in _KNOCKOUT,
            narrative_summary=brief,
            calibration_snippet=calib,
        )

    @staticmethod
    def _form_line(team: Team, history: _History, before: datetime) -> str:
        played = scored = conceded = 0
        marks: list[str] = []
        for kickoff, home_id, away_id, hg, ag in history:
            if kickoff >= before or team.id not in (home_id, away_id):
                continue
            gf, ga = (hg, ag) if team.id == home_id else (ag, hg)
            played += 1
            scored += gf
            conceded += ga
            marks.append("W" if gf > ga else "D" if gf == ga else "L")
        if played == 0:
            return f"{team.name}: no prior matches yet."
        return (
            f"{team.name}: {played} played, {scored} scored / {conceded} conceded, "
            f"recent {''.join(marks[-5:])}."
        )

    # --- persistence --------------------------------------------------------
    async def _store(
        self,
        fixture: Fixture,
        home: Team,
        away: Team,
        out: PredictionOutput | None,
        model_id: str,
        calibration_version: int,
    ) -> None:
        if out is None:
            fields = dict(
                home_score=0, away_score=0, scorers=[], match_confidence=0.0,
                advancing_team_id=None, explanation="", status="failed",
                failure_reason="batch returned no usable JSON", raw_output=None,
            )
        else:
            advancing = None
            if out.advancing_team == "home":
                advancing = home.id
            elif out.advancing_team == "away":
                advancing = away.id
            fields = dict(
                home_score=out.home_score, away_score=out.away_score,
                scorers=[s.model_dump() for s in out.scorers],
                match_confidence=out.match_confidence, advancing_team_id=advancing,
                explanation=out.explanation, status="ok", failure_reason=None, raw_output=None,
            )
        existing = await self.repo.current(
            fixture_id=fixture.id, prompt_version=PROMPT_VERSION,
            model_id=model_id, calibration_version=calibration_version,
        )
        fields.update(
            snapshot_id=None, is_backfill=True, model_id=model_id,
            prompt_version=PROMPT_VERSION, schema_version=SCHEMA_VERSION,
            calibration_version=calibration_version,
        )
        if existing is not None:
            for key, value in fields.items():
                setattr(existing, key, value)
            await self.session.flush()
        else:
            await self.repo.create_prediction(fixture_id=fixture.id, **fields)
