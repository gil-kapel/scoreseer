"""MarketService — persist Market predictions from de-vigged bookmaker odds.

Odds exist only for UPCOMING matches, so Market predicts forward (it can't be
backfilled onto already-played games). Gated on the_odds_api_key; matches odds
events to fixtures by accent-/alias-normalized team names, orientation-agnostic.
"""

import unicodedata
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.config import logger
from app.estimators.market import MarketPrediction, predict_market
from app.models import Fixture, Prediction, Team
from app.providers.odds import MatchOdds, OddsProvider
from app.repositories import PredictionRepository

MARKET_MODEL_ID = "market-v1"
MARKET_VERSION = "market-v1"
_KNOCKOUT_STAGES = {"r32", "r16", "qf", "sf", "final", "third_place"}

# Normalized-name aliases for the handful of teams the odds feed spells differently.
_ALIASES = {
    "czechrepublic": "czechia",
    "capeverde": "capeverdeislands",
    "drcongo": "congodr",
    "congodemocraticrepublic": "congodr",
    "cotedivoire": "ivorycoast",
    "korearepublic": "southkorea",
    "usa": "unitedstates",
    "turkiye": "turkey",
    "bosniaandherzegovina": "bosniaherzegovina",
}


def _norm(name: str) -> str:
    ascii_only = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    key = "".join(ch for ch in ascii_only.lower() if ch.isalnum())
    return _ALIASES.get(key, key)


class MarketService:
    def __init__(self, session: AsyncSession, provider: OddsProvider) -> None:
        self.session = session
        self.provider = provider
        self.repo = PredictionRepository(session)

    async def run(self, *, cap: int | None = None) -> dict:
        log = logger.bind(component="MarketService")
        odds = await self.provider.list_odds()
        if not odds:
            return {"stored": 0, "fetched": 0, "matched": 0}
        index = {frozenset((_norm(o.home_team), _norm(o.away_team))): o for o in odds}

        fixtures = await self._upcoming(cap)
        teams = await self._team_map(fixtures)
        stored = matched = 0
        for fixture in fixtures:
            home = teams.get(fixture.home_team_id)
            away = teams.get(fixture.away_team_id)
            if home is None or away is None:
                continue
            o = index.get(frozenset((_norm(home.name), _norm(away.name))))
            if o is None:
                continue
            matched += 1
            ph, pd, pa = self._orient(home.name, o)
            await self._upsert(fixture, predict_market(ph, pd, pa))
            stored += 1
        log.info("market.run fetched={} matched={} stored={}", len(odds), matched, stored)
        return {"stored": stored, "fetched": len(odds), "matched": matched}

    @staticmethod
    def _orient(our_home: str, o: MatchOdds) -> tuple[float, float, float]:
        # the-odds-api home/away may be flipped vs our fixture; align to OUR home side.
        if _norm(our_home) == _norm(o.home_team):
            return o.p_home, o.p_draw, o.p_away
        return o.p_away, o.p_draw, o.p_home

    async def _upcoming(self, cap: int | None) -> list[Fixture]:
        stmt = (
            select(Fixture)
            .where(col(Fixture.kickoff_utc) > datetime.now(UTC), col(Fixture.status) == "scheduled")
            .order_by(col(Fixture.kickoff_utc))
        )
        if cap:
            stmt = stmt.limit(cap)
        return list((await self.session.execute(stmt)).scalars().all())

    async def _team_map(self, fixtures: list[Fixture]) -> dict:
        ids = {f.home_team_id for f in fixtures} | {f.away_team_id for f in fixtures}
        if not ids:
            return {}
        rows = (
            await self.session.execute(select(Team).where(col(Team.id).in_(ids)))
        ).scalars().all()
        return {t.id: t for t in rows}

    def _advancing(self, fixture: Fixture, outcome: str):
        if fixture.stage not in _KNOCKOUT_STAGES or outcome == "draw":
            return None
        return fixture.home_team_id if outcome == "home" else fixture.away_team_id

    async def _upsert(self, fixture: Fixture, pred: MarketPrediction) -> Prediction:
        explanation = (
            "Market: de-vigged bookmaker odds — "
            f"home/draw/away = {pred.p_home:.0%}/{pred.p_draw:.0%}/{pred.p_away:.0%}. "
            f"Implied {pred.home_goals}–{pred.away_goals} "
            f"(P({pred.outcome})={pred.confidence:.0%})."
        )
        fields = dict(
            snapshot_id=None,
            home_score=pred.home_goals,
            away_score=pred.away_goals,
            scorers=[],
            match_confidence=round(pred.confidence, 3),
            advancing_team_id=self._advancing(fixture, pred.outcome),
            explanation=explanation,
            model_id=MARKET_MODEL_ID,
            prompt_version=MARKET_VERSION,
            schema_version=MARKET_VERSION,
            calibration_version=0,
            is_backfill=False,
            status="ok",
        )
        existing = await self.repo.current(
            fixture_id=fixture.id,
            prompt_version=MARKET_VERSION,
            model_id=MARKET_MODEL_ID,
            calibration_version=0,
        )
        if existing is not None:
            for key, value in fields.items():
                setattr(existing, key, value)
            await self.session.flush()
            return existing
        return await self.repo.create_prediction(fixture_id=fixture.id, **fields)
