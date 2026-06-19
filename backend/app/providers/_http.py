"""Rate-limit-aware JSON fetch for sports providers.

Free tiers are stingy (football-data.org ~10 req/min; API-Football ~100 req/day),
so this helper:
  * caches successful responses on disk with a TTL (repeated dev/test runs are free),
  * honors HTTP 429 `Retry-After` with bounded retries,
  * raises `ProviderUnavailable` on exhaustion so the composite can fall back.
"""

import asyncio
import hashlib
import json
import time
from pathlib import Path

import httpx

from app.config import get_settings, logger

_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "providers"


class ProviderUnavailable(Exception):
    """Provider could not serve the request (rate limited, error, or down)."""


def _cache_path(key: str) -> Path:
    digest = hashlib.sha256(key.encode()).hexdigest()[:24]
    return _CACHE_DIR / f"{digest}.json"


def _read_cache(key: str, ttl: int) -> dict | None:
    if ttl <= 0:
        return None
    path = _cache_path(key)
    if not path.exists() or (time.time() - path.stat().st_mtime) > ttl:
        return None
    logger.bind(component="http").debug("cache.hit key={}", key)
    return json.loads(path.read_text())


def _write_cache(key: str, data: dict) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(key).write_text(json.dumps(data))


def _retry_after_seconds(resp: httpx.Response) -> float:
    raw = resp.headers.get("Retry-After")
    try:
        return min(float(raw), 60.0) if raw else 6.0
    except ValueError:
        return 6.0


async def fetch_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    cache_key: str,
    params: dict | None = None,
    max_retries: int = 2,
) -> dict:
    ttl = get_settings().http_cache_ttl_seconds
    cached = _read_cache(cache_key, ttl)
    if cached is not None:
        return cached

    log = logger.bind(component="http")
    for attempt in range(max_retries + 1):
        resp = await client.get(url, headers=headers, params=params)
        if resp.status_code == 429:
            wait = _retry_after_seconds(resp)
            log.warning("http.rate_limited url={} attempt={} wait={}s", url, attempt, wait)
            if attempt < max_retries:
                await asyncio.sleep(wait)
                continue
            raise ProviderUnavailable(f"rate limited after {max_retries} retries: {url}")
        if resp.status_code >= 400:
            raise ProviderUnavailable(f"{resp.status_code} from {url}: {resp.text[:200]}")
        data = resp.json()
        _write_cache(cache_key, data)
        log.debug("http.ok url={} status={}", url, resp.status_code)
        return data
    raise ProviderUnavailable(f"unreachable: {url}")  # pragma: no cover
