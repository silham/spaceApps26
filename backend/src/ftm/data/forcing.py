"""Engine-facing accessor for processed daily forcing. Owner: M3, consumed by M4.

Shape (wide, one row per day, index = ``date``):
- ``<VARIABLE>``: processed value in the source's unit (NaN when missing; never 0 for missing).
- ``<VARIABLE>__flag``: quality flag (ok / estimated / missing / rejected / flagged).
- ``frame.attrs``: ``source_ids``, ``processing_run_id``, ``units``, ``site_id``.

Every requested day appears. A day the store has no row for is NaN with flag ``missing``, so the engine
can see the gap instead of silently skipping it. Exactly one weather source per call (guide section 6).
"""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ftm.contracts.models import QualityFlag
from ftm.db.models import ObservationRow, ProcessingRunRow, SiteRow

FLAG_SUFFIX = "__flag"


class ForcingNotAvailableError(LookupError):
    """No processing run exists for this site and source."""


def get_daily_forcing(
    site_id: str,
    start: date,
    end: date,
    weather_source_id: str,
    *,
    session: Session,
    processing_run_id: str | None = None,
) -> pd.DataFrame:
    """Return the processed daily forcing for one site and one weather source.

    Uses the newest ProcessingRun for that site+source unless ``processing_run_id`` pins one, so a
    simulation can record exactly which processed data it used.
    """
    if end < start:
        raise ValueError(f"end ({end}) is before start ({start})")
    site = session.get(SiteRow, site_id)
    if site is None:
        raise ForcingNotAvailableError(f"unknown site {site_id!r}")
    run_id = processing_run_id or _latest_run_id(session, site_id, weather_source_id)
    tz = ZoneInfo(site.timezone)

    rows = session.execute(
        select(
            ObservationRow.observed_at,
            ObservationRow.variable,
            ObservationRow.unit,
            ObservationRow.processed_value,
            ObservationRow.quality_flag,
        ).where(
            ObservationRow.site_id == site_id,
            ObservationRow.source_id == weather_source_id,
            ObservationRow.processing_run_id == run_id,
            ObservationRow.observed_at >= pd.Timestamp(start, tz=tz).to_pydatetime(),
            ObservationRow.observed_at < (pd.Timestamp(end, tz=tz) + pd.Timedelta(days=1)).to_pydatetime(),
        )
    ).all()
    long = pd.DataFrame(rows, columns=["observed_at", "variable", "unit", "processed_value", "quality_flag"])
    long["date"] = [pd.Timestamp(t).tz_convert(tz).date() for t in long["observed_at"]]
    frame = to_wide(long, start, end)
    frame.attrs.update(site_id=site_id, source_ids=[weather_source_id], processing_run_id=run_id)
    return frame


def to_wide(long: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """Pivot ``date, variable, unit, processed_value, quality_flag`` rows to the engine's wide shape."""
    days = pd.Index(pd.date_range(start, end, freq="D").date, name="date")
    units = long.drop_duplicates("variable").set_index("variable")["unit"].to_dict() if len(long) else {}
    if long.empty:
        frame = pd.DataFrame(index=days)
    else:
        values = long.pivot(index="date", columns="variable", values="processed_value").reindex(days)
        flags = long.pivot(index="date", columns="variable", values="quality_flag").reindex(days)
        flags = flags.fillna(QualityFlag.MISSING.value).add_suffix(FLAG_SUFFIX)
        frame = pd.concat([values.astype("float64"), flags], axis=1)
        frame = frame[[c for v in sorted(values.columns) for c in (v, f"{v}{FLAG_SUFFIX}")]]
        frame.columns.name = None
    frame.attrs["units"] = units
    return frame


def _latest_run_id(session: Session, site_id: str, source_id: str) -> str:
    runs = session.execute(
        select(ProcessingRunRow.id, ProcessingRunRow.input_source_ids)
        .where(ProcessingRunRow.site_id == site_id)
        .order_by(ProcessingRunRow.created_at.desc())
    ).all()
    for run_id, sources in runs:
        if source_id in (sources or []):
            return str(run_id)
    raise ForcingNotAvailableError(f"no processed data for site {site_id!r} from source {source_id!r}")
