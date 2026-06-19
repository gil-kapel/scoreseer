"""PredictionService — orchestrates fetch → snapshot → predict → store.

Append-only and reproducible: every Prediction records its snapshot, model id,
prompt/schema version, and calibration version. Failures are stored visibly
(status="failed") rather than dropped.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import logger
from app.models import Fixture, Team
from app.models.schemas import PredictionContext
from app.prompts import PROMPT_VERSION, SCHEMA_VERSION
from app.providers.base import NarrativeProvider, PredictionModel
from app.repositories import CalibrationRepository, PredictionRepository

_KNOCKOUT_STAGES = {"r32", "r16", "qf", "sf", "final", "third_place"}


class PredictionService:
    def __init__(
        self, session: AsyncSession, narrative: NarrativeProvider, model: PredictionModel
    ) -> None:
        self.session = session
        self.narrative = narrative
        self.model = model
        self.repo = PredictionRepository(session)

    async def predict_fixture(
        self, fixture_id: uuid.UUID, *, model_id: str, is_backfill: bool = False,
        force: bool = False,
    ) -> dict:
        log = logger.bind(component="PredictionService", fixture_id=str(fixture_id))
        log.info("predict.init")
        fixture = await self.session.get(Fixture, fixture_id)
        if fixture is None:
            return {"status": "not_found"}

        # Idempotent on (fixture, prompt, model) — calibration changes don't force a
        # re-predict. `force` (used by backfill) overwrites the latest prediction in
        # place; on a provider error nothing is written, so no fixture is orphaned.
        existing_ok = await self.repo.latest_ok_for(fixture_id, PROMPT_VERSION, model_id)
        if existing_ok is not None and not force:
            log.info("predict.skip already_predicted prediction_id={}", existing_ok.id)
            return {"status": "skipped", "prediction_id": str(existing_ok.id)}

        profile = await CalibrationRepository(self.session).latest()
        calibration_version = profile.version if profile else 0
        calibration_snippet = profile.prompt_snippet if profile else ""
        if force:
            existing = existing_ok or await self.repo.latest(fixture_id)
        else:
            # A prior FAILED attempt at this same calibration version is retried in place.
            existing = await self.repo.current(
                fixture_id=fixture_id, prompt_version=PROMPT_VERSION,
                model_id=model_id, calibration_version=calibration_version,
            )

        home, away = await self._teams(fixture)
        is_knockout = fixture.stage in _KNOCKOUT_STAGES
        log.info("predict.search_start {} vs {} ({})", home.name, away.name, fixture.stage)
        bundle = await self.narrative.fetch_pre_match(
            home=home.name, away=away.name, kickoff_utc=fixture.kickoff_utc, stage=fixture.stage
        )
        log.info(
            "predict.search_done sources={} quality={}",
            len(bundle.sources), bundle.data_quality,
        )
        snapshot = await self.repo.create_snapshot(fixture_id=fixture_id, bundle=bundle)

        context = PredictionContext(
            home_name=home.name,
            away_name=away.name,
            stage=fixture.stage,
            group_label=fixture.group_label,
            kickoff_utc=fixture.kickoff_utc,
            is_knockout=is_knockout,
            narrative_summary=bundle.evidence.get("summary", ""),
            calibration_snippet=calibration_snippet,
        )
        log.info("predict.model_start model={} knockout={}", model_id, is_knockout)
        attempt = await self.model.predict(context)
        prediction = await self._store(
            fixture, snapshot.id, home, away, attempt, model_id,
            existing=existing, calibration_version=calibration_version, is_backfill=is_backfill,
        )
        await self.session.commit()
        log.info(
            "predict.stored status={} score={}-{} confidence={}",
            prediction.status, prediction.home_score, prediction.away_score,
            prediction.match_confidence,
        )
        return {
            "status": prediction.status,
            "prediction_id": str(prediction.id),
            "score": f"{prediction.home_score}-{prediction.away_score}",
            "failure_reason": prediction.failure_reason,
        }

    async def _teams(self, fixture: Fixture) -> tuple[Team, Team]:
        home = await self.session.get(Team, fixture.home_team_id)
        away = await self.session.get(Team, fixture.away_team_id)
        assert home is not None and away is not None  # FK guarantees existence
        return home, away

    async def _store(
        self, fixture, snapshot_id, home, away, attempt, model_id, existing,
        calibration_version, is_backfill,
    ):
        if attempt.output is None:
            fields = dict(
                home_score=0, away_score=0, scorers=[], match_confidence=0.0,
                advancing_team_id=None, explanation="", status="failed",
                failure_reason=attempt.failure_reason, raw_output=attempt.raw_output,
            )
        else:
            out = attempt.output
            fields = dict(
                home_score=out.home_score, away_score=out.away_score,
                scorers=[s.model_dump() for s in out.scorers],
                match_confidence=out.match_confidence,
                advancing_team_id=_advancing_team_id(out.advancing_team, home, away),
                explanation=out.explanation, status="ok", failure_reason=None, raw_output=None,
            )
        fields["snapshot_id"] = snapshot_id
        fields["is_backfill"] = is_backfill
        fields["model_id"] = model_id
        fields["prompt_version"] = PROMPT_VERSION
        fields["schema_version"] = SCHEMA_VERSION
        fields["calibration_version"] = calibration_version
        if existing is not None:  # overwrite in place (failed retry or forced backfill)
            for key, value in fields.items():
                setattr(existing, key, value)
            await self.session.flush()
            return existing
        return await self.repo.create_prediction(fixture_id=fixture.id, **fields)


def _advancing_team_id(side: str | None, home: Team, away: Team) -> uuid.UUID | None:
    if side == "home":
        return home.id
    if side == "away":
        return away.id
    return None
