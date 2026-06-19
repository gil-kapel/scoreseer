"""Seed varied DEMO predictions so the UI has data to show.

These are NOT real Claude predictions — they're deterministic pseudo-random
guesses (model_id="seed-demo"), clearly labeled in the explanation. Run a real
`predict-fixture` / `run-predict` to get genuine, web-search-grounded predictions.

    cd backend && uv run python scripts/seed_demo.py [upcoming_count]

Seeds every finished fixture (→ gradeable history of prediction-vs-actual) plus
the next N upcoming fixtures (default 12).
"""

import asyncio
import hashlib
import sys

from app.db import dispose_engine, get_sessionmaker
from app.models import Fixture, Prediction, Team
from sqlalchemy import select
from sqlmodel import col


def _h(seed: str, mod: int) -> int:
    return int(hashlib.sha256(seed.encode()).hexdigest(), 16) % mod


async def seed(upcoming_limit: int) -> None:
    sm = get_sessionmaker()
    async with sm() as s:
        fixtures = (
            await s.execute(select(Fixture).order_by(col(Fixture.kickoff_utc)))
        ).scalars().all()
        teams = {t.id: t for t in (await s.execute(select(Team))).scalars().all()}
        created = upcoming = 0
        for f in fixtures:
            if f.status != "finished":
                if upcoming >= upcoming_limit:
                    continue
                upcoming += 1
            existing = (
                await s.execute(
                    select(Prediction).where(
                        col(Prediction.fixture_id) == f.id, col(Prediction.status) == "ok"
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            hs, as_ = _h(f.external_id + "h", 4), _h(f.external_id + "a", 3)
            home, away = teams[f.home_team_id], teams[f.away_team_id]
            scorers = []
            if hs:
                scorers.append({
                    "player_name": f"{home.name} forward", "team": "home",
                    "likelihood": round(0.4 + _h(f.external_id + "hs", 40) / 100, 2),
                })
            if as_:
                scorers.append({
                    "player_name": f"{away.name} forward", "team": "away",
                    "likelihood": round(0.3 + _h(f.external_id + "as", 30) / 100, 2),
                })
            s.add(Prediction(
                fixture_id=f.id, home_score=hs, away_score=as_, scorers=scorers,
                match_confidence=round(0.4 + _h(f.external_id + "c", 40) / 100, 2),
                explanation="Seeded demo prediction (not a real Claude run).",
                model_id="seed-demo", prompt_version="pred-v1", schema_version="out-v1",
                calibration_version=0, status="ok",
            ))
            created += 1
        await s.commit()
        print(f"seeded {created} predictions ({upcoming} upcoming, rest finished)")
    await dispose_engine()


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    asyncio.run(seed(limit))
