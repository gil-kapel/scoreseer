"""API-key auth: disabled when no token, enforced when one is set; /health open."""

import httpx
import pytest
import pytest_asyncio
from app.config import get_settings
from app.main import app
from httpx import ASGITransport


@pytest_asyncio.fixture
async def _clear_settings_cache():
    """Keep the lru_cached Settings from leaking a test token into other tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_auth_disabled_when_no_token(session, monkeypatch, _clear_settings_cache) -> None:
    monkeypatch.setenv("API_TOKEN", "")  # explicit: ignore any API_TOKEN in the repo .env
    get_settings.cache_clear()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/dashboard/metrics")
    assert resp.status_code == 200  # no token configured -> open


@pytest.mark.asyncio
async def test_api_key_enforced_when_set(session, monkeypatch, _clear_settings_cache) -> None:
    monkeypatch.setenv("API_TOKEN", "s3cret")
    get_settings.cache_clear()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/health")).status_code == 200  # probe stays open
        assert (await client.get("/api/dashboard/metrics")).status_code == 401  # missing key
        wrong = await client.get("/api/dashboard/metrics", headers={"x-api-key": "nope"})
        assert wrong.status_code == 401
        ok = await client.get("/api/dashboard/metrics", headers={"x-api-key": "s3cret"})
        assert ok.status_code == 200
