"""Repositories for Team and Fixture (data access only — no business logic)."""

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models import Fixture, Team

_FIXTURE_MUTABLE = (
    "stage", "group_label", "kickoff_utc", "venue", "status", "provider", "external_id",
)


class TeamRepository:
    """Get-or-create teams keyed by FIFA/3-letter code."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create(
        self,
        *,
        fifa_code: str,
        name: str,
        group_label: str | None = None,
        crest_url: str | None = None,
    ) -> Team:
        existing = (
            await self.session.execute(select(Team).where(col(Team.fifa_code) == fifa_code))
        ).scalar_one_or_none()
        if existing is not None:
            if group_label and existing.group_label != group_label:
                existing.group_label = group_label
            if crest_url and not existing.crest_url:
                existing.crest_url = crest_url
            return existing
        team = Team(fifa_code=fifa_code, name=name, group_label=group_label, crest_url=crest_url)
        self.session.add(team)
        await self.session.flush()
        return team


class FixtureRepository:
    """Idempotent fixture upserts + read queries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _find(
        self, *, provider: str, external_id: str, home_id: uuid.UUID, away_id: uuid.UUID
    ) -> Fixture | None:
        # Primary identity: (provider, external_id). Fallback: natural key (home, away).
        by_ext = (
            await self.session.execute(
                select(Fixture).where(
                    col(Fixture.provider) == provider, col(Fixture.external_id) == external_id
                )
            )
        ).scalar_one_or_none()
        if by_ext is not None:
            return by_ext
        return (
            await self.session.execute(
                select(Fixture).where(
                    col(Fixture.home_team_id) == home_id, col(Fixture.away_team_id) == away_id
                )
            )
        ).scalar_one_or_none()

    async def upsert(
        self, *, values: dict, home_id: uuid.UUID, away_id: uuid.UUID
    ) -> tuple[Fixture, bool]:
        """Insert or update a fixture. Returns (fixture, created)."""
        existing = await self._find(
            provider=values["provider"],
            external_id=values["external_id"],
            home_id=home_id,
            away_id=away_id,
        )
        if existing is not None:
            for field in _FIXTURE_MUTABLE:
                if field in values:
                    setattr(existing, field, values[field])
            return existing, False
        fixture = Fixture(home_team_id=home_id, away_team_id=away_id, **values)
        self.session.add(fixture)
        await self.session.flush()
        return fixture, True

    async def list_upcoming(self, *, now: datetime, until: datetime) -> list[Fixture]:
        result = await self.session.execute(
            select(Fixture)
            .where(col(Fixture.kickoff_utc) >= now, col(Fixture.kickoff_utc) <= until)
            .order_by(col(Fixture.kickoff_utc))
        )
        return list(result.scalars().all())

    async def count(self) -> int:
        return (await self.session.execute(select(func.count()).select_from(Fixture))).scalar_one()
