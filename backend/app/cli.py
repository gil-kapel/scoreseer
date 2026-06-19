"""Management CLI.

    uv run python -m app.cli sync-fixtures             # one live sync (rate-limit friendly)
    uv run python -m app.cli predict-fixture           # predict the earliest upcoming fixture
    uv run python -m app.cli predict-fixture <ext_id>  # predict a specific fixture (external id)

Prefer the CLI over hammering the HTTP endpoints during development.
predict-fixture makes real Claude calls (web search + structured output) — it
incurs API cost, so it predicts exactly one fixture per run.
"""

import argparse
import asyncio
from datetime import UTC, datetime

import httpx
from sqlalchemy import delete, select
from sqlmodel import col

from app.config import configure_logging, get_settings
from app.db import dispose_engine, get_sessionmaker
from app.models import Fixture, Grade, Prediction
from app.providers.claude_factory import claude_adapters
from app.providers.results import build_results_provider
from app.providers.sports_api import build_fixtures_provider
from app.repositories import PredictionRepository
from app.services import (
    CalibrationService,
    FixtureSyncService,
    GradingService,
    PoissonService,
    PredictionService,
)
from app.workers.runner import run_grade, run_predict


async def _sync_fixtures() -> None:
    settings = get_settings()
    async with get_sessionmaker()() as session:
        async with httpx.AsyncClient(timeout=30.0) as client:
            provider = build_fixtures_provider(settings, client)
            summary = await FixtureSyncService(session, provider).sync()
    await dispose_engine()
    print("sync-fixtures:", summary)


async def _earliest_upcoming(session) -> Fixture | None:
    now = datetime.now(UTC)
    return (
        await session.execute(
            select(Fixture)
            .where(col(Fixture.kickoff_utc) >= now)
            .order_by(col(Fixture.kickoff_utc))
            .limit(1)
        )
    ).scalar_one_or_none()


async def _earliest_gradeable(session) -> Fixture | None:
    """Earliest finished fixture that has an OK prediction but no grade yet."""
    rows = (
        await session.execute(
            select(Fixture)
            .join(Prediction, col(Prediction.fixture_id) == col(Fixture.id))
            .where(col(Fixture.status) == "finished", col(Prediction.status) == "ok")
            .order_by(col(Fixture.kickoff_utc))
        )
    ).scalars().all()
    return rows[0] if rows else None


async def _grade_fixture(external_id: str | None) -> None:
    settings = get_settings()
    async with get_sessionmaker()() as session:
        if external_id:
            fixture = (
                await session.execute(
                    select(Fixture).where(col(Fixture.external_id) == external_id)
                )
            ).scalar_one_or_none()
        else:
            fixture = await _earliest_gradeable(session)
        if fixture is None:
            print("grade-fixture: no gradeable fixture found")
            await dispose_engine()
            return
        async with httpx.AsyncClient(timeout=30.0) as client:
            provider = build_results_provider(settings, client)
            result = await GradingService(session, provider).grade_fixture(fixture.id)
    await dispose_engine()
    print("grade-fixture:", result)


async def _predict_fixture(external_id: str | None) -> None:
    settings = get_settings()
    async with get_sessionmaker()() as session:
        if external_id:
            fixture = (
                await session.execute(
                    select(Fixture).where(col(Fixture.external_id) == external_id)
                )
            ).scalar_one_or_none()
        else:
            fixture = await _earliest_upcoming(session)
        if fixture is None:
            print("predict-fixture: no matching fixture found")
            await dispose_engine()
            return
        async with claude_adapters(settings) as (narrative, model):
            service = PredictionService(session, narrative, model)
            result = await service.predict_fixture(fixture.id, model_id=settings.predict_model_id)
    await dispose_engine()
    print("predict-fixture:", result)


async def _run(kind: str) -> None:
    result = await (run_predict("manual") if kind == "predict" else run_grade("manual"))
    await dispose_engine()
    print(f"run-{kind}:", result)


async def _backfill(count: int) -> None:
    """Real LLM predictions on past matches, flagged is_backfill (excluded from calibration)."""
    settings = get_settings()
    async with get_sessionmaker()() as session:
        fixtures = (
            await session.execute(
                select(Fixture)
                .where(col(Fixture.status) == "finished")
                .order_by(col(Fixture.kickoff_utc))
                .limit(count)
            )
        ).scalars().all()
    if not fixtures:
        print("backfill: no finished fixtures")
        await dispose_engine()
        return
    async with claude_adapters(settings) as (narrative, model):
        async with httpx.AsyncClient(timeout=30.0) as client:
            results = build_results_provider(settings, client)
            for fx in fixtures:
                try:
                    # force=True overwrites the seed in place; on a provider error
                    # nothing is written, so the fixture is never left without a prediction.
                    async with get_sessionmaker()() as s:
                        res = await PredictionService(s, narrative, model).predict_fixture(
                            fx.id, model_id=settings.predict_model_id, is_backfill=True, force=True
                        )
                    async with get_sessionmaker()() as s:
                        # re-grade against the new (backfill) prediction
                        await s.execute(delete(Grade).where(col(Grade.fixture_id) == fx.id))
                        await s.commit()
                    async with get_sessionmaker()() as s:
                        g = await GradingService(s, results).grade_fixture(fx.id)
                    print(
                        f"backfill {fx.external_id}: predict={res['status']} "
                        f"{res.get('score')} grade={g['status']}"
                    )
                except Exception as exc:  # noqa: BLE001 — isolate per-fixture failure
                    print(f"backfill {fx.external_id}: FAILED ({str(exc)[:120]})")
    await dispose_engine()


_SEED_MODEL_ID = "seed-demo"


async def _poisson(count: int | None) -> None:
    """Replace random demo seeds with honest Poisson predictions, then grade + calibrate.

    Free (no Claude). Per fixture: drop any `seed-demo` prediction + its grade, then
    — if no real (LLM) prediction remains — create an as-of Poisson prediction. Real
    LLM predictions and the labeled backfill are left untouched.
    """
    created = replaced = kept = 0
    async with get_sessionmaker()() as session:
        stmt = select(Fixture).order_by(col(Fixture.kickoff_utc))
        if count:
            stmt = stmt.limit(count)
        fixtures = (await session.execute(stmt)).scalars().all()
        repo = PredictionRepository(session)
        for fx in fixtures:
            seeds = (
                await session.execute(
                    select(Prediction).where(
                        col(Prediction.fixture_id) == fx.id,
                        col(Prediction.model_id) == _SEED_MODEL_ID,
                    )
                )
            ).scalars().all()
            for seed in seeds:
                await session.execute(delete(Grade).where(col(Grade.prediction_id) == seed.id))
                await session.delete(seed)
                replaced += 1
            await session.flush()
            if await repo.latest_ok(fx.id) is not None:  # a real LLM prediction survives
                kept += 1
                continue
            await PoissonService(session).predict_fixture(fx)
            created += 1
        await session.commit()
    await dispose_engine()
    print(f"poisson: created={created} (replaced {replaced} seeds, kept {kept} real predictions)")
    # Grade the new Poisson predictions and refresh calibration (both free).
    await _run("grade")
    await _calibrate()


async def _calibrate() -> None:
    async with get_sessionmaker()() as session:
        profile = await CalibrationService(session).recompute()
        if profile is not None:
            await session.commit()
    await dispose_engine()
    if profile is None:
        print("calibrate: not enough graded matches yet")
    else:
        print(f"calibrate: v{profile.version} ({profile.n_graded} graded) — {profile.bias_summary}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="scoreseer")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync-fixtures", help="Fetch and upsert WC2026 fixtures (free-first).")
    p_predict = sub.add_parser("predict-fixture", help="Predict one fixture (real Claude calls).")
    p_predict.add_argument("external_id", nargs="?", default=None, help="Fixture external id.")
    p_grade = sub.add_parser("grade-fixture", help="Grade one finished, predicted fixture.")
    p_grade.add_argument("external_id", nargs="?", default=None, help="Fixture external id.")
    sub.add_parser("run-predict", help="Predict-run over eligible upcoming fixtures (capped).")
    sub.add_parser("run-grade", help="Grade-run over finished, predicted fixtures.")
    sub.add_parser("calibrate", help="Recompute the calibration profile from graded matches.")
    p_backfill = sub.add_parser(
        "backfill", help="Real LLM predictions on past matches (labeled, excluded)."
    )
    p_backfill.add_argument("count", type=int, nargs="?", default=3, help="How many past matches.")
    p_poisson = sub.add_parser(
        "poisson", help="Replace demo seeds with free as-of Poisson predictions, grade + calibrate."
    )
    p_poisson.add_argument(
        "count", type=int, nargs="?", default=None, help="Limit fixtures (default: all)."
    )
    args = parser.parse_args()

    configure_logging(level=get_settings().log_level)
    if args.command == "sync-fixtures":
        asyncio.run(_sync_fixtures())
    elif args.command == "predict-fixture":
        asyncio.run(_predict_fixture(args.external_id))
    elif args.command == "grade-fixture":
        asyncio.run(_grade_fixture(args.external_id))
    elif args.command == "run-predict":
        asyncio.run(_run("predict"))
    elif args.command == "run-grade":
        asyncio.run(_run("grade"))
    elif args.command == "calibrate":
        asyncio.run(_calibrate())
    elif args.command == "backfill":
        asyncio.run(_backfill(args.count))
    elif args.command == "poisson":
        asyncio.run(_poisson(args.count))


if __name__ == "__main__":
    main()
