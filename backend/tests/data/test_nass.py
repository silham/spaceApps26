"""NASS Crop Progress parsing and 50 % date interpolation (no network)."""

import json
from datetime import date

import pytest

from ftm.data.adapters import nass_quickstats as n


def _payload(rows: list[tuple[str, str, str]]) -> bytes:
    return json.dumps(
        {"data": [{"year": d[:4], "week_ending": d, "Value": v, "short_desc": s} for d, v, s in rows]}
    ).encode()


ROWS = [
    ("2018-04-22", "15", "CORN - PROGRESS, MEASURED IN PCT PLANTED"),
    ("2018-04-29", "27", "CORN - PROGRESS, MEASURED IN PCT PLANTED"),
    ("2018-05-06", "47", "CORN - PROGRESS, MEASURED IN PCT PLANTED"),
    ("2018-05-13", "67", "CORN - PROGRESS, MEASURED IN PCT PLANTED"),
]


def test_parse_and_interpolate_50_pct() -> None:
    df = n.parse(_payload(ROWS))
    assert list(df.pct) == [15, 27, 47, 67]
    # 47 -> 67 between 6 and 13 May: 3/20 of 7 days = ~1 day after 6 May
    assert n.date_at_pct(df, 2018, 50) == date(2018, 5, 7)


def test_not_bracketed_returns_none() -> None:
    df = n.parse(_payload(ROWS[2:]))
    assert n.date_at_pct(df, 2018, 40) is None  # first report already above
    assert n.date_at_pct(df, 2018, 90) is None  # never reached


def test_api_error_and_empty_raise() -> None:
    with pytest.raises(n.NassError):
        n.parse(b'{"error": ["bad request"]}')
    with pytest.raises(n.NassError):
        n.parse(b'{"data": []}')
