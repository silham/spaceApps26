"""One command: load weather, soil and satellite vegetation for a site, then print its Data Journey.

Usage (from backend/):
  uv run python scripts/load_site.py --site-id ks-field-2 --name "Kansas field 2 (irrigated pivot)" \
      --lat 38.01517 --lon -100.92496 --timezone America/Chicago \
      --boundary ../docs/site-search/ks-field-2.geojson --area-ha 45.8 \
      --status "primary site (D3); local confirmation pending"

Soil source follows D8: SSURGO inside the contiguous US, SoilGrids elsewhere. MODIS needs an Earth Engine
sign-in; use --skip-modis without it. Each step is the existing loader script, so behaviour stays identical.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from ftm.data.journey import build_journey
from ftm.db.session import get_engine

HERE = Path(__file__).resolve().parent


def _in_conus(lat: float, lon: float) -> bool:
    return 24.0 <= lat <= 49.5 and -125.0 <= lon <= -66.5


def _run(script: str, *args: str) -> None:
    print(f"\n== {script} {' '.join(args)}")
    subprocess.run([sys.executable, str(HERE / script), *args], check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for a in ("--site-id", "--name", "--timezone"):
        ap.add_argument(a, required=True)
    ap.add_argument("--lat", required=True)
    ap.add_argument("--lon", required=True)
    ap.add_argument("--start", default="1981-01-01")
    ap.add_argument("--end", default="2025-12-31")
    ap.add_argument("--boundary")
    ap.add_argument("--area-ha")
    ap.add_argument("--status")
    ap.add_argument("--skip-modis", action="store_true")
    args = ap.parse_args()

    power = [
        "--site-id",
        args.site_id,
        "--name",
        args.name,
        "--lat",
        args.lat,
        "--lon",
        args.lon,
        "--timezone",
        args.timezone,
        "--start",
        args.start,
        "--end",
        args.end,
    ]
    for flag, val in (("--boundary", args.boundary), ("--area-ha", args.area_ha), ("--status", args.status)):
        if val:
            power += [flag, val]
    _run("load_power.py", *power)
    soil = "ssurgo" if _in_conus(float(args.lat), float(args.lon)) else "soilgrids"
    _run("load_soil.py", "--site-id", args.site_id, "--source", soil)
    if not args.skip_modis:
        _run("load_modis.py", "--site-id", args.site_id)

    with Session(get_engine()) as s:
        print("\n== Data Journey")
        for st in build_journey(args.site_id, s):
            print(f"  {st.stage.value:<12} {st.status.value:<12} {st.summary}")


if __name__ == "__main__":
    main()
