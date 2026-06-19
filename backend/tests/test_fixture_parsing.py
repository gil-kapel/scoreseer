"""Offline parsing tests for both sports adapters — no network, no quota."""

from datetime import UTC

from app.providers.sports_api import ApiFootballProvider, FootballDataProvider

_FOOTBALL_DATA_SAMPLE = {
    "matches": [
        {
            "id": 537882,
            "utcDate": "2026-06-20T16:00:00Z",
            "status": "TIMED",
            "stage": "GROUP_STAGE",
            "group": "GROUP_A",
            "homeTeam": {"id": 759, "name": "Mexico", "tla": "MEX"},
            "awayTeam": {"id": 762, "name": "Canada", "tla": "CAN"},
            "venue": "Estadio Azteca",
        },
        {
            "id": 537999,
            "utcDate": "2026-07-10T19:00:00Z",
            "status": "SCHEDULED",
            "stage": "SEMI_FINALS",
            "group": None,
            "homeTeam": {"id": None, "name": None, "tla": None},  # TBD -> skipped
            "awayTeam": {"id": None, "name": None, "tla": None},
        },
    ]
}

_API_FOOTBALL_SAMPLE = {
    "response": [
        {
            "fixture": {
                "id": 1100,
                "date": "2026-06-21T18:00:00+00:00",
                "venue": {"name": "MetLife Stadium"},
                "status": {"short": "NS"},
            },
            "league": {"id": 1, "season": 2026, "round": "Round of 16"},
            "teams": {"home": {"name": "Brazil"}, "away": {"name": "Argentina"}},
        }
    ]
}


def test_football_data_parse_skips_tbd_and_maps_fields() -> None:
    dtos = FootballDataProvider._parse_matches(_FOOTBALL_DATA_SAMPLE)
    assert len(dtos) == 1  # TBD knockout skipped
    dto = dtos[0]
    assert dto.external_id == "537882"
    assert dto.provider == "football_data"
    assert dto.stage == "group"
    assert (dto.home_code, dto.away_code) == ("MEX", "CAN")
    assert dto.status == "scheduled"
    assert dto.kickoff_utc.tzinfo is not None
    assert dto.kickoff_utc.astimezone(UTC).hour == 16


def test_api_football_parse_maps_round_to_stage() -> None:
    dtos = ApiFootballProvider._parse_fixtures(_API_FOOTBALL_SAMPLE)
    assert len(dtos) == 1
    dto = dtos[0]
    assert dto.external_id == "1100"
    assert dto.provider == "api_football"
    assert dto.stage == "r16"
    assert dto.home_name == "Brazil"
    assert dto.away_code == "ARG"  # derived from name
    assert dto.kickoff_utc.tzinfo is not None
