"""Derive the Kansas winter wheat season length from USDA NASS Crop Progress (D4). Owner: M4.

    uv run python scripts/derive_wheat_season.py                 # print the derivation
    uv run python scripts/derive_wheat_season.py --write         # also fill catalog/winter_wheat_ks.json

Needs NASS_API_KEY in .env (free: https://quickstats.nass.usda.gov/api) unless the raw responses are
already cached under data/raw/nass/. Uses M3's adapter (``ftm.data.adapters.nass_quickstats``): weekly
statewide % planted and % harvested, 50 % date linearly interpolated between reports.

Method (D4, docs/decisions.md): for each crop season, sown in autumn of year Y (50 % planted, Aug-Dec
reports) and harvested in summer of Y+1 (50 % harvested, May-Sep reports), season length = harvest - sowing.
Only seasons whose harvest year lies in the sample pool (validation plan v1.2: 1984-2019) are used; held-out
years 2020-2025 are never read. The catalog gets the median length and a reference naming the NASS source
and the seasons used. Statewide dates, not this field's (disclosed in the reference).
"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import date

import pandas as pd

from ftm.data.adapters import nass_quickstats as nass
from ftm.engine.params import CATALOG_DIR

POOL = (1984, 2019)
WINTER = "WHEAT, WINTER"


def _fifty_pct(progress: pd.DataFrame, start: date, end: date) -> date | None:
    """50 % date from weekly reports with ``start <= week_ending <= end`` (None if not bracketed)."""
    part = progress[(progress["week_ending"] >= start) & (progress["week_ending"] <= end)].copy()
    if part.empty:
        return None
    part["year"] = start.year  # one season per call; M3's helper groups by this column
    return nass.date_at_pct(part, start.year, 50.0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="fill season_days and reference in winter_wheat_ks.json")
    args = ap.parse_args()

    years = range(POOL[0] - 1, POOL[1] + 1)  # sowing in 1983 feeds the 1984 harvest
    snaps = [nass.fetch_progress_cached("WHEAT", unit, years=years) for unit in ("PCT PLANTED", "PCT HARVESTED")]
    planted, harvested = (nass.parse(s.path.read_bytes()) for s in snaps)
    planted = planted[planted["short_desc"].str.startswith(WINTER)]
    harvested = harvested[harvested["short_desc"].str.startswith(WINTER)]
    source = nass.build_source(snaps, pd.concat([planted, harvested]))

    rows = []
    for y in range(POOL[0] - 1, POOL[1]):
        sow = _fifty_pct(planted, date(y, 8, 1), date(y, 12, 31))
        cut = _fifty_pct(harvested, date(y + 1, 5, 1), date(y + 1, 9, 30))
        rows.append(
            {
                "sown": y,
                "harvested": y + 1,
                "sow_50": sow,
                "harvest_50": cut,
                "days": (cut - sow).days if sow and cut else None,
            }
        )
    table = pd.DataFrame(rows)
    print(table.to_string(index=False))
    usable = [int(d) for d in table["days"].dropna()]
    if not usable:
        raise SystemExit("no season has both a 50 % planted and a 50 % harvested date; nothing derived")
    median = round(statistics.median(usable))
    sow_md = sorted(d.strftime("%m-%d") for d in table["sow_50"].dropna())
    cut_md = sorted(d.strftime("%m-%d") for d in table["harvest_50"].dropna())
    reference = (
        f"USDA NASS Crop Progress, Kansas statewide winter wheat 50 % planted -> 50 % harvested "
        f"(source {source.id}); median of {len(usable)} seasons harvested {POOL[0]}-{POOL[1]} "
        f"(range {min(usable)}-{max(usable)} d; sowing median {sow_md[len(sow_md) // 2]}, "
        f"harvest median {cut_md[len(cut_md) // 2]}); statewide, not field-level"
    )
    print(f"\nseason length: median {median} d over {len(usable)} seasons (range {min(usable)}-{max(usable)})")
    print(f"reference: {reference}")
    if args.write:
        path = CATALOG_DIR / "winter_wheat_ks.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["engine_extras"]["local_calendar"].update(season_days=median, reference=reference)
        raw["_status"] = "D4: Kansas-local season length from USDA NASS Crop Progress (derived by this script)."
        path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {path}")
    print("\nAlso register the NASS source in docs/data-sources.md (M3) if it is not listed yet:", source.id)


if __name__ == "__main__":
    main()
