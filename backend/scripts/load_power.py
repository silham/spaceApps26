"""Download (or reuse) NASA POWER daily weather for a site, process it and store it in Postgres.

Usage (from backend/):
  uv run python scripts/load_power.py --site-id cand-kansas --name "Candidate: western Kansas" \
      --lat 37.97 --lon -100.87 --timezone America/Chicago --start 1981-01-01 --end 2025-12-31

Optional: --boundary <GeoJSON> --area-ha <ha> --status "<text>". The default status is "candidate";
never record farmer confirmation that has not happened.
Re-running creates a new ProcessingRun; earlier runs and their rows are kept.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ftm.contracts.models import Site, ValueKind
from ftm.data.adapters import nasa_power
from ftm.data.pipeline.run import AlignContext, run_daily_pipeline
from ftm.data.store import save_pipeline_result, upsert_site, upsert_source
from ftm.db.session import get_engine

PARAMETERS = (*nasa_power.DEFAULT_PARAMETERS, "T2MDEW")


def _multipolygon(path: Path) -> dict[str, Any]:
    """The site boundary column is MULTIPOLYGON: wrap a single Polygon, unwrap a Feature or a one-feature collection."""
    g = json.loads(path.read_text(encoding="utf-8"))
    if g.get("type") == "FeatureCollection":
        if len(g["features"]) != 1:
            raise SystemExit(f"--boundary FeatureCollection must hold exactly one feature, got {len(g['features'])}")
        g = g["features"][0]
    g = g.get("geometry", g)
    if g["type"] == "Polygon":
        return {"type": "MultiPolygon", "coordinates": [g["coordinates"]]}
    if g["type"] != "MultiPolygon":
        raise SystemExit(f"--boundary must be a Polygon or MultiPolygon, got {g['type']}")
    return g


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site-id", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--timezone", required=True, help="IANA timezone, e.g. America/Chicago")
    ap.add_argument("--start", type=date.fromisoformat, required=True)
    ap.add_argument("--end", type=date.fromisoformat, required=True)
    ap.add_argument("--boundary", type=Path, help="GeoJSON file (Polygon/MultiPolygon geometry or Feature)")
    ap.add_argument("--area-ha", type=float, help="Field area in hectares, if known")
    ap.add_argument(
        "--status",
        default="candidate location; primary site (D3) not yet decided",
        help="Short status stored with the site; never claim farmer confirmation that has not happened",
    )
    args = ap.parse_args()

    site = Site(
        id=args.site_id,
        name=args.name,
        latitude=args.lat,
        longitude=args.lon,
        timezone=args.timezone,
        boundary_geojson=_multipolygon(args.boundary) if args.boundary else None,
        area_ha=args.area_ha,
        farmer_context={"status": args.status},
    )
    snap = nasa_power.fetch_daily_cached(args.lat, args.lon, args.start, args.end, PARAMETERS)
    parsed = nasa_power.parse_daily(snap.path.read_bytes())
    source = nasa_power.build_source(nasa_power.source_id_for(snap), snap, parsed)
    result = run_daily_pipeline(
        parsed.observations,
        site_id=site.id,
        source_id=source.id,
        fill_value=parsed.fill_value,
        start=args.start,
        end=args.end,
        value_kind=ValueKind.REANALYSIS,
        align=AlignContext(
            timezone=site.timezone,
            source_time_standard=parsed.time_standard,
            native_resolution=nasa_power.NATIVE_RESOLUTION,
            grid_point=parsed.grid_point,
        ),
    )
    with Session(get_engine()) as s, s.begin():
        upsert_site(s, site)
        upsert_source(s, source)
        s.flush()
        n = save_pipeline_result(s, result)
    print(f"site={site.id} source={source.id} run={result.run.id} observations={n}")
    for stage in result.journey:
        print(f"  {stage.stage.value:<12} {stage.status.value:<8} {stage.summary}")


if __name__ == "__main__":
    main()
