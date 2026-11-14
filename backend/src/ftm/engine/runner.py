"""Engine entry point: one validated request in, contract-shaped output out. Owner: M4.

``run_engine`` is what M1's ``POST /runs`` will call. It does not touch the database or the API; it
returns ``SimulationRun``, ``Result`` and ``JourneyStage`` contract objects plus the block pool and the
per-strategy feasibility so the caller can store and serve them.

Every result carries the IDs of the sources actually used (weather source, soil sources, FAO-56, TR-55)
and the weather processing-run ID (in ``SimulationRun.input_versions``). Infeasible strategies get
results with null values and their reasons, so a blocked claim is visible, never silently dropped.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from ftm.contracts.models import (
    RANGE_LABEL,
    Feasibility,
    JourneyStage,
    JourneyStageName,
    Result,
    SimulationMode,
    SimulationRun,
    Site,
    Source,
    StageStatus,
    Strategy,
)
from ftm.engine.ensemble import (
    BOOTSTRAP_METHOD,
    METRIC_UNITS,
    MIN_PATHS_FOR_RANGE,
    MODEL_VERSION,
    REPLAY_METHOD,
    BlockPool,
    PathOutcome,
    SoilRunConfig,
    horizon_blocks,
    replay_windows,
    run_ensemble,
    run_replay,
    summarize,
    usable_blocks,
)
from ftm.engine.et0 import HARGREAVES, compute_et0
from ftm.engine.forcing import ForcingContractError, ForcingInfo, assert_forcing_contract
from ftm.engine.params import LITERATURE_SOURCES, CropEntry, SoilSpec
from ftm.engine.rotation import FALLOW_CHUNK_DAYS, SUPPORTED_IRRIGATION_RULE, ZE_BARE_SOIL_M, check_feasibility
from ftm.engine.water_balance import IRRIGATION_RULE
from ftm.provenance import inputs_hash, new_id

SUPPORTED_METRICS = (
    "irrigation_mm",
    "allocation_shortfall_days",
    "water_stress_days",
    "aet_mm",
    "deep_drainage_mm",
    "runoff_mm",
    "cover_days",
    "possible_low_cover_days",
    "crop_diversity_count",
)
# Claims this engine cannot support: never emitted, and shown as unavailable rather than estimated.
UNSUPPORTED_CLAIMS = (
    "yield",
    "profit",
    "soil carbon change",
    "nitrogen balance",
    "salinity",
    "erosion (t/ha)",
    "residue cover",
)


class EngineInputError(ValueError):
    """The request cannot be run as stated. The message is readable by a farmer or a reviewer."""


@dataclass(frozen=True)
class EngineRequest:
    site: Site
    elevation_m: float
    elevation_note: str  # where the elevation came from; disclosed in the run
    forcing: pd.DataFrame  # wide daily frame (``engine.forcing``)
    weather_source: Source
    soil: SoilSpec
    crops: Mapping[str, CropEntry]
    strategies: list[Strategy]
    horizon: tuple[date, date]
    mode: SimulationMode
    allocation_mm_per_season: float | None
    initial_fraction: float  # declared initial condition (fraction of field capacity) before warm-up
    n_paths: int = 0
    seed: int = 0
    replay_years: tuple[int, ...] | None = None  # set: replay these consecutive years instead of bootstrap
    available_crop_ids: set[str] | None = None
    trace_dir: Path | None = None  # set: write per-strategy Parquet traces under it


@dataclass
class EngineOutput:
    run: SimulationRun
    results: list[Result]
    feasibility: dict[str, Feasibility]
    block_pool: BlockPool
    replay_windows: list[dict[str, object]]
    journey: JourneyStage
    limitations: list[str]
    et0_method_days: dict[str, int]
    outcomes: list[PathOutcome] = field(default_factory=list)


def validate_request(req: EngineRequest) -> ForcingInfo:
    """Reject inputs the engine cannot run honestly. Returns the forcing provenance."""
    try:
        info = assert_forcing_contract(req.forcing)
    except ForcingContractError as exc:
        raise EngineInputError(f"weather input rejected: {exc}") from exc
    if info.source_id != req.weather_source.id:
        raise EngineInputError(
            f"forcing source_id '{info.source_id}' does not match the weather source '{req.weather_source.id}'"
        )
    if not math.isfinite(req.elevation_m):
        raise EngineInputError("site elevation is required for Penman-Monteith ET0; it is never assumed")
    if not req.horizon[0] < req.horizon[1]:
        raise EngineInputError("the comparison horizon must end after it starts")
    if not req.strategies:
        raise EngineInputError("at least one strategy is required")
    ids = [s.id for s in req.strategies]
    if len(set(ids)) != len(ids):
        raise EngineInputError("strategy ids must be unique")
    if any(s.site_id != req.site.id for s in req.strategies):
        raise EngineInputError(f"every strategy must belong to site '{req.site.id}'")
    if req.mode is SimulationMode.FIXED_ALLOCATION:
        if req.allocation_mm_per_season is None or not req.allocation_mm_per_season >= 0:
            raise EngineInputError("fixed_allocation mode needs an allocation >= 0 mm per irrigated season")
    elif req.allocation_mm_per_season is not None:
        raise EngineInputError("an allocation is only used in fixed_allocation mode; remove it or change mode")
    if not 0.0 <= req.initial_fraction <= 1.0:
        raise EngineInputError("initial soil water must be a fraction of field capacity in [0, 1]")
    if not req.soil.data_depth_m > 0:
        raise EngineInputError("soil data depth must be > 0 m")
    if req.replay_years is None and req.n_paths < 1:
        raise EngineInputError("n_paths must be >= 1 for the bootstrap ensemble")
    return info


def _source_ids(req: EngineRequest) -> list[str]:
    ids = [req.weather_source.id, *req.soil.profile.source_ids, *(s.id for s in LITERATURE_SOURCES)]
    return list(dict.fromkeys(ids))


def _common_limitations(req: EngineRequest, et0_days: dict[str, int], n_paths: int) -> list[str]:
    lim = [
        "Historical weather is resampled; this is not a climate forecast.",
        f"p10-p90 is the {RANGE_LABEL} across weather paths, not a calibrated prediction interval.",
        "Crop parameters are generic FAO-56 table values (ILLUSTRATIVE, not locally calibrated; D4 is open).",
        "Single crop coefficient soil-water balance (FAO-56 ch. 8); root depth fixed from planting.",
        f"Fallow uses the FAO-56 Annex 7 bare-soil Kc per {FALLOW_CHUNK_DAYS}-day period, "
        f"evaporation layer {ZE_BARE_SOIL_M} m.",
        "Runoff from TR-55 curve numbers (average condition); snowmelt and frozen ground are not modelled.",
        f"Elevation: {req.elevation_note}.",
        *req.soil.notes,
        "Water stress days count days with Ks < 1 in the model; they are not a yield estimate.",
    ]
    if req.mode is not SimulationMode.IRRIGATION_NEEDED or any(
        s.irrigation_rule for st in req.strategies for s in st.seasons
    ):
        lim.append(f"Irrigation rule: {IRRIGATION_RULE}.")
    if n := et0_days.get(HARGREAVES, 0):
        lim.append(f"ET0 used the Hargreaves fallback (FAO-56 eq. 52) on {n} day(s) of the record.")
    if n_paths < MIN_PATHS_FOR_RANGE:
        lim.append(f"Only {n_paths} path(s): p10/p90 are not reported below {MIN_PATHS_FOR_RANGE} paths.")
    return lim


def _write_traces(trace_dir: Path, run_id: str, outcomes: list[PathOutcome]) -> dict[str, str]:
    out_dir = trace_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    for sid in outcomes[0].traces:
        frames = [o.traces[sid].assign(path=k) for k, o in enumerate(outcomes)]
        df = pd.concat(frames, ignore_index=True)
        df["crop_id"] = df["crop_id"].astype("string")
        target = out_dir / f"{sid}.parquet"
        df.to_parquet(target, index=False)
        paths[sid] = target.as_posix()
    return paths


def run_engine(req: EngineRequest) -> EngineOutput:
    info = validate_request(req)
    et0 = compute_et0(req.forcing, latitude_deg=req.site.latitude, elevation_m=req.elevation_m)
    et0_days = {str(k): int(v) for k, v in Counter(et0["et0_method"].fillna("none")).items()}
    feas = {
        s.id: check_feasibility(
            s, req.crops, horizon=req.horizon, soil=req.soil, available_crop_ids=req.available_crop_ids
        )
        for s in req.strategies
    }
    feasible = [s for s in req.strategies if feas[s.id].feasible]
    config = SoilRunConfig(soil=req.soil, initial_fraction=req.initial_fraction)
    n_years = horizon_blocks(req.horizon)
    keep = req.trace_dir is not None
    pool = usable_blocks(req.forcing, et0, req.horizon[0].strftime("%m-%d"))
    method = REPLAY_METHOD if req.replay_years is not None else BOOTSTRAP_METHOD

    outcomes: list[PathOutcome] = []
    try:
        if feasible and req.replay_years is not None:
            _, one = run_replay(
                req.forcing,
                et0,
                feasible,
                req.crops,
                config,
                horizon=req.horizon,
                mode=req.mode,
                allocation_mm_per_season=req.allocation_mm_per_season,
                years=req.replay_years,
                keep_traces=keep,
            )
            outcomes = [one]
        elif feasible:
            _, outcomes = run_ensemble(
                req.forcing,
                et0,
                feasible,
                req.crops,
                config,
                horizon=req.horizon,
                mode=req.mode,
                allocation_mm_per_season=req.allocation_mm_per_season,
                n_paths=req.n_paths,
                seed=req.seed,
                keep_traces=keep,
            )
    except ValueError as exc:
        raise EngineInputError(str(exc)) from exc

    windows = (
        replay_windows(pool, horizon_years=n_years, first=pool.usable_years[0], last=pool.usable_years[-1])
        if pool.usable_years
        else []
    )
    run_id = new_id("sim")
    trace_paths = _write_traces(req.trace_dir, run_id, outcomes) if req.trace_dir is not None and outcomes else {}
    is_demo = (
        req.site.is_demo
        or req.weather_source.is_demo
        or req.soil.profile.is_demo
        or any(s.is_demo for s in req.strategies)
        or any(c.profile.is_demo for c in req.crops.values())
    )
    usable_starts = [pd.Timestamp(f"{y}-{req.horizon[0]:%m-%d}") for y in pool.usable_years]
    sample_period = (
        (usable_starts[0].date(), (usable_starts[-1] + pd.DateOffset(years=1) - pd.Timedelta(days=1)).date())
        if usable_starts
        else (info.start.date(), info.end.date())
    )
    catalog = {cid: c.profile.model_dump(mode="json") for cid, c in sorted(req.crops.items())}
    run = SimulationRun(
        id=run_id,
        site_id=req.site.id,
        strategy_ids=[s.id for s in req.strategies],
        mode=req.mode,
        allocation_mm=req.allocation_mm_per_season,
        weather_source_id=req.weather_source.id,
        resampling_method=method,
        sample_period=sample_period,
        n_paths=len(outcomes),
        horizon_years=n_years,
        seed=req.seed,
        model_version=MODEL_VERSION,
        input_versions={
            "weather_processing_run_id": info.processing_run_id,
            "soil_profile_id": req.soil.profile.id,
            "crop_catalog_sha256": inputs_hash(catalog),
            "elevation_m": f"{req.elevation_m:g}",
            "initial_fraction_of_field_capacity": f"{req.initial_fraction:g}",
            "irrigation_rule": SUPPORTED_IRRIGATION_RULE,
            **({"replay_years": "-".join(map(str, req.replay_years))} if req.replay_years else {}),
        },
        created_at=datetime.now(UTC),
        is_demo=is_demo,
    )

    common = _common_limitations(req, et0_days, len(outcomes))
    summary = summarize(outcomes)
    fixed = req.mode is SimulationMode.FIXED_ALLOCATION
    metrics = [m for m in SUPPORTED_METRICS if fixed or m != "allocation_shortfall_days"]
    source_ids = _source_ids(req)
    results: list[Result] = []
    for s in req.strategies:
        notes = sorted({n for o in outcomes for n in o.notes.get(s.id, ())})
        for m in metrics:
            row = summary.get(s.id, {}).get(m)
            if row is None:
                results.append(
                    Result(
                        id=new_id("res"),
                        run_id=run_id,
                        strategy_id=s.id,
                        metric=m,
                        unit=METRIC_UNITS[m],
                        p10=None,
                        p50=None,
                        p90=None,
                        sample_count=0,
                        source_ids=source_ids,
                        limitations=["Not simulated: strategy is infeasible.", *feas[s.id].reasons],
                        is_demo=is_demo,
                    )
                )
                continue
            results.append(
                Result(
                    id=new_id("res"),
                    run_id=run_id,
                    strategy_id=s.id,
                    metric=m,
                    unit=METRIC_UNITS[m],
                    p10=_opt(row["p10"]),
                    p50=_opt(row["p50"]),
                    p90=_opt(row["p90"]),
                    sample_count=len(outcomes),
                    trace_path=trace_paths.get(s.id),
                    source_ids=source_ids,
                    limitations=[*common, *notes],
                    is_demo=is_demo,
                )
            )

    journey = _journey(req, info, run, pool, feas, et0_days, source_ids)
    return EngineOutput(run, results, feas, pool, windows, journey, common, et0_days, outcomes)


def _opt(v: object) -> float | None:
    return None if v is None else float(str(v))


def _journey(
    req: EngineRequest,
    info: ForcingInfo,
    run: SimulationRun,
    pool: BlockPool,
    feas: dict[str, Feasibility],
    et0_days: dict[str, int],
    source_ids: list[str],
) -> JourneyStage:
    n_ok = sum(f.feasible for f in feas.values())
    if n_ok == 0:
        status = StageStatus.FAILED
        summary = f"No strategy could be simulated: all {len(feas)} are infeasible (see reasons)."
    else:
        warn = pool.excluded or n_ok < len(feas) or et0_days.get(HARGREAVES, 0) > 0
        status = StageStatus.WARNING if warn else StageStatus.OK
        what = "replayed" if req.replay_years else f"run on {run.n_paths} resampled weather paths"
        summary = (
            f"{n_ok} of {len(feas)} strategies {what} of {run.horizon_years} season(s), from "
            f"{len(pool.usable_years)} usable seasons ({len(pool.excluded)} excluded for missing data)."
        )
    return JourneyStage(
        stage=JourneyStageName.SIMULATE,
        status=status,
        summary=summary,
        source_ids=source_ids,
        processing_run_id=info.processing_run_id,
        chart={
            "type": "bar",
            "title": "Season blocks available to the simulation",
            "labels": ["usable", "excluded"],
            "values": [len(pool.usable_years), len(pool.excluded)],
            "unit": "seasons",
        },
        details={
            "run_id": run.id,
            "mode": run.mode.value,
            "resampling_method": run.resampling_method,
            "seed": run.seed,
            "et0_method_days": et0_days,
            "excluded_blocks": pool.excluded,
            "infeasible": {sid: f.reasons for sid, f in feas.items() if not f.feasible},
            "min_paths_for_range": MIN_PATHS_FOR_RANGE,
            "unsupported_claims": list(UNSUPPORTED_CLAIMS),
            "input_versions": json.loads(json.dumps(run.input_versions)),
        },
        is_demo=run.is_demo,
    )
