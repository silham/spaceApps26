"""Pipeline step: align (Data Journey stage "Align"). Owner: M3.

Gives every daily value a timezone-aware timestamp for the site, and records how the source's day
relates to it. Nothing is resampled or interpolated here: a daily gridded source stays daily and stays
at its native grid resolution (DEVELOPMENT_GUIDE.md section 6: alignment must not imply field detail).
"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pandas as pd

from ftm.contracts.models import ProcessingStep


def align_daily(
    df: pd.DataFrame,
    *,
    timezone: str,
    source_time_standard: str | None,
    native_resolution: str | None,
    grid_point: tuple[float, float] | None,
) -> tuple[pd.DataFrame, ProcessingStep]:
    """Add ``observed_at``: 00:00 local civil time of each value's date in the site's IANA ``timezone``.

    The source's own day definition (e.g. POWER's local solar time) is recorded, not converted:
    daily totals cannot be re-split into civil days without sub-daily data.
    """
    tz = ZoneInfo(timezone)  # raises for an unknown zone: never fall back silently
    out = df.copy()
    out["observed_at"] = [datetime.combine(d, time(0), tzinfo=tz) for d in _as_dates(out["date"])]
    leap_days = int(sum(1 for d in _as_dates(out["date"]) if d.month == 2 and d.day == 29))
    step = ProcessingStep(
        name="align",
        params={
            "timezone": timezone,
            "timestamp_rule": "00:00 site-local civil time of the source's calendar date",
            "source_day_definition": source_time_standard or "not stated by source",
            "resampling": "none (source is already daily)",
            "native_resolution": native_resolution,
            "grid_point_lon_lat": list(grid_point) if grid_point else None,
            "leap_days": "kept as delivered",
            "leap_day_rows": leap_days,
        },
        affected_count=len(out),
        reason=(
            "Stamped each daily value with the site's timezone. Values keep the source's own day "
            "definition and native grid resolution; nothing was resampled."
        ),
    )
    return out, step


def _as_dates(values: pd.Series) -> list[date]:
    return [v if isinstance(v, date) and not isinstance(v, datetime) else pd.Timestamp(v).date() for v in values]
