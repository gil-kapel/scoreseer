"""Versioned prompts + the structured-output JSON schema.

`PROMPT_VERSION` / `SCHEMA_VERSION` are stored on every Prediction so any result
is reproducible and re-gradeable. Bump them when the prompt or schema changes.

The JSON schema given to the Messages API deliberately omits numeric/length
bounds (structured outputs don't support `minimum`/`maximum`/`minLength`); those
are enforced client-side by `PredictionOutput` after parsing.
"""

from datetime import datetime

from app.models.schemas import PredictionContext

PROMPT_VERSION = "pred-v2"
SCHEMA_VERSION = "out-v1"

# Structured-output contract (API-side): types + enums + required only.
PREDICTION_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "home_score": {"type": "integer"},
        "away_score": {"type": "integer"},
        "scorers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "player_name": {"type": "string"},
                    "team": {"type": "string", "enum": ["home", "away"]},
                    "likelihood": {"type": "number"},
                },
                "required": ["player_name", "team", "likelihood"],
                "additionalProperties": False,
            },
        },
        "match_confidence": {"type": "number"},
        "advancing_team": {
            "anyOf": [{"type": "string", "enum": ["home", "away"]}, {"type": "null"}]
        },
        "explanation": {"type": "string"},
    },
    "required": [
        "home_score",
        "away_score",
        "scorers",
        "match_confidence",
        "advancing_team",
        "explanation",
    ],
    "additionalProperties": False,
}


def build_search_prompt(*, home: str, away: str, stage: str, kickoff_utc: datetime) -> str:
    when = kickoff_utc.strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"Research the FIFA World Cup 2026 match {home} vs {away} "
        f"({stage} stage), kicking off {when}. Use web search for current information.\n\n"
        "Write a concise, factual pre-match brief. Cover, with numbers where available:\n"
        "1. Recent form (last 5 results) and goals scored/conceded per game for each team.\n"
        "2. Probable starting XI, plus key injuries or suspensions affecting attack/defense.\n"
        "3. Bookmaker odds: match-winner (1X2) and the over/under 2.5 goals line, and "
        "both-teams-to-score if reported — convert odds to implied probabilities.\n"
        "4. Any market-implied or model expected-goals (xG) figures you can find.\n"
        "5. Head-to-head history and what's at stake (group standings or knockout context).\n\n"
        "Cite your sources. Do NOT predict a score here — just gather the facts and the market."
    )


def build_prediction_prompt(ctx: PredictionContext) -> str:
    stage_rule = (
        "This is a KNOCKOUT match: predict the 90-minute scoreline AND set `advancing_team` "
        "to the side you expect to progress (a draw at 90' is allowed — it would go to extra "
        "time/penalties, but the score you give is the 90-minute line)."
        if ctx.is_knockout
        else "This is a GROUP-STAGE match: a draw is allowed. Leave `advancing_team` null."
    )
    calibration = (
        f"\n\nKnown biases of your past predictions (correct for these):\n{ctx.calibration_snippet}"
        if ctx.calibration_snippet
        else ""
    )
    return (
        f"You are predicting the exact result of {ctx.home_name} (home) vs {ctx.away_name} "
        f"(away), {ctx.stage} stage of the FIFA World Cup 2026.\n\n"
        f"Pre-match brief:\n{ctx.narrative_summary}\n\n"
        "Method: start from each side's expected goals (anchor on bookmaker odds / market "
        "implied probabilities and recent scoring rates from the brief), then adjust for "
        "lineups, injuries and context. Pick the single most likely exact scoreline — not a "
        "safe average.\n"
        "`match_confidence` is the probability (0-1) that your predicted OUTCOME (home win / "
        "draw / away win) is correct — NOT the exact score. A clear favourite should be "
        "0.65-0.85, a tight game 0.40-0.55. Do not output a tiny exact-score probability."
        f"\n\n{stage_rule}{calibration}\n\n"
        "Return your prediction as JSON: the final score, a list of the most likely "
        "goalscorers each with a probability (0-1), an overall match confidence (0-1), and a "
        "short explanation (2-4 sentences) citing the strongest signals (including the odds). "
        "Only list scorers you genuinely expect; an empty list is fine for a predicted 0-0."
    )
