"""ResultsProvider — authoritative final scores + goalscorers (football-data.org).

Uses the match-detail endpoint (`/v4/matches/{id}`), which carries the 90-minute
`fullTime` score, the `duration` (regular / extra time / penalties), the `winner`,
and a best-effort `goals` list. Score-based metrics are reliable; goalscorers are
best-effort (free-tier coverage varies) and degrade gracefully to an empty list.
"""

from typing import Any, Literal

import httpx

from app.config import Settings, logger
from app.providers._http import ProviderUnavailable, fetch_json
from app.providers.base import ActualScorerDTO, ResultDTO

_FOOTBALL_DATA_BASE = "https://api.football-data.org/v4"
_DURATION: dict[str, Literal["regular", "extra_time", "penalties"]] = {
    "REGULAR": "regular",
    "EXTRA_TIME": "extra_time",
    "PENALTY_SHOOTOUT": "penalties",
}
_GOAL_TYPE: dict[str, Literal["goal", "pen", "og"]] = {
    "OWN": "og",
    "PENALTY": "pen",
    "REGULAR": "goal",
}


class FootballDataResultsProvider:
    """`ResultsProvider` over football-data.org match detail."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    async def get_result(self, external_id: str) -> ResultDTO | None:
        if not self._settings.football_data_api_key:
            raise ProviderUnavailable("football_data: no api key")
        data = await fetch_json(
            self._client,
            f"{_FOOTBALL_DATA_BASE}/matches/{external_id}",
            headers={"X-Auth-Token": self._settings.football_data_api_key},
            cache_key=f"fd:match:{external_id}",
        )
        match = data.get("match", data)  # endpoint may wrap in {"match": {...}}
        if match.get("status") != "FINISHED":
            return None
        return self._parse(external_id, match)

    @staticmethod
    def _parse(external_id: str, match: dict) -> ResultDTO:
        score = match.get("score", {})
        ft = score.get("fullTime", {})
        home_id = (match.get("homeTeam") or {}).get("id")
        scorers = _parse_goals(match.get("goals") or [], home_id)
        logger.bind(component="FootballDataResultsProvider").info(
            "result.parsed id={} score={}-{}", external_id, ft.get("home"), ft.get("away")
        )
        return ResultDTO(
            external_id=external_id,
            home_score_90=int(ft.get("home") or 0),
            away_score_90=int(ft.get("away") or 0),
            decided_by=_DURATION.get(score.get("duration", "REGULAR"), "regular"),
            advanced=_winner(score.get("winner")),
            scorers=scorers,
            source_refs=[{"provider": "football_data", "match_id": external_id}],
        )


def _winner(winner: str | None) -> Literal["home", "away"] | None:
    if winner == "HOME_TEAM":
        return "home"
    if winner == "AWAY_TEAM":
        return "away"
    return None


def _parse_goals(goals: list[dict[str, Any]], home_id: Any) -> list[ActualScorerDTO]:
    out: list[ActualScorerDTO] = []
    for g in goals:
        scorer = g.get("scorer") or {}
        name = scorer.get("name")
        if not name:
            continue
        team_id = (g.get("team") or {}).get("id")
        side: Literal["home", "away"] = "home" if team_id == home_id else "away"
        out.append(
            ActualScorerDTO(
                player_name=name,
                team=side,
                type=_GOAL_TYPE.get(g.get("type", "REGULAR"), "goal"),
                minute=g.get("minute"),
            )
        )
    return out


def build_results_provider(
    settings: Settings, client: httpx.AsyncClient
) -> FootballDataResultsProvider:
    return FootballDataResultsProvider(settings, client)
