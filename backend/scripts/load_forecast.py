"""Fetch (or reuse today's) ECMWF SEAS5 seasonal forecast for an existing site via Open-Meteo (D16).

Usage (from backend/):
  uv run python scripts/load_forecast.py --site-id <site>

Stores the raw daily-member and monthly-anomaly responses unchanged, a Source row and a ForecastSnapshot row.
The forecast never becomes weather in the water balance: it only weights past NASA POWER years.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from ftm.data.adapters import forecast_openmeteo as fo
from ftm.data.store import upsert_source
from ftm.db.models import ForecastSnapshotRow, SiteRow
from ftm.db.session import get_engine


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site-id", required=True)
    args = ap.parse_args()

    today = datetime.now(UTC).date()
    # From the start of last month: the window may begin there when POWER lags into a new month; days the
    # forecast does not cover come back empty and those months are simply not used.
    start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    end = today + timedelta(days=fo.MAX_FORECAST_DAYS - 1)
    with Session(get_engine()) as s, s.begin():
        site = s.get(SiteRow, args.site_id)
        if site is None:
            raise SystemExit(f"Unknown site {args.site_id!r}: load it first with scripts/load_power.py")
        daily, monthly = fo.fetch_cached(site.latitude, site.longitude, start, end)
        fc = fo.load(daily, monthly)
        source = fo.build_source(fo.source_id_for(daily, monthly), daily, monthly, fc)
        upsert_source(s, source)
        s.flush()
        snap_id = f"fcs_{site.id}_{source.id}"[:64]
        if s.get(ForecastSnapshotRow, snap_id) is None:
            days = fc.daily["precipitation_sum"].dropna(how="all").index
            s.add(
                ForecastSnapshotRow(
                    id=snap_id,
                    site_id=site.id,
                    source_id=source.id,
                    retrieved_at=daily.retrieved_at,
                    forecast_start=days.min().date(),
                    forecast_end=days.max().date(),
                    n_members=fc.n_members,
                    monthly_raw_path=monthly.relative_path,
                    monthly_raw_sha256=monthly.sha256,
                )
            )
    print(f"site={args.site_id} source={source.id} members={fc.n_members} snapshot={snap_id}")


if __name__ == "__main__":
    main()
