"""Run the M4 engine end to end on this machine. Owner: M4. No database and no GitHub needed.

    uv run python scripts/run_engine_demo.py                          # offline, synthetic DEMO weather
    uv run python scripts/run_engine_demo.py --allocation 250         # fixed-allocation (water-stress) mode
    uv run python scripts/run_engine_demo.py --replay 1995            # replay 1995-1996 for every strategy
    uv run python scripts/run_engine_demo.py --power 38.0 -100.0      # real NASA POWER weather (internet)

Crop parameters are cited FAO-56 table values (ILLUSTRATIVE; D4 open). The soil is a DEMO FAO-56 Table 19
assumption (D8 open) and the strategies are ILLUSTRATIVE (D5 open), so every output is DEMO, also with
--power. The wide pivot in ``power_forcing`` stands in for M3's ``get_daily_forcing``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from ftm.config import get_settings
from ftm.contracts.models import RANGE_LABEL, QualityFlag, Source, ValueKind
from ftm.contracts.models import SimulationMode as Mode
from ftm.engine.demo import (
    DEMO_ELEVATION_M,
    DEMO_ELEVATION_NOTE,
    DEMO_FORCING_SOURCE,
    DEMO_HORIZON,
    demo_site,
    demo_strategies,
    synthetic_forcing,
)
from ftm.engine.forcing import TDEW, flag_col
from ftm.engine.params import demo_soil, load_crops
from ftm.engine.runner import EngineInputError, EngineOutput, EngineRequest, run_engine
from ftm.provenance import sha256_file


def power_forcing(lat: float, lon: float, start: date, end: date) -> tuple[pd.DataFrame, Source, float | None]:
    """Real POWER weather through M3's adapter and pipeline, pivoted to the engine's wide shape."""
    from ftm.data.adapters import nasa_power
    from ftm.data.pipeline.run import run_daily_pipeline
    from ftm.data.raw_cache import RawSnapshot, find_latest_raw

    params = (*nasa_power.DEFAULT_PARAMETERS, TDEW)  # T2MDEW requested on PR #2
    name = nasa_power.raw_filename(lat, lon, start, end)
    cached = find_latest_raw(nasa_power.SOURCE_KEY, name)
    if cached is not None:
        root = get_settings().raw_dir
        mtime = datetime.fromtimestamp(cached.stat().st_mtime, UTC)
        snap = RawSnapshot(cached, cached.relative_to(root.parent).as_posix(), sha256_file(cached), mtime)
    else:
        snap = nasa_power.fetch_daily(lat, lon, start, end, params)
    parsed = nasa_power.parse_daily(snap.path.read_bytes())
    source = nasa_power.build_source(f"power-{lat:.4f}-{lon:.4f}", snap, parsed)
    res = run_daily_pipeline(
        parsed.observations,
        site_id="demo-site",
        source_id=source.id,
        fill_value=parsed.fill_value,
        start=start,
        end=end,
        value_kind=ValueKind.REANALYSIS,
    )
    obs = res.observations
    obs = obs[(obs["quality_flag"] != QualityFlag.DUPLICATE.value) & (obs["date"] >= start) & (obs["date"] <= end)]
    obs = obs.assign(date=pd.to_datetime(obs["date"]))
    wide = obs.pivot(index="date", columns="variable", values="processed_value").astype("float64")
    flags = obs.pivot(index="date", columns="variable", values="quality_flag").add_suffix("__flag")
    df = wide.join(flags).asfreq("D")
    for v in wide.columns:
        df[flag_col(v)] = df[flag_col(v)].fillna(QualityFlag.MISSING.value)
    df.index.name = "date"
    df["source_id"], df["processing_run_id"] = source.id, res.run.id
    return df, source, parsed.elevation_m


def _fmt(v: float | None) -> str:
    return "  n/a" if v is None else f"{v:5.0f}"


def print_report(out: EngineOutput) -> None:
    run = out.run
    print("=" * 96)
    print(
        f"FARM TIME MACHINE ENGINE {run.model_version}  |  {'DEMO OUTPUT - not a field result' if run.is_demo else ''}"
    )
    print("=" * 96)
    print(f"run {run.id}  weather source {run.weather_source_id}  ({run.input_versions['weather_processing_run_id']})")
    print(f"mode {run.mode.value}  allocation {run.allocation_mm} mm/season  method {run.resampling_method}")
    a, b = run.sample_period
    print(f"paths {run.n_paths}  horizon {run.horizon_years} season(s)  seed {run.seed}  sample {a} to {b}")
    print(f"ET0 methods (days): {out.et0_method_days}")
    print(f"journey [{out.journey.status.value}] {out.journey.summary}")
    for e in out.block_pool.excluded:
        print(f"  excluded season {e['year']}: {e['reason']}")
    disabled = [w for w in out.replay_windows if not w["enabled"]]
    print(f"replay windows: {len(out.replay_windows) - len(disabled)} enabled, {len(disabled)} disabled")
    for sid, f in out.feasibility.items():
        print(f"\n{sid}: {'feasible' if f.feasible else 'NOT feasible'}")
        for r in f.reasons:
            print(f"  - {r}")

    sids = list(out.feasibility)
    print(f"\n{RANGE_LABEL}: p10 / p50 / p90")
    print(f"{'metric':<28}" + "".join(f"{s:>24}" for s in sids))
    by = {(r.strategy_id, r.metric): r for r in out.results}
    for m in dict.fromkeys(r.metric for r in out.results):
        cells = "".join(f"{_fmt(by[s, m].p10)}/{_fmt(by[s, m].p50)}/{_fmt(by[s, m].p90)}".rjust(24) for s in sids)
        print(f"{m + ' (' + by[sids[0], m].unit + ')':<28}{cells}")
    print("\nlimitations:")
    for line in dict.fromkeys(lim for r in out.results for lim in r.limitations):
        print(f"  - {line}")
    print(f"\nsources used: {out.results[0].source_ids if out.results else []}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--power", nargs=2, type=float, metavar=("LAT", "LON"), help="use real NASA POWER weather")
    ap.add_argument("--paths", type=int, default=50)
    ap.add_argument("--seed", type=int, default=20261114)
    ap.add_argument("--allocation", type=float, help="mm per irrigated season; switches to fixed_allocation mode")
    ap.add_argument("--awc", choices=("low", "mid", "high"), default="mid", help="FAO-56 Table 19 silt loam bound")
    ap.add_argument("--replay", type=int, metavar="YEAR", help="replay consecutive years starting at YEAR")
    ap.add_argument("--traces", action="store_true", help="write Parquet traces under results/")
    ap.add_argument("--json", type=Path, help="write the run, results and journey as JSON")
    args = ap.parse_args()
    sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]  # Windows code pages (e.g. cp932)

    site = demo_site()
    if args.power:
        lat, lon = args.power
        site = site.model_copy(update={"latitude": lat, "longitude": lon})
        forcing, source, elevation = power_forcing(lat, lon, date(1984, 1, 1), date(2014, 12, 31))  # M5 pool
        if elevation is None:
            raise SystemExit("POWER did not report an elevation; the engine never assumes one.")
        note = f"{elevation:.0f} m, POWER grid-cell elevation (fallback until Site.elevation_m exists)"
    else:
        forcing, source, elevation, note = (
            synthetic_forcing(),
            DEMO_FORCING_SOURCE,
            DEMO_ELEVATION_M,
            DEMO_ELEVATION_NOTE,
        )

    horizon_years = 2
    req = EngineRequest(
        site=site,
        elevation_m=elevation,
        elevation_note=note,
        forcing=forcing,
        weather_source=source,
        soil=demo_soil(site.id, bound=args.awc),
        crops=load_crops(),
        strategies=demo_strategies(site.id),
        horizon=DEMO_HORIZON,
        mode=Mode.FIXED_ALLOCATION if args.allocation is not None else Mode.IRRIGATION_NEEDED,
        allocation_mm_per_season=args.allocation,
        initial_fraction=0.5,  # declared initial condition, softened by the one-season warm-up
        n_paths=args.paths,
        seed=args.seed,
        replay_years=tuple(range(args.replay, args.replay + horizon_years)) if args.replay else None,
        trace_dir=get_settings().results_dir if args.traces else None,
    )
    try:
        out = run_engine(req)
    except EngineInputError as exc:
        raise SystemExit(f"Run blocked: {exc}") from exc
    print_report(out)
    if args.json:
        payload = {
            "run": out.run.model_dump(mode="json"),
            "results": [r.model_dump(mode="json") for r in out.results],
            "feasibility": {k: v.model_dump(mode="json") for k, v in out.feasibility.items()},
            "journey": out.journey.model_dump(mode="json"),
        }
        args.json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
