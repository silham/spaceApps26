"""Engine side of the sensitivity study (validation plan section 4). Owner: M4.

M5's ``ftm.validation.sensitivity`` owns the scenarios (``default_factors``, ``one_at_a_time``,
``full_factorial``) and the ranking (``ranking_stability``). It calls the engine through
``run_fn(inputs) -> {strategy_id: {metric: median}}``; ``make_run_fn`` builds that function.

Inputs (M5's factor names), applied to one base request:

| key | engine meaning |
|---|---|
| ``awc_mm_per_m`` | soil AWC (provider low/mid/high, or a labelled assumption) |
| ``initial_soil_water_frac_taw`` | initial water as a fraction of field capacity over the whole profile |
| ``planting_shift_days`` | every crop season moves by this many days, harvest included; fallow stays |
| ``irrigation_allocation_mm`` | allocation per irrigated season (fixed-allocation mode only) |

Every call keeps the base seed, sample pool, horizon and path count, so every scenario draws the *same*
weather paths; ``make_run_fn`` checks this and raises if pairing ever breaks. A shift that breaks a hard
constraint makes that strategy infeasible with its reason; it is then missing from that scenario's result
(never moved back silently), which M5's ranking counts as a change.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from datetime import timedelta
from typing import Any

from ftm.contracts.models import SimulationMode, Strategy
from ftm.engine.params import with_awc
from ftm.engine.runner import EngineOutput, EngineRequest, run_engine

FACTOR_KEYS = ("awc_mm_per_m", "initial_soil_water_frac_taw", "planting_shift_days", "irrigation_allocation_mm")
RunFn = Callable[[dict[str, Any]], Mapping[str, Mapping[str, float]]]


def shift_planting(strategy: Strategy, days: int) -> Strategy:
    """Move every crop season (planting and harvest) by ``days``; fallow seasons stay where they are."""
    if days == 0:
        return strategy
    delta = timedelta(days=days)
    seasons = [
        s
        if s.crop_id is None
        else s.model_copy(update={"plant_date": s.plant_date + delta, "end_date": s.end_date + delta})
        for s in strategy.seasons
    ]
    return strategy.model_copy(update={"seasons": seasons, "feasibility": None})


def apply_inputs(base: EngineRequest, inputs: Mapping[str, Any]) -> EngineRequest:
    """The base request with M5's sensitivity inputs; weather, seed, pool and path count are unchanged."""
    unknown = set(inputs) - set(FACTOR_KEYS)
    if unknown:
        raise ValueError(f"unknown sensitivity input(s) {sorted(unknown)}; supported: {list(FACTOR_KEYS)}")
    req = base
    if (
        awc := inputs.get("awc_mm_per_m")
    ) is not None and awc != base.soil.profile.available_water_capacity_mm_per_m.value:
        req = dataclasses.replace(req, soil=with_awc(base.soil, float(awc), "sensitivity input (validation plan s4)"))
    if (frac := inputs.get("initial_soil_water_frac_taw")) is not None:
        req = dataclasses.replace(req, initial_fraction=float(frac))
    if (shift := inputs.get("planting_shift_days")) is not None:
        req = dataclasses.replace(req, strategies=[shift_planting(s, int(shift)) for s in base.strategies])
    if (alloc := inputs.get("irrigation_allocation_mm")) is not None:
        if base.mode is not SimulationMode.FIXED_ALLOCATION:
            raise ValueError("irrigation allocation applies only in fixed_allocation mode")
        req = dataclasses.replace(req, allocation_mm_per_season=float(alloc))
    return dataclasses.replace(req, trace_dir=None)


def medians(out: EngineOutput) -> dict[str, dict[str, float]]:
    """{strategy_id: {metric: p50}} for strategies that were simulated (infeasible ones are absent)."""
    res: dict[str, dict[str, float]] = {}
    for r in out.results:
        if r.p50 is not None:
            res.setdefault(r.strategy_id, {})[r.metric] = r.p50
    return res


def make_run_fn(base: EngineRequest, *, on_output: Callable[[EngineOutput], None] | None = None) -> RunFn:
    """``run_fn`` for ``ftm.validation.sensitivity.ranking_stability`` (same weather paths in every call)."""
    first_paths: list[tuple[int, ...]] | None = None

    def run_fn(inputs: dict[str, Any]) -> dict[str, dict[str, float]]:
        nonlocal first_paths
        out = run_engine(apply_inputs(base, inputs))
        paths = [o.years for o in out.outcomes]
        if paths:
            if first_paths is None:
                first_paths = paths
            elif paths != first_paths:
                raise RuntimeError("sensitivity scenarios drew different weather paths; pairing is broken")
        if on_output is not None:
            on_output(out)
        return medians(out)

    return run_fn
