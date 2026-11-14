"""NASA POWER adapter tests. Uses a mocked transport: no network, no DB."""

import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from ftm.contracts.models import ValueKind
from ftm.data.adapters import nasa_power
from ftm.provenance import sha256_bytes

PAYLOAD = {
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [-100.5, 38.5, 850.0]},
    "properties": {
        "parameter": {
            "PRECTOTCORR": {"20240101": 0.0, "20240102": -999.0, "20240103": 2.4},
            "T2M_MAX": {"20240101": 5.1, "20240102": 6.3, "20240103": -999.0},
        }
    },
    "header": {
        "api": {"version": "v2.x-test"},
        "sources": ["MERRA2"],
        "fill_value": -999.0,
    },
    "messages": [],
    "parameters": {
        "PRECTOTCORR": {"units": "mm/day", "longname": "Precipitation Corrected"},
        "T2M_MAX": {"units": "C", "longname": "Temperature at 2 Meters Maximum"},
    },
}
CONTENT = json.dumps(PAYLOAD).encode()


def _client(
    status: int = 200, content: bytes = CONTENT, seen: list[httpx.Request] | None = None
) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, content=content)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_request_params() -> None:
    params = nasa_power.build_request_params(
        38.5, -100.5, date(2024, 1, 1), date(2024, 1, 3), ["T2M_MAX"]
    )
    assert params["start"] == "20240101" and params["end"] == "20240103"
    assert params["community"] == "AG" and params["format"] == "JSON"


@pytest.mark.parametrize(
    "args",
    [
        (91, 0, date(2024, 1, 1), date(2024, 1, 2), ["X"]),
        (0, 0, date(2024, 1, 2), date(2024, 1, 1), ["X"]),
        (0, 0, date(2024, 1, 1), date(2024, 1, 2), []),
    ],
)
def test_request_params_rejects_bad_input(args: tuple) -> None:  # type: ignore[type-arg]
    with pytest.raises(ValueError):
        nasa_power.build_request_params(*args)


def test_fetch_saves_raw_bytes_unchanged(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    snap = nasa_power.fetch_daily(
        38.5,
        -100.5,
        date(2024, 1, 1),
        date(2024, 1, 3),
        client=_client(seen=seen),
        raw_dir=tmp_path / "raw",
    )
    assert snap.path.read_bytes() == CONTENT
    assert snap.sha256 == sha256_bytes(CONTENT)
    assert seen[0].url.params["parameters"] == ",".join(nasa_power.DEFAULT_PARAMETERS)


def test_fetch_http_error_writes_nothing(tmp_path: Path) -> None:
    with pytest.raises(httpx.HTTPStatusError):
        nasa_power.fetch_daily(
            0,
            0,
            date(2024, 1, 1),
            date(2024, 1, 2),
            client=_client(status=500),
            raw_dir=tmp_path / "raw",
        )
    assert not (tmp_path / "raw").exists()


def test_parse_keeps_fill_values_raw() -> None:
    parsed = nasa_power.parse_daily(CONTENT)
    obs = parsed.observations
    assert len(obs) == 6
    assert parsed.fill_value == -999.0
    rain_day2 = obs[
        (obs.variable == "PRECTOTCORR") & (obs.date_key == "20240102")
    ].raw_value.item()
    assert rain_day2 == -999.0  # decoding is the QA step's job, not the adapter's
    # A real zero rainfall stays zero; it is distinguishable from missing.
    assert (
        obs[
            (obs.variable == "PRECTOTCORR") & (obs.date_key == "20240101")
        ].raw_value.item()
        == 0.0
    )
    assert parsed.units == {"PRECTOTCORR": "mm/day", "T2M_MAX": "C"}
    assert parsed.grid_point == (-100.5, 38.5)


def test_parse_requires_fill_value() -> None:
    bad = {**PAYLOAD, "header": {"api": {}}}
    with pytest.raises(nasa_power.PowerResponseError):
        nasa_power.parse_daily(json.dumps(bad).encode())


def test_parse_rejects_non_json() -> None:
    with pytest.raises(nasa_power.PowerResponseError):
        nasa_power.parse_daily(b"<html>maintenance</html>")


def test_build_source_metadata(tmp_path: Path) -> None:
    snap = nasa_power.fetch_daily(
        38.5,
        -100.5,
        date(2024, 1, 1),
        date(2024, 1, 3),
        client=_client(),
        raw_dir=tmp_path / "raw",
    )
    src = nasa_power.build_source(
        "src_power_test", snap, nasa_power.parse_daily(CONTENT)
    )
    assert src.kind == ValueKind.REANALYSIS
    assert src.coverage_start == date(2024, 1, 1) and src.coverage_end == date(
        2024, 1, 3
    )
    assert src.raw_sha256 == snap.sha256 and src.raw_path == snap.relative_path
    assert src.units["PRECTOTCORR"] == "mm/day"
    assert src.attribution and "POWER" in src.attribution
