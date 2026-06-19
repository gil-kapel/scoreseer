"""Slice 1 acceptance: the app boots and reports DB connectivity.

Requires Postgres running (docker compose up -d) and migrations applied.
"""

import httpx
import pytest
from app.main import app
from httpx import ASGITransport


@pytest.mark.asyncio
async def test_health_ok() -> None:
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": "ok"}
