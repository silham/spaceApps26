"""MODIS MOD13Q1 adapter tests with a fake Earth Engine getRegion result (no credentials, no network)."""

import json
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ftm.data.adapters import modis_gee as m

HEADER = ["id", "longitude", "latitude", "time", "NDVI", "EVI", "SummaryQA", "DetailedQA", "DayOfYear"]


def _rows() -> list[list[object]]:
    return [
        HEADER,
        ["2024_01_01", -100.87, 37.97, 1704067200000, 2500, 1500, 0, 2116, 5],  # good
        ["2024_01_17", -100.87, 37.97, 1705449600000, 2600, 1600, 1, 2117, 20],  # marginal
        ["2024_02_02", -100.87, 37.97, 1706832000000, 900, 500, 2, 18432, 35],  # snow/ice
        ["2024_02_18", -100.87, 37.97, 1708214400000, -3000, -3000, 3, 3, 49],  # cloudy + fill
        ["2024_03_05", -100.87, 37.97, 1709596800000, 12000, 1700, 0, 2116, 66],  # NDVI out of range
        ["2024_12_18", -100.87, 37.97, 1734480000000, 2000, 1200, 0, 2116, 2],  # acquired next January
    ]


def _fake_region(lat: float, lon: float, start: date, end: date) -> list[list[object]]:
    return _rows()


def _snapshot(tmp_path: Path):  # type: ignore[no-untyped-def]
    return m.fetch_cached(
        37.97, -100.87, date(2024, 1, 1), date(2024, 12, 31), raw_dir=tmp_path / "raw", region_fn=_fake_region
    )


def test_fetch_caches_and_reuses(tmp_path: Path) -> None:
    calls: list[int] = []

    def counting(*a: object) -> list[list[object]]:
        calls.append(1)
        return _rows()

    a = m.fetch_cached(
        37.97, -100.87, date(2024, 1, 1), date(2024, 12, 31), raw_dir=tmp_path / "raw", region_fn=counting
    )
    b = m.fetch_cached(
        37.97, -100.87, date(2024, 1, 1), date(2024, 12, 31), raw_dir=tmp_path / "raw", region_fn=counting
    )
    assert len(calls) == 1 and a.sha256 == b.sha256
    stored = json.loads(a.path.read_bytes())
    assert stored["result"] == _rows()  # Earth Engine's answer kept exactly
    assert stored["request"]["collection"] == "MODIS/061/MOD13Q1"


def test_parse_keeps_raw_integers(tmp_path: Path) -> None:
    parsed = m.parse(_snapshot(tmp_path).path.read_bytes())
    ndvi = parsed.observations.query("variable == 'NDVI'")
    assert ndvi.raw_value.tolist()[:2] == [2500.0, 2600.0]
    assert parsed.pixel_center_lon_lat == (-100.87, 37.97)


def test_process_scales_flags_and_never_drops(tmp_path: Path) -> None:
    parsed = m.parse(_snapshot(tmp_path).path.read_bytes())
    obs, comp, step = m.process(parsed.observations)
    assert len(comp) == 6  # every composite kept
    c = comp.set_index("composite_start")
    assert c.loc[date(2024, 1, 1), "ndvi"] == pytest.approx(0.25)
    assert c.loc[date(2024, 1, 1), "qa_pass"] and c.loc[date(2024, 1, 17), "qa_pass"]  # good + marginal
    assert not c.loc[date(2024, 2, 2), "qa_pass"] and c.loc[date(2024, 2, 2), "ndvi"] == pytest.approx(0.09)
    assert c.loc[date(2024, 2, 2), "ndvi_flag"] == "flagged"  # snow: kept, flagged
    assert np.isnan(c.loc[date(2024, 2, 18), "ndvi"]) and c.loc[date(2024, 2, 18), "ndvi_flag"] == "missing"
    assert c.loc[date(2024, 3, 5), "ndvi_flag"] == "rejected" and not c.loc[date(2024, 3, 5), "qa_pass"]
    raw = obs[obs.variable == "NDVI"].raw_value.tolist()
    assert raw[3] == -3000.0 and raw[4] == 12000.0  # raw values untouched
    assert step.params["qa_pass"] == 3 and step.params["missing"] == 2 and step.params["rejected"] == 1


def test_acquisition_date_wraps_into_next_year(tmp_path: Path) -> None:
    _, comp, _ = m.process(m.parse(_snapshot(tmp_path).path.read_bytes()).observations)
    c = comp.set_index("composite_start")
    assert c.loc[date(2024, 1, 17), "acquired"] == date(2024, 1, 20)
    assert c.loc[date(2024, 12, 18), "acquired"] == date(2025, 1, 2)


def test_decode_detailed_qa_bits() -> None:
    q = m.decode_detailed_qa(0b1100_0100_0000_0101)  # vi_quality 1, usefulness 1, mixed clouds, snow, shadow
    assert q["vi_quality"] == 1 and q["usefulness"] == 1
    assert q["mixed_clouds"] == 1 and q["possible_snow_ice"] == 1 and q["possible_shadow"] == 1
    assert q["adjacent_cloud"] == 0


def test_parse_rejects_empty_and_missing_bands() -> None:
    with pytest.raises(m.ModisError):
        m.parse(json.dumps({"result": [HEADER]}).encode())
    with pytest.raises(m.ModisError):
        m.parse(json.dumps({"result": [["id", "NDVI"], ["2024_01_01", 1]]}).encode())


def test_missing_project_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from ftm.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("EE_PROJECT", "")
    with pytest.raises(m.ModisError, match="EE_PROJECT"):
        m._ee_region(0, 0, date(2024, 1, 1), date(2024, 1, 2))
    get_settings.cache_clear()


def test_vi_reader_keeps_composite_dates_east_of_utc() -> None:
    """Postgres returns timestamptz in UTC; local midnight in Asia/Colombo is the previous UTC day."""
    from datetime import UTC
    from zoneinfo import ZoneInfo

    from ftm.data.vegetation import _to_composites

    tz = ZoneInfo("Asia/Colombo")
    rows = []
    for day, ndvi in ((date(2024, 1, 1), 0.61), (date(2024, 1, 17), 0.64)):
        stored = datetime.combine(day, datetime.min.time(), tzinfo=tz).astimezone(UTC)
        for var, value in (
            ("NDVI", ndvi),
            ("EVI", 0.4),
            ("SummaryQA", 0.0),
            ("DayOfYear", float(day.timetuple().tm_yday)),
        ):
            rows.append({"observed_at": stored, "variable": var, "processed_value": value, "raw_value": value,
                         "quality_flag": "ok"})  # fmt: skip
    out = _to_composites(pd.DataFrame(rows), tz)
    assert list(out["composite_start"]) == [date(2024, 1, 1), date(2024, 1, 17)]
    assert list(out["acquired"]) == [date(2024, 1, 1), date(2024, 1, 17)]
    assert out["qa_pass"].all()
