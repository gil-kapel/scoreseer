"""Unit tests for batch-result parsing (no network)."""

from dataclasses import dataclass
from typing import Any

from app.providers.claude_batch import parse_batch_entry


@dataclass
class _Block:
    type: str
    text: str


@dataclass
class _Message:
    content: list[Any]


@dataclass
class _Result:
    type: str
    message: Any = None


@dataclass
class _Entry:
    custom_id: str
    result: Any


def _entry(text: str, status: str = "succeeded") -> _Entry:
    return _Entry("fix-1", _Result(status, _Message([_Block("text", text)])))


def test_parses_clean_json():
    out = parse_batch_entry(_entry('{"home_score":2,"away_score":1,"scorers":[],'
                                   '"match_confidence":0.6,"advancing_team":null,'
                                   '"explanation":"home edge on form"}'))
    assert out is not None
    assert (out.home_score, out.away_score) == (2, 1)


def test_extracts_json_with_surrounding_prose():
    text = 'Here is my prediction:\n{"home_score":0,"away_score":0,"scorers":[],' \
           '"match_confidence":0.4,"advancing_team":null,' \
           '"explanation":"evenly matched, likely draw"}\nThanks.'
    out = parse_batch_entry(_entry(text))
    assert out is not None
    assert (out.home_score, out.away_score) == (0, 0)


def test_errored_entry_returns_none():
    assert parse_batch_entry(_entry("whatever", status="errored")) is None


def test_garbage_returns_none():
    assert parse_batch_entry(_entry("no json here")) is None
