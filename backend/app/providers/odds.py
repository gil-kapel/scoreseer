"""the-odds-api.com client — de-vigged World Cup match probabilities.

Powers the Market estimator. Free tier (~500 req/month): we average the h2h (1X2)
prices across bookmakers and strip the overround so probabilities sum to 1.
"""

from dataclasses import dataclass

import httpx

from app.config import logger

_SPORT = "soccer_fifa_world_cup"
_URL = f"https://api.the-odds-api.com/v4/sports/{_SPORT}/odds"


@dataclass(frozen=True)
class MatchOdds:
    home_team: str
    away_team: str
    p_home: float
    p_draw: float
    p_away: float


def _devig_event(ev: dict) -> MatchOdds | None:
    home, away = ev.get("home_team"), ev.get("away_team")
    if not home or not away:
        return None
    hs: list[float] = []
    ds: list[float] = []
    aws: list[float] = []
    for bk in ev.get("bookmakers", []):
        for market in bk.get("markets", []):
            if market.get("key") != "h2h":
                continue
            price = {o.get("name"): o.get("price") for o in market.get("outcomes", [])}
            ph, pd, pa = price.get(home), price.get("Draw"), price.get(away)
            if not (ph and pd and pa):
                continue
            inv = [1.0 / ph, 1.0 / pd, 1.0 / pa]  # decimal odds -> implied prob
            s = sum(inv) or 1.0
            hs.append(inv[0] / s)  # de-vig: normalize out the overround
            ds.append(inv[1] / s)
            aws.append(inv[2] / s)
    if not hs:
        return None
    n = len(hs)
    return MatchOdds(home, away, sum(hs) / n, sum(ds) / n, sum(aws) / n)


class OddsProvider:
    def __init__(self, api_key: str, client: httpx.AsyncClient) -> None:
        self.api_key = api_key
        self.client = client

    async def list_odds(self) -> list[MatchOdds]:
        log = logger.bind(component="OddsProvider")
        resp = await self.client.get(
            _URL,
            params={
                "apiKey": self.api_key,
                "regions": "uk,eu",
                "markets": "h2h",
                "oddsFormat": "decimal",
            },
        )
        if resp.status_code != 200:
            log.warning("odds.http status={} body={}", resp.status_code, resp.text[:160])
            return []
        events = resp.json()
        out = [m for ev in events if (m := _devig_event(ev)) is not None]
        log.info("odds.fetched events={} priced={}", len(events), len(out))
        return out
