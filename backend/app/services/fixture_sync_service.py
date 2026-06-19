"""FixtureSyncService — upsert WC2026 fixtures from a FixturesProvider.

Idempotent: re-running upserts in place (no duplicates). Decoupled from any
specific provider (takes a `FixturesProvider`) so it is testable with a fake.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import logger
from app.providers.base import FixtureDTO, FixturesProvider
from app.repositories import FixtureRepository, TeamRepository


class FixtureSyncService:
    def __init__(self, session: AsyncSession, provider: FixturesProvider) -> None:
        self.session = session
        self.provider = provider
        self.teams = TeamRepository(session)
        self.fixtures = FixtureRepository(session)

    async def sync(self) -> dict[str, int]:
        log = logger.bind(component="FixtureSyncService")
        log.info("sync.init")
        dtos = await self.provider.list_fixtures()
        created = updated = 0
        for dto in dtos:
            created_one = await self._upsert_one(dto)
            created += int(created_one)
            updated += int(not created_one)
        await self.session.commit()
        summary = {
            "fetched": len(dtos),
            "created": created,
            "updated": updated,
            "total_fixtures": await self.fixtures.count(),
        }
        log.info("sync.exit {}", summary)
        return summary

    async def _upsert_one(self, dto: FixtureDTO) -> bool:
        home = await self.teams.get_or_create(
            fifa_code=dto.home_code, name=dto.home_name,
            group_label=dto.group_label, crest_url=dto.home_crest,
        )
        away = await self.teams.get_or_create(
            fifa_code=dto.away_code, name=dto.away_name,
            group_label=dto.group_label, crest_url=dto.away_crest,
        )
        values = {
            "external_id": dto.external_id,
            "provider": dto.provider,
            "stage": dto.stage,
            "group_label": dto.group_label,
            "kickoff_utc": dto.kickoff_utc,
            "venue": dto.venue,
            "status": dto.status,
        }
        _, created = await self.fixtures.upsert(values=values, home_id=home.id, away_id=away.id)
        return created
