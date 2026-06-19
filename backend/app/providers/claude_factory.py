"""Build the Claude adapters (shared by route + CLI)."""

from contextlib import asynccontextmanager

from anthropic import AsyncAnthropic

from app.config import Settings
from app.providers.claude_predict import ClaudePredictionModel
from app.providers.claude_search import ClaudeNarrativeProvider


@asynccontextmanager
async def claude_adapters(settings: Settings):
    """Yield (narrative, model) backed by one AsyncAnthropic client."""
    async with AsyncAnthropic(api_key=settings.anthropic_api_key) as client:
        yield ClaudeNarrativeProvider(settings, client), ClaudePredictionModel(settings, client)
