"""Fetch (or reuse) soil data for an existing site and store its SoilProfile + Source in Postgres.

Usage (from backend/):
  uv run python scripts/load_soil.py --site-id cand-kansas --source ssurgo
  uv run python scripts/load_soil.py --site-id cand-sri-lanka --source soilgrids

SSURGO covers the US only; SoilGrids is global. The site must already exist (see load_power.py).
"""

from __future__ import annotations

import argparse
import json

from sqlalchemy.orm import Session

from ftm.data.adapters import soil_soilgrids, soil_ssurgo
from ftm.data.soil import DEFAULT_DEPTH_M, upsert_soil
from ftm.db.models import SiteRow
from ftm.db.session import get_engine

ADAPTERS = {"ssurgo": soil_ssurgo, "soilgrids": soil_soilgrids}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site-id", required=True)
    ap.add_argument("--source", choices=sorted(ADAPTERS), required=True)
    ap.add_argument("--depth-m", type=float, default=DEFAULT_DEPTH_M)
    args = ap.parse_args()

    adapter = ADAPTERS[args.source]
    with Session(get_engine()) as s, s.begin():
        site = s.get(SiteRow, args.site_id)
        if site is None:
            raise SystemExit(f"Unknown site {args.site_id!r}: load it first with scripts/load_power.py")
        snap = adapter.fetch_cached(site.latitude, site.longitude)
        result = adapter.build(site.id, snap, args.depth_m)
        upsert_soil(s, result)
    awc = result.profile.available_water_capacity_mm_per_m
    print(f"site={args.site_id} source={result.source.id} profile={result.profile.id}")
    print(f"  AWC (0-{args.depth_m:g} m): {awc.value} {awc.unit}")
    print(f"  bounds: low={result.awc_low_mm_per_m} high={result.awc_high_mm_per_m}")
    print(f"  texture: {result.profile.texture}")
    print(f"  uncertainty: {awc.uncertainty}")
    print("  details:", json.dumps(result.details, default=str)[:800])


if __name__ == "__main__":
    main()
