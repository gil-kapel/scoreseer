"""Single-owner API-key auth.

When `settings.api_token` is empty (the default), auth is DISABLED — local dev,
tests, and the docker-compose stack run open. When it's set (production), every
protected route requires a matching `X-API-Key` header; `/health` stays open so
platform probes work. The frontend injects the key server-side, so the browser
never sees it.
"""

import secrets

from fastapi import Header, HTTPException, status

from app.config import get_settings


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    token = get_settings().api_token
    if not token:
        return  # auth disabled
    if x_api_key is None or not secrets.compare_digest(x_api_key, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-API-Key",
        )
