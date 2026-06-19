"""Structured sports-data adapters (authoritative fixtures/results).

Two providers, used **free-first** via `CompositeFixturesProvider`:
  1. football-data.org  (primary; gives 3-letter team codes + clean stages)
  2. API-Football       (fallback)

Parsing is isolated in pure `_parse_*` staticmethods so it is unit-tested
offline against recorded JSON — no network, no quota burned.
"""

from datetime import datetime

import httpx

from app.config import Settings, logger
from app.providers._http import ProviderUnavailable, fetch_json
from app.providers.base import FixtureDTO

_FOOTBALL_DATA_BASE = "https://api.football-data.org/v4"
_API_FOOTBALL_BASE = "https://v3.football.api-sports.io"

# football-data stage/status -> internal vocab.
_FD_STAGE = {
    "GROUP_STAGE": "group",
    "LAST_32": "r32",
    "LAST_16": "r16",
    "QUARTER_FINALS": "qf",
    "SEMI_FINALS": "sf",
    "THIRD_PLACE": "third_place",
    "FINAL": "final",
}
_FD_STATUS = {
    "SCHEDULED": "scheduled",
    "TIMED": "scheduled",
    "IN_PLAY": "live",
    "PAUSED": "live",
    "FINISHED": "finished",
    "AWARDED": "finished",
    "POSTPONED": "postponed",
    "SUSPENDED": "abandoned",
    "CANCELLED": "abandoned",
}
_AF_STATUS = {
    "NS": "scheduled", "TBD": "scheduled",
    "1H": "live", "HT": "live", "2H": "live", "ET": "live", "BT": "live", "P": "live",
    "LIVE": "live",
    "FT": "finished", "AET": "finished", "PEN": "finished",
    "PST": "postponed",
    "CANC": "abandoned", "ABD": "abandoned", "AWD": "abandoned", "WO": "abandoned",
}


def _code_from_name(name: str) -> str:
    """Best-effort 3-letter code when a provider omits one (API-Football fixtures)."""
    letters = "".join(c for c in name.upper() if c.isalpha())
    return (letters[:3] or "TBD").ljust(3, "X")


class FootballDataProvider:
    """`FixturesProvider` over football-data.org."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    async def list_fixtures(self) -> list[FixtureDTO]:
        if not self._settings.football_data_api_key:
            raise ProviderUnavailable("football_data: no api key")
        code = self._settings.football_data_competition
        data = await fetch_json(
            self._client,
            f"{_FOOTBALL_DATA_BASE}/competitions/{code}/matches",
            headers={"X-Auth-Token": self._settings.football_data_api_key},
            cache_key=f"fd:matches:{code}",
        )
        return self._parse_matches(data)

    @staticmethod
    def _parse_matches(data: dict) -> list[FixtureDTO]:
        out: list[FixtureDTO] = []
        for m in data.get("matches", []):
            home, away = m.get("homeTeam") or {}, m.get("awayTeam") or {}
            if not home.get("tla") or not away.get("tla"):
                continue  # team not decided yet (knockout TBD) — skip
            out.append(
                FixtureDTO(
                    external_id=str(m["id"]),
                    provider="football_data",
                    stage=_FD_STAGE.get(m.get("stage", ""), (m.get("stage") or "group").lower()),
                    group_label=m.get("group"),
                    home_code=home["tla"],
                    away_code=away["tla"],
                    home_name=home.get("name") or home["tla"],
                    away_name=away.get("name") or away["tla"],
                    home_crest=home.get("crest"),
                    away_crest=away.get("crest"),
                    kickoff_utc=datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00")),
                    venue=m.get("venue"),
                    status=_FD_STATUS.get(m.get("status", ""), "scheduled"),
                )
            )
        return out


class ApiFootballProvider:
    """`FixturesProvider` over API-Football (api-sports.io direct)."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    async def list_fixtures(self) -> list[FixtureDTO]:
        if not self._settings.api_football_key:
            raise ProviderUnavailable("api_football: no api key")
        league, season = self._settings.api_football_league, self._settings.api_football_season
        data = await fetch_json(
            self._client,
            f"{_API_FOOTBALL_BASE}/fixtures",
            headers={"x-apisports-key": self._settings.api_football_key},
            params={"league": league, "season": season},
            cache_key=f"af:fixtures:{league}:{season}",
        )
        return self._parse_fixtures(data)

    @staticmethod
    def _parse_fixtures(data: dict) -> list[FixtureDTO]:
        out: list[FixtureDTO] = []
        for item in data.get("response", []):
            fx, teams = item.get("fixture", {}), item.get("teams", {})
            home, away = teams.get("home") or {}, teams.get("away") or {}
            if not home.get("name") or not away.get("name"):
                continue
            round_name = (item.get("league") or {}).get("round", "")
            out.append(
                FixtureDTO(
                    external_id=str(fx["id"]),
                    provider="api_football",
                    stage=_stage_from_round(round_name),
                    group_label=_group_from_round(round_name),
                    home_code=_code_from_name(home["name"]),
                    away_code=_code_from_name(away["name"]),
                    home_name=home["name"],
                    away_name=away["name"],
                    home_crest=home.get("logo"),
                    away_crest=away.get("logo"),
                    kickoff_utc=datetime.fromisoformat(fx["date"]),
                    venue=(fx.get("venue") or {}).get("name"),
                    status=_AF_STATUS.get((fx.get("status") or {}).get("short", ""), "scheduled"),
                )
            )
        return out


def _stage_from_round(round_name: str) -> str:
    r = round_name.lower()
    if "group" in r:
        return "group"
    if "32" in r:
        return "r32"
    if "16" in r:
        return "r16"
    if "quarter" in r:
        return "qf"
    if "semi" in r:
        return "sf"
    if "3rd" in r or "third" in r:
        return "third_place"
    if "final" in r:
        return "final"
    return "group"


def _group_from_round(round_name: str) -> str | None:
    # "Group Stage - 1" carries no group letter here; group is derived elsewhere if needed.
    return round_name if round_name.lower().startswith("group") else None


class CompositeFixturesProvider:
    """Tries providers in free-first order; first non-empty result wins."""

    def __init__(self, providers: list[tuple[str, object]]) -> None:
        self._providers = providers  # [(name, FixturesProvider)]

    async def list_fixtures(self) -> list[FixtureDTO]:
        log = logger.bind(component="provider")
        last_error: Exception | None = None
        for name, provider in self._providers:
            try:
                fixtures = await provider.list_fixtures()  # type: ignore[attr-defined]
                if fixtures:
                    log.info("provider.selected name={} fixtures={}", name, len(fixtures))
                    return fixtures
                log.warning("provider.empty name={}", name)
            except ProviderUnavailable as exc:
                log.warning("provider.unavailable name={} reason={}", name, exc)
                last_error = exc
        if last_error is not None:
            raise last_error
        return []


def build_fixtures_provider(
    settings: Settings, client: httpx.AsyncClient
) -> CompositeFixturesProvider:
    """Wire the composite from `settings.provider_order` (free-first)."""
    factory = {
        "football_data": lambda: FootballDataProvider(settings, client),
        "api_football": lambda: ApiFootballProvider(settings, client),
    }
    chain = [(name, factory[name]()) for name in settings.provider_order if name in factory]
    return CompositeFixturesProvider(chain)
