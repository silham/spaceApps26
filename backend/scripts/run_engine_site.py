"""Run the engine for a loaded site from the database (real POWER weather + stored soil). Owner: M4.

    uv run python scripts/run_engine_site.py --site-id ks-field-2 --weather-source power_9a04873ea83f797c
    uv run python scripts/run_engine_site.py ... --allocation 300          # fixed allocation, mm per season
    uv run python scripts/run_engine_site.py ... --replay 2022             # held-out years: replay only
    uv run python scripts/run_engine_site.py ... --sensitivity oat         # validation plan s4 (8 + 1 runs)

Needs the site, its weather (scripts/load_power.py) and its soil profile (scripts/load_soil.py) in the DB.
Nothing is assumed when an input is missing: the run stops and says what to load. Strategies are the
ks-field-2 scenarios in ``ftm.engine.scenarios`` (D5, see docs/decisions.md).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ftm.config import get_settings
from ftm.contracts.models import RANGE_LABEL, Site, SoilProfile, Source
from ftm.contracts.models import SimulationMode as Mode
from ftm.data.forcing import get_daily_forcing
from ftm.db.models import SiteRow, SoilProfileRow, SourceRow
from ftm.db.session import get_engine
from ftm.engine.forcing import from_store_frame
from ftm.engine.params import soil_spec_from_profile
from ftm.engine.runner import EngineInputError, EngineOutput, EngineRequest, run_engine
from ftm.engine.scenarios import SCENARIO_HORIZON, build_ks_field_2
from ftm.engine.sensitivity import AwcBounds, full_grid, one_at_a_time, run_sensitivity

# Validation plan v1.2 section 1: ET0-based ranges draw from 1984-2019; 2020-2025 are held out.
DEFAULT_POOL = (1984, 2019)
RECORD = (date(1981, 1, 1), date(2025, 12, 31))


def _site(row: SiteRow) -> Site:
    return Site(
        id=row.id,
        name=row.name,
        latitude=row.latitude,
        longitude=row.longitude,
        timezone=row.timezone,
        area_ha=row.area_ha,
        farmer_context=row.farmer_context or {},
        is_demo=row.is_demo,
    )


def _source(row: SourceRow) -> Source:
    fields = {k: getattr(row, k) for k in Source.model_fields if k != "footprint_geojson"}
    return Source.model_validate(fields)


def _elevation(source: Source) -> tuple[float, str]:
    """POWER grid-cell elevation from the immutable raw snapshot (fallback until Site.elevation_m exists)."""
    from ftm.data.adapters import nasa_power

    if not source.raw_path:
        raise SystemExit(f"weather source {source.id} has no raw snapshot path; elevation unknown, run stopped")
    parsed = nasa_power.parse_daily((get_settings().data_dir / source.raw_path).read_bytes())
    if parsed.elevation_m is None:
        raise SystemExit("POWER reported no elevation; the engine never assumes one")
    return float(parsed.elevation_m), f"{parsed.elevation_m:.0f} m, POWER grid-cell elevation ({source.id})"


def _awc_bounds(site: Site, profile: SoilProfile, cli: list[float] | None) -> AwcBounds | None:
    mid = profile.available_water_capacity_mm_per_m.value
    if mid is None:
        return None
    if cli:
        return AwcBounds(cli[0], float(mid), cli[1], "AWC bounds given on the command line")
    from ftm.data.adapters import soil_ssurgo
    from ftm.data.raw_cache import find_latest_raw

    path = find_latest_raw(soil_ssurgo.SOURCE_KEY, soil_ssurgo.raw_filename(site.latitude, site.longitude))
    if path is None:
        return None
    res = soil_ssurgo.build(site.id, soil_ssurgo.fetch_cached(site.latitude, site.longitude))
    if res.awc_low_mm_per_m is None or res.awc_high_mm_per_m is None:
        return None
    return AwcBounds(res.awc_low_mm_per_m, float(mid), res.awc_high_mm_per_m, "SSURGO awc_l / awc_r / awc_h, 0-1 m")


def _print(out: EngineOutput) -> None:
    run = out.run
    print("=" * 100)
    print(f"{run.site_id}  run {run.id}  engine {run.model_version}  {'DEMO' if run.is_demo else ''}")
    print("=" * 100)
    for k in ("sample_pool", "block_definition", "horizon", "held_out_or_outside_pool_years"):
        print(f"{k}: {run.input_versions.get(k)}")
    iv = run.input_versions
    print(f"weather {run.weather_source_id} / {iv['weather_processing_run_id']}  soil {iv['soil_profile_id']}")
    print(f"mode {run.mode.value}  allocation {run.allocation_mm}  paths {run.n_paths}  seed {run.seed}")
    print(f"ET0 methods (days, whole record): {out.et0_method_days}")
    print(f"journey [{out.journey.status.value}] {out.journey.summary}")
    for e in out.block_pool.excluded:
        print(f"  excluded {e['year']}: {e['reason']}")
    for sid, f in out.feasibility.items():
        print(f"{sid}: {'feasible' if f.feasible else 'NOT feasible'}" + "".join(f"\n  - {r}" for r in f.reasons))
    sids = list(out.feasibility)
    by = {(r.strategy_id, r.metric): r for r in out.results}

    def cell(v: float | None) -> str:
        return " n/a" if v is None else f"{v:4.0f}"

    print(f"\n{RANGE_LABEL}: p10/p50/p90")
    print(f"{'metric':<30}" + "".join(f"{s:>24}" for s in sids))
    for m in dict.fromkeys(r.metric for r in out.results):
        row = "".join(f"{cell(by[s, m].p10)}/{cell(by[s, m].p50)}/{cell(by[s, m].p90)}".rjust(24) for s in sids)
        print(f"{m + ' (' + by[sids[0], m].unit + ')':<30}{row}")
    print("\nlimitations:")
    for lim in dict.fromkeys(x for r in out.results for x in r.limitations):
        print(f"  - {lim}")
    print(f"sources: {out.results[0].source_ids if out.results else []}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site-id", required=True)
    ap.add_argument("--weather-source", required=True, help="source id printed by scripts/load_power.py")
    ap.add_argument("--soil-profile", help="soil_profile id (default: the site's newest profile)")
    ap.add_argument("--pool", nargs=2, type=int, default=DEFAULT_POOL, metavar=("FIRST", "LAST"))
    ap.add_argument("--paths", type=int, default=200)
    ap.add_argument("--seed", type=int, default=20261114)
    ap.add_argument("--allocation", type=float, help="mm per irrigated season (farmer-confirmed); fixed mode")
    ap.add_argument("--initial-fraction", type=float, default=0.5, help="declared initial soil water (0-1)")
    ap.add_argument("--replay", type=int, metavar="YEAR", help="replay consecutive years from YEAR")
    ap.add_argument("--sensitivity", choices=("oat", "grid"))
    ap.add_argument("--awc-bounds", nargs=2, type=float, metavar=("LOW", "HIGH"))
    ap.add_argument(
        "--wheat",
        choices=("kansas-local", "fao56-idaho"),
        default="kansas-local",
        help="kansas-local (D4, blocked until the NASS season length is entered) or the FAO-56 Idaho row as printed",
    )
    ap.add_argument("--traces", action="store_true", help="write Parquet traces under results/")
    ap.add_argument("--json", type=Path, help="write run, results, feasibility and journey as JSON")
    args = ap.parse_args()
    sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]  # Windows code pages (e.g. cp932)

    with Session(get_engine()) as s:
        site_row = s.get(SiteRow, args.site_id)
        if site_row is None:
            raise SystemExit(f"site {args.site_id!r} is not in the database; run scripts/load_power.py first")
        src_row = s.get(SourceRow, args.weather_source)
        if src_row is None:
            raise SystemExit(f"weather source {args.weather_source!r} is not in the database")
        q = (
            select(SoilProfileRow)
            .where(SoilProfileRow.site_id == args.site_id)
            .order_by(SoilProfileRow.created_at.desc())
        )
        soil_row = s.get(SoilProfileRow, args.soil_profile) if args.soil_profile else s.scalars(q).first()
        if soil_row is None:
            raise SystemExit(
                f"no soil profile for {args.site_id!r}; run scripts/load_soil.py --site-id {args.site_id} "
                "--source ssurgo (the engine never assumes a soil for a real site)"
            )
        site, source = _site(site_row), _source(src_row)
        profile = SoilProfile.model_validate(soil_row.params)
        forcing = from_store_frame(get_daily_forcing(site.id, *RECORD, source.id, session=s))

    elevation, note = _elevation(source)
    soil = soil_spec_from_profile(profile, data_depth_m=1.0)  # M3 integrates AWC over 0-1 m (DEFAULT_DEPTH_M)
    if args.site_id != "ks-field-2":
        raise SystemExit("strategies are defined for ks-field-2 only (D5); other sites need their own scenarios")
    pool_years = list(range(args.pool[0], args.pool[1] + 1))
    scen = build_ks_field_2(forcing, pool_years, site_id=site.id, wheat=args.wheat)
    print("scenario notes:")
    for n in scen.notes:
        print(f"  - {n}")
    req = EngineRequest(
        site=site,
        elevation_m=elevation,
        elevation_note=note,
        forcing=forcing,
        weather_source=source,
        soil=soil,
        crops=scen.crops,
        strategies=scen.strategies,
        horizon=SCENARIO_HORIZON,
        mode=Mode.FIXED_ALLOCATION if args.allocation is not None else Mode.IRRIGATION_NEEDED,
        allocation_mm_per_season=args.allocation,
        initial_fraction=args.initial_fraction,
        n_paths=args.paths,
        seed=args.seed,
        replay_years=(args.replay, args.replay + 1) if args.replay else None,
        pool_range=(args.pool[0], args.pool[1]),
        trace_dir=get_settings().results_dir if args.traces else None,
    )
    try:
        if args.sensitivity:
            bounds = _awc_bounds(site, profile, args.awc_bounds)
            if bounds is None:
                raise SystemExit(
                    "AWC bounds unknown: no cached SSURGO snapshot; pass --awc-bounds LOW HIGH with a source"
                )
            fixed = req.mode is Mode.FIXED_ALLOCATION
            cases = (
                one_at_a_time(include_allocation=fixed)
                if args.sensitivity == "oat"
                else full_grid(include_allocation=fixed)
            )
            report = run_sensitivity(req, cases, bounds)
            print(f"sensitivity ({args.sensitivity}, {len(cases)} runs, same weather paths; AWC {bounds.source})")
            for line in report.summary.values():
                print(f"  - {line}")
            return
        out = run_engine(req)
    except EngineInputError as exc:
        raise SystemExit(f"Run blocked: {exc}") from exc
    _print(out)
    if args.json:
        payload = {
            "run": out.run.model_dump(mode="json"),
            "results": [r.model_dump(mode="json") for r in out.results],
            "feasibility": {k: v.model_dump(mode="json") for k, v in out.feasibility.items()},
            "journey": out.journey.model_dump(mode="json"),
            "replay_windows": out.replay_windows,
        }
        args.json.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        print(f"wrote {args.json}")


if __name__ == "__main__":
    main()
