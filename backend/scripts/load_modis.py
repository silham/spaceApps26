"""Extract (or reuse) MODIS MOD13Q1 NDVI/EVI for an existing site via Earth Engine and store it.

Usage (from backend/, after Earth Engine sign-in and EE_PROJECT in .env):
  uv run python scripts/load_modis.py --site-id cand-kansas
  uv run python scripts/load_modis.py --site-id cand-sri-lanka --start 2000-02-18 --end 2025-12-31

Re-running reuses the cached raw extraction and creates a new ProcessingRun; earlier runs are kept.
"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from ftm.contracts.models import ProcessingRun
from ftm.data.adapters import modis_gee
from ftm.data.pipeline.align import align_daily
from ftm.data.pipeline.run import PipelineResult
from ftm.data.store import save_pipeline_result, upsert_source
from ftm.db.models import SiteRow
from ftm.db.session import get_engine
from ftm.provenance import new_id

PIPELINE_VERSION = "modis-0.1.0"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site-id", required=True)
    ap.add_argument("--start", type=date.fromisoformat, default=date(2000, 2, 18))  # first MOD13Q1 composite
    ap.add_argument("--end", type=date.fromisoformat, default=date(2025, 12, 31))
    args = ap.parse_args()

    with Session(get_engine()) as s, s.begin():
        site = s.get(SiteRow, args.site_id)
        if site is None:
            raise SystemExit(f"Unknown site {args.site_id!r}: load it first with scripts/load_power.py")
        lat, lon, tz = site.latitude, site.longitude, site.timezone

    snap = modis_gee.fetch_cached(lat, lon, args.start, args.end)
    parsed = modis_gee.parse(snap.path.read_bytes())
    source = modis_gee.build_source(snap, parsed)
    obs, composites, qa_step = modis_gee.process(parsed.observations)
    obs, align_step = align_daily(
        obs,
        timezone=tz,
        source_time_standard="composite start date (MODIS UTC calendar day)",
        native_resolution=source.spatial_resolution,
        grid_point=parsed.pixel_center_lon_lat,
    )
    run_id = new_id("proc")
    obs["processing_run_id"], obs["source_id"], obs["site_id"] = run_id, source.id, args.site_id
    run = ProcessingRun(
        id=run_id,
        version=PIPELINE_VERSION,
        site_id=args.site_id,
        input_source_ids=[source.id],
        steps=[qa_step, align_step],
        created_at=datetime.now(UTC),
        summary={"composites": len(composites), "qa_pass": int(composites["qa_pass"].sum())},
    )
    with Session(get_engine()) as s, s.begin():
        upsert_source(s, source)
        s.flush()
        n = save_pipeline_result(s, PipelineResult(observations=obs, run=run, gaps=[], journey=[]))

    p = qa_step.params
    print(f"site={args.site_id} source={source.id} run={run_id} observations={n}")
    print(f"  composites={p['composites']} ({composites.composite_start.min()} to {composites.composite_start.max()})")
    print(f"  SummaryQA counts={p['summary_qa_counts']}  qa_pass={p['qa_pass']}")
    print(f"  missing={p['missing']}  rejected={p['rejected']}")
    print(f"  pixel centre lon/lat={parsed.pixel_center_lon_lat}")


if __name__ == "__main__":
    main()
