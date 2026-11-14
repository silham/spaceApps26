"""Read stored MODIS vegetation composites for a site (consumed by M5 season detection). Owner: M3."""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ftm.data.adapters.modis_gee import QA_PASS, SUMMARY_QA, _acquired
from ftm.db.models import ObservationRow, ProcessingRunRow, SiteRow


class VegetationNotAvailableError(LookupError):
    """No MODIS processing run exists for this site."""


def get_vi_composites(site_id: str, *, session: Session, processing_run_id: str | None = None) -> pd.DataFrame:
    """One row per 16-day composite: ``composite_start, acquired, ndvi, evi, summary_qa, qa_pass, ndvi_flag``.

    ``frame.attrs`` carries ``source_ids`` and ``processing_run_id``. Flagged (snow/cloud) composites are
    included with ``qa_pass=False``; callers filter, the store never drops them.
    """
    run_id, source_id = processing_run_id, None
    for rid, sources in session.execute(
        select(ProcessingRunRow.id, ProcessingRunRow.input_source_ids)
        .where(ProcessingRunRow.site_id == site_id)
        .order_by(ProcessingRunRow.created_at.desc())
    ):
        modis = [s for s in (sources or []) if s.startswith("modis_")]
        if modis and (run_id is None or rid == run_id):
            run_id, source_id = rid, modis[0]
            break
    if source_id is None:
        raise VegetationNotAvailableError(f"no MODIS data stored for site {site_id!r}")

    rows = session.execute(
        select(ObservationRow.observed_at, ObservationRow.variable, ObservationRow.processed_value,
               ObservationRow.raw_value, ObservationRow.quality_flag)
        .where(ObservationRow.processing_run_id == run_id)
    ).all()  # fmt: skip
    long = pd.DataFrame(rows, columns=["observed_at", "variable", "processed_value", "raw_value", "quality_flag"])
    site = session.get(SiteRow, site_id)
    if site is None:
        raise VegetationNotAvailableError(f"unknown site {site_id!r}")
    out = _to_composites(long, ZoneInfo(site.timezone))
    out.attrs.update(site_id=site_id, source_ids=[source_id], processing_run_id=run_id)
    return out


def _to_composites(long: pd.DataFrame, tz: ZoneInfo) -> pd.DataFrame:
    """Pivot stored rows to one row per composite.

    ``observed_at`` was stamped at 00:00 site-local time, but Postgres returns ``timestamptz`` in the
    session zone (UTC), so convert back to the site zone before taking the date; otherwise sites east
    of UTC read every composite one day early.
    """
    long = long.copy()
    long["composite_start"] = [pd.Timestamp(t).tz_convert(tz).date() for t in long["observed_at"]]
    val = long.pivot(index="composite_start", columns="variable", values="processed_value").sort_index()
    flags = long[long.variable == "NDVI"].set_index("composite_start")["quality_flag"]
    sqa = val.get("SummaryQA")
    doy = val.get("DayOfYear")
    out = pd.DataFrame(
        {
            "composite_start": val.index,
            "acquired": [_acquired(s, d) for s, d in zip(val.index, doy, strict=True)] if doy is not None else None,
            "ndvi": val["NDVI"].to_numpy(),
            "evi": val["EVI"].to_numpy(),
            "summary_qa": [SUMMARY_QA.get(int(q), "unknown") if pd.notna(q) else "missing" for q in sqa],
            "qa_pass": [bool(pd.notna(q) and int(q) in QA_PASS) for q in sqa],
            "ndvi_flag": flags.reindex(val.index).to_numpy(),
        }
    ).reset_index(drop=True)
    out.loc[out["ndvi"].isna(), "qa_pass"] = False
    return out


def date_range_of(frame: pd.DataFrame) -> tuple[date, date]:
    return frame["composite_start"].min(), frame["composite_start"].max()
