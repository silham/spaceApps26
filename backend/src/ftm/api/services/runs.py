"""Comparison runs: D6 supported edits -> engine -> stored SimulationRun, Results and paired deltas. Owner: M1.

The engine (``ftm.engine.runner.run_engine``) does the science; this module only turns a ``RunRequest`` into
an engine request, caches by inputs hash, stores the outputs and serves them back. Rules kept here:

- Only the D6 edits exist (mode, allocation, planting shift <= 14 days); anything else never reaches the engine.
- Every strategy shares the same weather paths, so strategy-minus-baseline differences are taken per path
  (paired comparison) before summarising; they are not differences of medians.
- A replay window that cannot run is refused with its reason; no nearby window is substituted.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ftm.config import get_settings
from ftm.contracts.models import (
    FarmerContext,
    PairedDelta,
    ReplaySeries,
    ReplayTrace,
    ReplayWindow,
    Result,
    RunDetail,
    RunRequest,
    SimulationMode,
    SimulationRun,
    Strategy,
)
from ftm.data.engine_inputs import (
    DEFAULT_POOL,
    SiteEngineInputs,
    build_site_scenario,
    load_site_engine_inputs,
)
from ftm.db.models import PairedDeltaRow, ResultRow, SimulationRunRow, SiteRow, StrategyRow
from ftm.engine.ensemble import MIN_PATHS_FOR_RANGE, MODEL_VERSION, PathOutcome, SoilRunConfig, run_replay
from ftm.engine.et0 import compute_et0
from ftm.engine.forcing import RAIN, usable_values
from ftm.engine.runner import UNSUPPORTED_CLAIMS, EngineInputError, EngineOutput, EngineRequest, run_engine
from ftm.engine.scenarios import SCENARIO_HORIZON, Scenario
from ftm.engine.sensitivity import shift_planting
from ftm.provenance import inputs_hash, new_id

# Declared initial soil water before warm-up (fraction of field capacity), as in scripts/run_engine_site.py.
INITIAL_FRACTION = 0.5

# Which direction is preferable, for presenting paired differences only (no score is formed from these).
# None: no preferred direction (more ET or more drainage is neither better nor worse in general).
BETTER_DIRECTION: dict[str, Literal["lower", "higher"] | None] = {
    "irrigation_mm": "lower",
    "allocation_shortfall_days": "lower",
    "water_stress_days": "lower",
    "aet_mm": None,
    "deep_drainage_mm": None,
    "runoff_mm": "lower",
    "cover_days": "higher",
    "possible_low_cover_days": "lower",
    "crop_diversity_count": "higher",
}


class RunNotFoundError(LookupError):
    pass


class RunBlockedError(ValueError):
    """The run cannot be computed as requested; the message is shown to the farmer."""


class SiteNotReadyError(LookupError):
    """A stored input the engine needs is missing (not loaded); the message says what to load."""


@dataclass(frozen=True)
class _Prepared:
    inputs: SiteEngineInputs
    scenario: Scenario
    farmer: FarmerContext | None


# Loading 45 years of daily forcing and computing ET0 takes ~1 s; replays reuse it per weather processing run.
_cache_lock = threading.Lock()
_prepared_cache: dict[tuple[str, str, tuple[str, ...]], _Prepared] = {}
_et0_cache: dict[tuple[str, str], pd.DataFrame] = {}
_replay_cache: dict[tuple[str, tuple[int, ...]], ReplayTrace] = {}


def _farmer_context(session: Session, site_id: str) -> FarmerContext | None:
    row = session.get(SiteRow, site_id)
    if row is None or not row.farmer_context:
        return None
    try:
        return FarmerContext.model_validate(row.farmer_context)
    except ValueError:
        return None  # legacy free-form context: not a confirmed farmer input


farmer_context_for = _farmer_context


def _prepare(session: Session, site_id: str) -> _Prepared:
    from ftm.api.services.rotations import active_strategies, selectable_crops
    from ftm.data.engine_inputs import SCENARIO_BUILDERS, EngineInputsNotAvailableError
    from ftm.engine.params import CatalogError
    from ftm.engine.scenarios import build_user_scenario

    user_strategies = [] if site_id in SCENARIO_BUILDERS else active_strategies(session, site_id)
    if site_id not in SCENARIO_BUILDERS and not user_strategies:  # observe-only farm until rotations are saved
        raise SiteNotReadyError(
            f"no rotations are saved for farm {site_id!r}, so it is observe-only: choose crops and build at least "
            "one rotation first (D15); reviewed strategies exist for ks-field-2 only (D5, D13)"
        )
    try:
        inputs = load_site_engine_inputs(session, site_id)
        weather_key = inputs.forcing.attrs.get("processing_run_id") or inputs.weather_source.id
        key = (site_id, weather_key, tuple(s.id for s in user_strategies))
        with _cache_lock:
            cached = _prepared_cache.get(key)
        if cached:
            scenario = cached.scenario
        elif user_strategies:
            scenario = build_user_scenario(user_strategies, selectable_crops())
        else:
            scenario = build_site_scenario(inputs)
    except (EngineInputsNotAvailableError, CatalogError) as exc:
        raise SiteNotReadyError(str(exc)) from exc
    prepared = _Prepared(inputs, scenario, _farmer_context(session, site_id))
    with _cache_lock:
        _prepared_cache[key] = prepared
    return prepared


def _strategies(scenario: Scenario, req: RunRequest) -> list[Strategy]:
    known = {s.id for s in scenario.strategies}
    unknown = sorted(set(req.planting_shift_days) - known)
    if unknown:
        raise RunBlockedError(f"unknown strategy id(s) for a planting shift: {unknown}; known: {sorted(known)}")
    return [shift_planting(s, req.planting_shift_days.get(s.id, 0)) for s in scenario.strategies]


def _engine_request(p: _Prepared, req: RunRequest, *, keep_traces: bool) -> EngineRequest:
    available = set(p.farmer.available_crop_ids) if p.farmer and p.farmer.available_crop_ids is not None else None
    return EngineRequest(
        site=p.inputs.site,
        elevation_m=p.inputs.elevation_m,
        elevation_note=p.inputs.elevation_note,
        forcing=p.inputs.forcing,
        weather_source=p.inputs.weather_source,
        soil=p.inputs.soil,
        crops=p.scenario.crops,
        strategies=_strategies(p.scenario, req),
        horizon=SCENARIO_HORIZON,
        mode=req.mode,
        allocation_mm_per_season=req.allocation_mm,
        initial_fraction=INITIAL_FRACTION,
        n_paths=req.n_paths,
        seed=req.seed,
        pool_range=DEFAULT_POOL,
        available_crop_ids=available,
        trace_dir=get_settings().results_dir if keep_traces else None,
    )


def _hash(p: _Prepared, ereq: EngineRequest, req: RunRequest) -> str:
    return inputs_hash(
        {
            "request": req.model_dump(mode="json"),
            "weather_source_id": p.inputs.weather_source.id,
            "weather_processing_run_id": p.inputs.forcing.attrs.get("processing_run_id"),
            "soil_profile_id": p.inputs.soil_profile.id,
            "crops": {cid: c.profile.model_dump(mode="json") for cid, c in sorted(ereq.crops.items())},
            "strategies": [s.model_dump(mode="json") for s in ereq.strategies],
            "available_crop_ids": sorted(ereq.available_crop_ids) if ereq.available_crop_ids is not None else None,
            "initial_fraction": ereq.initial_fraction,
            "pool": ereq.pool_range,
            "model_version": MODEL_VERSION,
        }
    )


def _window_rain(forcing: pd.DataFrame, years: list[int]) -> float | None:
    rain = pd.Series(usable_values(forcing, RAIN), index=forcing.index)
    part = rain[rain.index.year.isin(years)]
    if part.empty or part.isna().any():
        return None  # missing rain is not zero rain
    return round(float(part.sum()), 1)


def deltas_from_outcomes(
    run_id: str,
    outcomes: list[PathOutcome],
    baseline_id: str,
    units: dict[str, str],
    source_ids: list[str],
    *,
    is_demo: bool,
) -> list[PairedDelta]:
    """Per-path strategy-minus-baseline differences, summarised as p10/p50/p90 across paths."""
    if not outcomes or baseline_id not in outcomes[0].metrics:
        return []
    enough = len(outcomes) >= MIN_PATHS_FOR_RANGE
    out = []
    for sid in outcomes[0].metrics:
        if sid == baseline_id:
            continue
        for metric in outcomes[0].metrics[sid]:
            if metric not in units:
                continue
            diff = np.array([o.metrics[sid][metric] - o.metrics[baseline_id][metric] for o in outcomes])
            p10, p50, p90 = (float(v) for v in np.percentile(diff, [10, 50, 90]))
            direction = BETTER_DIRECTION.get(metric)
            better = worse = None
            if direction is not None:
                sign = -1.0 if direction == "lower" else 1.0
                better = float(np.mean(sign * diff > 0))
                worse = float(np.mean(sign * diff < 0))
            out.append(
                PairedDelta(
                    id=new_id("dlt"),
                    run_id=run_id,
                    strategy_id=sid,
                    baseline_strategy_id=baseline_id,
                    metric=metric,
                    unit=units[metric],
                    p10=p10 if enough else None,
                    p50=p50,
                    p90=p90 if enough else None,
                    better_direction=direction,
                    share_better=better,
                    share_worse=worse,
                    sample_count=len(outcomes),
                    source_ids=source_ids,
                    is_demo=is_demo,
                )
            )
    return out


def _detail_payload(
    out: EngineOutput, req: RunRequest, strategies: list[Strategy], p: _Prepared, source_ids: list[str]
) -> dict[str, Any]:
    windows = []
    for w in out.replay_windows:
        years = [int(y) for y in w["years"]]  # type: ignore[attr-defined]
        windows.append(
            ReplayWindow(
                years=years,
                enabled=bool(w["enabled"]),
                reason=None if w["reason"] is None else str(w["reason"]),
                in_sample_pool=bool(w["in_sample_pool"]),
                rain_mm=_window_rain(p.inputs.forcing, years) if w["enabled"] else None,
            )
        )
    detail = RunDetail(
        run=out.run,
        request=req,
        strategies=[s.model_copy(update={"feasibility": out.feasibility[s.id]}) for s in strategies],
        replay_windows=windows,
        excluded_blocks=out.block_pool.excluded,
        limitations=out.limitations,
        source_ids=source_ids,
        scenario_notes=list(p.scenario.notes),
        unsupported_claims=list(UNSUPPORTED_CLAIMS),
    )
    payload = detail.model_dump(mode="json", exclude={"run", "cached"})
    payload["journey"] = out.journey.model_dump(mode="json")
    return payload


def _run_from_row(row: SimulationRunRow) -> SimulationRun:
    return SimulationRun(
        id=row.id,
        site_id=row.site_id,
        strategy_ids=list(row.strategy_ids),
        mode=SimulationMode(row.mode),
        allocation_mm=row.allocation_mm,
        weather_source_id=row.weather_source_id,
        resampling_method=row.resampling_method,
        sample_period=(row.sample_start, row.sample_end),
        n_paths=row.n_paths,
        horizon_years=row.horizon_years,
        seed=row.seed,
        model_version=row.model_version,
        input_versions=dict(row.input_versions or {}),
        created_at=row.created_at,
        is_demo=row.is_demo,
    )


def detail_from_row(row: SimulationRunRow, *, cached: bool = False) -> RunDetail:
    if not row.detail:
        raise RunNotFoundError(f"run {row.id!r} has no stored detail (DEMO fixture or pre-1.2 run)")
    data = {k: v for k, v in row.detail.items() if k != "journey"}
    return RunDetail.model_validate({**data, "run": _run_from_row(row), "cached": cached})


def create_run(session: Session, req: RunRequest, *, owner_user_id: str | None = None) -> RunDetail:
    p = _prepare(session, req.site_id)
    ereq = _engine_request(p, req, keep_traces=True)
    key = _hash(p, ereq, req)
    existing = session.scalars(
        select(SimulationRunRow)
        .where(
            SimulationRunRow.inputs_hash == key,
            SimulationRunRow.detail.is_not(None),
            SimulationRunRow.owner_user_id == owner_user_id,
        )
        .order_by(SimulationRunRow.created_at.desc())
    ).first()
    if existing is not None:
        return detail_from_row(existing, cached=True)

    try:
        out = run_engine(ereq)
    except EngineInputError as exc:
        raise RunBlockedError(str(exc)) from exc

    source_ids = out.results[0].source_ids if out.results else []
    run = out.run
    for st in p.scenario.strategies:  # results reference strategy rows; register any the seed script has not
        if session.get(StrategyRow, st.id) is None:
            session.add(StrategyRow(**st.model_dump(mode="json")))
    session.add(
        SimulationRunRow(
            id=run.id,
            owner_user_id=owner_user_id,
            site_id=run.site_id,
            strategy_ids=run.strategy_ids,
            mode=run.mode.value,
            allocation_mm=run.allocation_mm,
            weather_source_id=run.weather_source_id,
            resampling_method=run.resampling_method,
            sample_start=run.sample_period[0],
            sample_end=run.sample_period[1],
            n_paths=run.n_paths,
            horizon_years=run.horizon_years,
            seed=run.seed,
            model_version=run.model_version,
            input_versions=run.input_versions,
            inputs_hash=key,
            detail=_detail_payload(out, req, ereq.strategies, p, source_ids),
            is_demo=run.is_demo,
            created_at=run.created_at,
        )
    )
    session.flush()
    for r in out.results:
        session.add(ResultRow(**r.model_dump(exclude={"range_label"})))
    baseline = next((s.id for s in ereq.strategies if s.is_baseline), None)
    units = {r.metric: r.unit for r in out.results}
    if baseline is not None:
        for d in deltas_from_outcomes(run.id, out.outcomes, baseline, units, source_ids, is_demo=run.is_demo):
            session.add(PairedDeltaRow(**d.model_dump(exclude={"range_label"})))
    session.commit()
    row = session.get(SimulationRunRow, run.id)
    assert row is not None
    return detail_from_row(row)


def get_run_row(session: Session, run_id: str) -> SimulationRunRow:
    row = session.get(SimulationRunRow, run_id)
    if row is None:
        raise RunNotFoundError(f"run {run_id!r} not found")
    return row


def list_runs(session: Session, site_id: str, limit: int = 20) -> list[RunDetail]:
    rows = session.scalars(
        select(SimulationRunRow)
        .where(SimulationRunRow.site_id == site_id, SimulationRunRow.detail.is_not(None))
        .order_by(SimulationRunRow.created_at.desc())
        .limit(limit)
    )
    return [detail_from_row(r) for r in rows]


def get_results(session: Session, run_id: str) -> list[Result]:
    rows = session.scalars(select(ResultRow).where(ResultRow.run_id == run_id).order_by(ResultRow.id)).all()
    return [Result.model_validate(r) for r in rows]


def get_deltas(session: Session, run_id: str) -> list[PairedDelta]:
    rows = session.scalars(select(PairedDeltaRow).where(PairedDeltaRow.run_id == run_id).order_by(PairedDeltaRow.id))
    return [PairedDelta.model_validate(r) for r in rows]


def _et0(p: _Prepared) -> pd.DataFrame:
    key = (p.inputs.site.id, p.inputs.forcing.attrs.get("processing_run_id") or p.inputs.weather_source.id)
    with _cache_lock:
        hit = _et0_cache.get(key)
    if hit is not None:
        return hit
    et0 = compute_et0(p.inputs.forcing, latitude_deg=p.inputs.site.latitude, elevation_m=p.inputs.elevation_m)
    with _cache_lock:
        _et0_cache[key] = et0
    return et0


def _num(values: Any) -> list[float | None]:
    return [None if v is None or not np.isfinite(v) else round(float(v), 3) for v in values]


def turning_point(series: list[ReplaySeries], dates: list[date]) -> tuple[date | None, str | None]:
    """The day the strategies' root-zone soil water differs most (first such day). None if <2 strategies."""
    if len(series) < 2 or not dates:
        return None, None
    stack = np.array([[np.nan if v is None else v for v in s.storage_mm] for s in series], dtype=float)
    if np.all(np.isnan(stack)):
        return None, None
    spread = np.nanmax(stack, axis=0) - np.nanmin(stack, axis=0)
    k = int(np.nanargmax(spread))
    return dates[k], f"largest difference in root-zone soil water between strategies ({spread[k]:.0f} mm)"


def replay(session: Session, run_id: str, years: tuple[int, ...]) -> ReplayTrace:
    with _cache_lock:
        hit = _replay_cache.get((run_id, years))
    if hit is not None:
        return hit
    detail = detail_from_row(get_run_row(session, run_id))
    window = next((w for w in detail.replay_windows if tuple(w.years) == years), None)
    if window is None:
        raise RunBlockedError(f"{'-'.join(map(str, years))} is not a replay window of this run")
    if not window.enabled:
        raise RunBlockedError(window.reason or "replay window unavailable")
    p = _prepare(session, detail.run.site_id)
    feasible = [s for s in detail.strategies if s.feasibility is None or s.feasibility.feasible]
    if not feasible:
        raise RunBlockedError("no feasible strategy to replay")
    try:
        _, outcome = run_replay(
            p.inputs.forcing,
            _et0(p),
            feasible,
            p.scenario.crops,
            SoilRunConfig(soil=p.inputs.soil, initial_fraction=INITIAL_FRACTION),
            horizon=SCENARIO_HORIZON,
            mode=detail.run.mode,
            allocation_mm_per_season=detail.run.allocation_mm,
            years=years,
            pool_range=DEFAULT_POOL,
            keep_traces=True,
        )
    except ValueError as exc:
        raise RunBlockedError(str(exc)) from exc
    first = next(iter(outcome.traces.values()))
    dates = [pd.Timestamp(d).date() for d in first["strategy_date"]]
    series = [
        ReplaySeries(
            strategy_id=sid,
            crop_id=[None if pd.isna(c) else str(c) for c in t["crop_id"]],
            in_crop=[bool(v) for v in t["in_crop"]],
            storage_mm=_num(t["storage_end_mm"]),
            ks=_num(t["ks"]),
            irrigation_mm=_num(t["irrigation_mm"]),
            aet_mm=_num(t["aet_mm"]),
            metrics={k: round(v, 3) for k, v in outcome.metrics[sid].items()},
        )
        for sid, t in outcome.traces.items()
    ]
    tp, why = turning_point(series, dates)
    limitations = [
        "One historical window replayed: a single path, so no range is shown.",
        *([] if window.in_sample_pool else ["These years are outside the sample pool (held out): replay only."]),
        *detail.limitations,
    ]
    trace = ReplayTrace(
        run_id=run_id,
        years=list(years),
        in_sample_pool=window.in_sample_pool,
        dates=dates,
        source_dates=[pd.Timestamp(d).date() for d in first["source_date"]],
        rain_mm=_num(first["rain_mm"]),
        et0_mm=_num(first["et0_mm"]),
        series=series,
        turning_point=tp,
        turning_point_reason=why,
        source_ids=detail.source_ids,
        limitations=limitations,
        is_demo=detail.run.is_demo,
    )
    with _cache_lock:
        _replay_cache[(run_id, years)] = trace
    return trace


def latest_run_row(session: Session, site_id: str) -> SimulationRunRow | None:
    return session.scalars(
        select(SimulationRunRow)
        .where(SimulationRunRow.site_id == site_id, SimulationRunRow.detail.is_not(None))
        .order_by(SimulationRunRow.created_at.desc())
    ).first()
