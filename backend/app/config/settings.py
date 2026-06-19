"""Typed application settings (pydantic-settings).

Loaded once at boot and validated; missing required secrets fail fast.
Both sports-data providers are configured here — the provider layer (Slice 2)
tries the free plans first and falls back between them.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo-root .env, resolved absolutely so it loads regardless of CWD
# (CLI/alembic/uvicorn all run from backend/, but .env lives at the repo root).
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Database ---
    database_url: str = Field(
        default="postgresql+asyncpg://scoreseer:scoreseer@127.0.0.1:5433/scoreseer",
        description="Async SQLAlchemy URL (asyncpg driver). Host port 5433 -> container 5432.",
    )

    # --- Claude / Anthropic (narrative web search + structured prediction) ---
    anthropic_api_key: str = Field(default="", description="Anthropic API key.")
    predict_model_id: str = Field(default="claude-opus-4-8", description="Reasoning model.")
    format_model_id: str = Field(default="claude-sonnet-4-6", description="Fetch/format model.")

    # --- Sports data providers (authoritative fixtures + results). Use BOTH, free-first. ---
    football_data_api_key: str = Field(default="", description="football-data.org token (free).")
    api_football_key: str = Field(default="", description="API-Football key (free).")
    sports_provider_order: str = Field(
        default="football_data,api_football",
        description="Comma-separated free-first provider preference order.",
    )
    # Competition selectors (WC2026).
    football_data_competition: str = Field(default="WC", description="football-data.org code.")
    api_football_league: int = Field(default=1, description="API-Football league id (1=World Cup).")
    api_football_season: int = Field(default=2026, description="API-Football season year.")

    # Rate-limit friendliness: cache provider responses on disk during dev.
    http_cache_ttl_seconds: int = Field(default=21600, ge=0, description="0 disables the cache.")

    # --- Prediction scheduling defaults (overridable via Config row) ---
    prediction_window_hours: int = Field(default=24, ge=1, le=72)
    per_run_fixture_cap: int = Field(default=20, ge=1)

    # --- Scheduler (APScheduler in-process). OFF by default to avoid surprise spend. ---
    scheduler_enabled: bool = Field(default=False, description="Run predict/grade jobs on a timer.")
    predict_interval_hours: int = Field(default=24, ge=1, description="Predict-run cadence.")
    grade_interval_hours: int = Field(default=6, ge=1, description="Grade-run cadence.")

    # --- Runtime ---
    environment: str = Field(default="development", description="development | production.")
    log_level: str = Field(default="INFO")

    # --- Security (single-owner). Empty = auth disabled (local dev + tests). When set,
    # every API route except /health requires a matching `X-API-Key` header. ---
    api_token: str = Field(default="", description="Shared API key required when non-empty.")

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def provider_order(self) -> list[str]:
        return [p.strip() for p in self.sports_provider_order.split(",") if p.strip()]

    def redacted(self) -> dict[str, object]:
        """Config summary safe to log — secrets masked."""

        def mask(v: str) -> str:
            return f"set({len(v)})" if v else "unset"

        return {
            "environment": self.environment,
            "database_url": self.database_url.split("@")[-1],  # drop credentials
            "predict_model_id": self.predict_model_id,
            "format_model_id": self.format_model_id,
            "provider_order": self.provider_order,
            "anthropic_api_key": mask(self.anthropic_api_key),
            "football_data_api_key": mask(self.football_data_api_key),
            "api_football_key": mask(self.api_football_key),
            "api_token": mask(self.api_token),
            "auth_enabled": bool(self.api_token),
            "prediction_window_hours": self.prediction_window_hours,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
