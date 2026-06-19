"""Sync idempotency test — fake provider, real DB. No network."""

from datetime import UTC, datetime, timedelta

from app.providers.base import FixtureDTO
from app.services import FixtureService, FixtureSyncService


class FakeProvider:
    """In-memory FixturesProvider for deterministic, offline testing."""

    def __init__(self, dtos: list[FixtureDTO]) -> None:
        self._dtos = dtos

    async def list_fixtures(self) -> list[FixtureDTO]:
        return self._dtos


def _dto(ext_id: str, home: str, away: str, hour: int) -> FixtureDTO:
    return FixtureDTO(
        external_id=ext_id,
        provider="football_data",
        stage="group",
        group_label="GROUP_A",
        home_code=home,
        away_code=away,
        home_name=home,
        away_name=away,
        kickoff_utc=datetime(2026, 6, 21, hour, 0, tzinfo=UTC),
        venue="Test Stadium",
        status="scheduled",
    )


async def test_sync_is_idempotent(session) -> None:
    dtos = [_dto("1", "MEX", "CAN", 16), _dto("2", "USA", "PAN", 19)]
    service = FixtureSyncService(session, FakeProvider(dtos))

    first = await service.sync()
    assert first == {"fetched": 2, "created": 2, "updated": 0, "total_fixtures": 2}

    # Re-running with the same data creates nothing new.
    second = await service.sync()
    assert second == {"fetched": 2, "created": 0, "updated": 2, "total_fixtures": 2}


async def test_upcoming_lists_synced_fixtures_within_window(session) -> None:
    # Future kickoff relative to the real clock so it lands inside the window
    # regardless of what "now" is when the test runs.
    soon = datetime.now(UTC) + timedelta(hours=2)
    dto = _dto("10", "BRA", "ARG", 12).model_copy(update={"kickoff_utc": soon})
    await FixtureSyncService(session, FakeProvider([dto])).sync()

    reads = await FixtureService(session).list_upcoming(window_h=24)
    r = next(r for r in reads if r.external_id == "10")
    assert r.home.code == "BRA"
    assert r.prediction_status == "scheduled"
