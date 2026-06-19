"""Shared test fixtures.

Tests run against a DEDICATED `scoreseer_test` database (NOT the dev DB), so the
suite can truncate freely without wiping demo/dev data. The env override below
must run before app settings are first read.
"""

import os

os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://scoreseer:scoreseer@127.0.0.1:5433/scoreseer_test"
)

import app.models  # noqa: E402, F401 — registers tables on SQLModel.metadata
import pytest_asyncio  # noqa: E402
from app.db import dispose_engine, get_engine, get_sessionmaker  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _engine_per_test():
    """Dispose the global engine after each test so connections never outlive their loop."""
    yield
    await dispose_engine()


@pytest_asyncio.fixture
async def session():
    """A clean AsyncSession on the test DB — schema rebuilt to match current models."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    async with get_sessionmaker()() as s:
        yield s
