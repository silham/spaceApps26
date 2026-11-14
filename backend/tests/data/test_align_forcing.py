"""Align step and forcing reshaping tests (no DB)."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfoNotFoundError

import numpy as np
import pandas as pd
import pytest

from ftm.data.forcing import FLAG_SUFFIX, to_wide
from ftm.data.pipeline.align import align_daily


def _df(dates: list[date]) -> pd.DataFrame:
    return pd.DataFrame({"date": dates, "variable": "T2M_MAX", "unit": "C", "processed_value": 1.0})


def _align(df: pd.DataFrame, tz: str = "UTC") -> tuple[pd.DataFrame, object]:
    return align_daily(df, timezone=tz, source_time_standard="LST", native_resolution="0.5 deg", grid_point=None)


def test_align_stamps_local_midnight_with_timezone() -> None:
    out, step = _align(_df([date(2024, 1, 1), date(2024, 7, 1)]), "America/Chicago")
    ts = out["observed_at"].tolist()
    assert all(isinstance(t, datetime) and t.tzinfo is not None for t in ts)
    assert ts[0].hour == 0 and ts[0].utcoffset() == timedelta(hours=-6)  # CST
    assert ts[1].utcoffset() == timedelta(hours=-5)  # CDT: daylight saving handled by zoneinfo
    assert step.params["source_day_definition"] == "LST"  # type: ignore[attr-defined]
    assert step.params["resampling"].startswith("none")  # type: ignore[attr-defined]


def test_align_keeps_leap_day_and_row_count() -> None:
    out, step = _align(_df([date(2024, 2, 28), date(2024, 2, 29), date(2024, 3, 1)]))
    assert len(out) == 3
    assert step.params["leap_day_rows"] == 1  # type: ignore[attr-defined]


def test_align_rejects_unknown_timezone() -> None:
    with pytest.raises(ZoneInfoNotFoundError):
        _align(_df([date(2024, 1, 1)]), "Mars/Olympus")


def _row(day: int, var: str, unit: str, value: float | None, flag: str) -> dict[str, object]:
    return {"date": date(2024, 1, day), "variable": var, "unit": unit, "processed_value": value, "quality_flag": flag}


def _long() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _row(1, "PRECTOTCORR", "mm/day", 0.0, "ok"),
            _row(2, "PRECTOTCORR", "mm/day", None, "missing"),
            _row(1, "T2M_MAX", "C", 5.0, "ok"),
            _row(2, "T2M_MAX", "C", 6.0, "estimated"),
        ]
    )


def test_to_wide_keeps_missing_rain_as_nan_with_flag() -> None:
    wide = to_wide(_long(), date(2024, 1, 1), date(2024, 1, 2))
    assert wide.loc[date(2024, 1, 1), "PRECTOTCORR"] == 0.0  # a real zero stays zero
    assert np.isnan(wide.loc[date(2024, 1, 2), "PRECTOTCORR"])
    assert wide.loc[date(2024, 1, 2), "PRECTOTCORR" + FLAG_SUFFIX] == "missing"
    assert wide.loc[date(2024, 1, 2), "T2M_MAX" + FLAG_SUFFIX] == "estimated"
    assert wide.attrs["units"] == {"PRECTOTCORR": "mm/day", "T2M_MAX": "C"}


def test_to_wide_adds_absent_days_as_missing() -> None:
    wide = to_wide(_long(), date(2024, 1, 1), date(2024, 1, 4))
    assert list(wide.index) == [date(2024, 1, d) for d in range(1, 5)]
    assert wide.loc[date(2024, 1, 4), "T2M_MAX" + FLAG_SUFFIX] == "missing"
    assert np.isnan(wide.loc[date(2024, 1, 4), "T2M_MAX"])
