"""Paired historical-weather ensemble and replay. Owner: M4.

- Blocks are season-aligned agricultural years starting on the horizon's anchor month-day, so a block
  keeps every weather variable of the same historical days together (within-block relationships kept).
- Block usability (agreed M4 policy, proposed on PR #2): a block with any unusable rain day or any day
  without ET0 is excluded from the pool and reported with its reason. A day is never skipped, because a
  skipped day would act as 0 mm rain (DEVELOPMENT_GUIDE.md section 6).
- Bootstrap: years drawn with replacement via ``numpy.random.default_rng(seed)``. Independent draws do
  not preserve multi-year persistence, so consecutive-year replay is offered as well; a window crossing
  an excluded year is reported disabled with a reason, never shortened or swapped.
- Pairing: each path's weather is built once and every strategy runs on that same object.
- Warm-up: each strategy is first run on its own year-1 schedule over the path's first block, and the
  main run starts from that end state (declared spin-up; reduces the effect of the initial condition).
- Sample pool (validation plan section 1): bootstrap draws only from the declared ``pool_years`` (e.g.
  1984-2019 for anything using ET0). Usable years outside it (e.g. held-out 2020-2025) can be replayed on
  screen but never build or tune a range.
- Output: p10/p50/p90 per metric labelled as a central 80% simulation range (``RANGE_LABEL``), only when
  at least ``MIN_PATHS_FOR_RANGE`` paths exist; otherwise p10/p90 are None.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from itertools import pairwise
from typing import Protocol

import numpy as np
import pandas as pd

from ftm.contracts.models import RANGE_LABEL, SimulationMode, Strategy
from ftm.engine.forcing import RAIN, TMAX, WIND, usable, usable_values
from ftm.engine.kc import rhmin_pct
from ftm.engine.params import CropEntry, SoilSpec
from ftm.engine.rotation import PathWeather, cover_indicators, daily_schedule
from ftm.engine.water_balance import BucketInputs, SoilState, end_state, simulate_bucket, state_at_fraction

MODEL_VERSION = "0.3.0"
BOOTSTRAP_METHOD = "season_aligned_block_bootstrap_iid_years"
REPLAY_METHOD = "consecutive_year_replay"
# Engine choice, not a calibrated value: with n paths, p10/p90 rest on n/10 paths per tail; below 20 paths a
# tail rests on a single path, so the range is not reported. M5 may revise this with the coverage study.
MIN_PATHS_FOR_RANGE = 20


@dataclass(frozen=True)
class BlockPool:
    usable_years: list[int]  # complete blocks with usable rain and ET0 every day (data check only)
    excluded: list[dict[str, object]]  # {"year", "start", "reason"}
    pool_range: tuple[int, int] | None = None  # declared sample pool; None = every usable year

    @property
    def pool_years(self) -> list[int]:
        """Usable years the bootstrap may draw from."""
        if self.pool_range is None:
            return list(self.usable_years)
        a, b = self.pool_range
        return [y for y in self.usable_years if a <= y <= b]

    @property
    def outside_pool_years(self) -> list[int]:
        """Usable years kept out of the ranges (replay only), e.g. the held-out test years."""
        return [y for y in self.usable_years if y not in self.pool_years]


@dataclass(frozen=True)
class EnsembleConfig:
    """Everything that defines the resampling, recorded with every run (validation plan section 3)."""

    horizon: tuple[date, date]
    pool_range: tuple[int, int] | None
    n_paths: int
    seed: int
    method: str = "season_aligned_block_bootstrap_iid_years"

    @property
    def anchor_md(self) -> str:
        return self.horizon[0].strftime("%m-%d")

    def describe(self) -> dict[str, str]:
        pool = "all usable years" if self.pool_range is None else f"{self.pool_range[0]}-{self.pool_range[1]}"
        return {
            "block_definition": f"agricultural year starting {self.anchor_md} (whole block, all variables together)",
            "horizon": f"{self.horizon[0]} to {self.horizon[1]}",
            "sample_pool": pool,
            "n_paths": str(self.n_paths),
            "seed": str(self.seed),
            "method": self.method,
        }


@dataclass(frozen=True)
class SoilRunConfig:
    soil: SoilSpec
    initial_fraction: float  # declared initial condition, fraction of field capacity in the whole profile
    warmup: bool = True

    @property
    def awc_mm_per_m(self) -> float:
        v = self.soil.profile.available_water_capacity_mm_per_m.value
        if v is None:
            raise ValueError("soil available water capacity is missing")
        return float(v)


@dataclass
class PathOutcome:
    years: tuple[int, ...]
    metrics: dict[str, dict[str, float]]  # strategy_id -> metric -> value
    notes: dict[str, tuple[str, ...]] = field(default_factory=dict)  # strategy_id -> disclosed assumptions
    traces: dict[str, pd.DataFrame] = field(default_factory=dict)


def _block_bounds(year: int, anchor_md: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(f"{year}-{anchor_md}")
    return start, pd.Timestamp(f"{year + 1}-{anchor_md}") - pd.Timedelta(days=1)


def horizon_blocks(horizon: tuple[date, date]) -> int:
    """Number of agricultural-year blocks (anchored on the horizon start) needed to cover the horizon."""
    start, end = horizon
    return end.year - start.year + (1 if end.strftime("%m-%d") >= start.strftime("%m-%d") else 0)


def usable_blocks(
    forcing: pd.DataFrame, et0: pd.DataFrame, anchor_md: str, pool_range: tuple[int, int] | None = None
) -> BlockPool:
    """Split complete agricultural-year blocks into usable and excluded (with reasons)."""
    if pool_range is not None and pool_range[0] > pool_range[1]:
        raise ValueError(f"sample pool {pool_range} ends before it starts")
    rain_ok = usable(forcing, RAIN)
    et0_ok = et0["et0_mm_day"].notna()
    years, excluded = [], []
    for y in range(forcing.index[0].year - 1, forcing.index[-1].year + 1):
        start, end = _block_bounds(y, anchor_md)
        if start < forcing.index[0] or end > forcing.index[-1]:
            continue  # incomplete edge block: not offered at all
        sl = slice(start, end)
        reasons = []
        if (n := int((~rain_ok[sl]).sum())) > 0:
            reasons.append(f"{n} day(s) without usable rainfall (missing rain is not zero rain)")
        if (n := int((~et0_ok[sl]).sum())) > 0:
            reasons.append(f"{n} day(s) where ET0 could not be computed")
        if reasons:
            excluded.append({"year": y, "start": start.date().isoformat(), "reason": "; ".join(reasons)})
        else:
            years.append(y)
    return BlockPool(usable_years=years, excluded=excluded, pool_range=pool_range)


def bootstrap_paths(pool: BlockPool, *, n_paths: int, horizon_years: int, seed: int) -> list[tuple[int, ...]]:
    if not pool.pool_years:
        raise ValueError("no usable season blocks in the sample pool; run blocked (see excluded blocks for reasons)")
    if n_paths < 1:
        raise ValueError("n_paths must be >= 1")
    rng = np.random.default_rng(seed)
    draws = rng.choice(np.asarray(pool.pool_years), size=(n_paths, horizon_years), replace=True)
    return [tuple(int(y) for y in row) for row in draws]


def replay_windows(pool: BlockPool, *, horizon_years: int, first: int, last: int) -> list[dict[str, object]]:
    """All consecutive-year windows in [first, last]; windows touching an excluded year are disabled."""
    excluded = {int(str(e["year"])): str(e["reason"]) for e in pool.excluded}
    out = []
    for y0 in range(first, last - horizon_years + 2):
        years = tuple(range(y0, y0 + horizon_years))
        bad = [y for y in years if y not in pool.usable_years]
        reason = None
        if bad:
            parts = [f"{y}: {excluded.get(y, 'no complete data block')}" for y in bad]
            reason = "Replay unavailable: " + " | ".join(parts)
        in_pool = not bad and all(y in pool.pool_years for y in years)
        out.append({"years": years, "enabled": not bad, "reason": reason, "in_sample_pool": in_pool})
    return out


def daily_weather(forcing: pd.DataFrame, et0: pd.DataFrame) -> pd.DataFrame:
    """Usable daily values the engine consumes; unusable days are NaN (never 0)."""
    return pd.DataFrame(
        {
            "rain_mm": usable_values(forcing, RAIN),
            "et0_mm": et0["et0_mm_day"].to_numpy(dtype="float64"),
            "u2_m_s": usable_values(forcing, WIND),
            "rhmin_pct": rhmin_pct(et0["ea_kpa"].to_numpy(dtype="float64"), usable_values(forcing, TMAX)),
        },
        index=forcing.index,
    )


def build_path_forcing(
    weather: pd.DataFrame, years: tuple[int, ...], *, anchor_md: str, base_year: int
) -> pd.DataFrame:
    """Concatenate the historical blocks of one path and add the strategy-calendar date for each day.

    Real historical days only: nothing is invented or dropped (a source Feb 29 maps to Feb 28 on a
    non-leap strategy year).
    """
    parts = []
    for k, y in enumerate(years):
        start, end = _block_bounds(y, anchor_md)
        block = weather.loc[start:end].copy()
        block["source_date"] = block.index
        block["strategy_date"] = block.index + pd.DateOffset(years=base_year + k - y)
        block["block"] = k
        parts.append(block)
    return pd.concat(parts).reset_index(drop=True)


def _path_weather(pf: pd.DataFrame) -> PathWeather:
    return PathWeather(*(pf[c].to_numpy(dtype="float64") for c in ("rain_mm", "et0_mm", "u2_m_s", "rhmin_pct")))


def run_strategies_on_path(
    path_forcing: pd.DataFrame,
    strategies: list[Strategy],
    crops: Mapping[str, CropEntry],
    config: SoilRunConfig,
    *,
    mode: SimulationMode,
    allocation_mm_per_season: float | None,
) -> tuple[dict[str, pd.DataFrame], dict[str, tuple[str, ...]]]:
    """Run every strategy on the *same* weather frame (identical forcing, horizon and soil)."""
    weather = _path_weather(path_forcing)
    dates = pd.DatetimeIndex(path_forcing["strategy_date"])
    awc, depth = config.awc_mm_per_m, config.soil.data_depth_m
    first = (path_forcing["block"] == 0).to_numpy()
    traces, notes = {}, {}
    for strat in strategies:
        sch = daily_schedule(strat, crops, config.soil, dates, weather)
        arrays = (
            weather.rain_mm,
            weather.et0_mm,
            sch.kc,
            sch.p_table,
            sch.zr_m,
            sch.cn,
            sch.crop_day,
            sch.irrigable,
            sch.season_id,
        )
        state: SoilState = state_at_fraction(
            config.initial_fraction, awc_mm_per_m=awc, profile_depth_m=depth, depth_m=float(sch.zr_m[0])
        )

        def run(inputs: BucketInputs, start: SoilState) -> pd.DataFrame:
            return simulate_bucket(
                inputs,
                awc_mm_per_m=awc,
                profile_depth_m=depth,
                initial_state=start,
                mode=mode,
                allocation_mm_per_season=allocation_mm_per_season,
            )

        if config.warmup:
            state = end_state(run(BucketInputs(*(a[first] for a in arrays)), state))
        trace = run(BucketInputs(*arrays), state)
        trace["et0_mm"] = weather.et0_mm
        trace["kc"] = sch.kc
        trace["strategy_date"] = dates
        trace["source_date"] = path_forcing["source_date"].to_numpy()
        trace["crop_id"] = sch.crop_id
        trace["in_crop"] = sch.crop_day
        trace["in_initial_stage"] = sch.in_initial_stage
        traces[strat.id] = trace
        notes[strat.id] = sch.notes
    return traces, notes


def path_metrics(trace: pd.DataFrame) -> dict[str, float]:
    in_crop = trace["in_crop"].to_numpy(dtype=bool)
    return {
        "irrigation_mm": float(trace["irrigation_mm"].sum()),
        "allocation_shortfall_days": float((trace["irrigation_shortfall_mm"] > 0).sum()),
        "water_stress_days": float(((trace["ks"] < 1.0) & in_crop).sum()),
        "aet_mm": float(trace["aet_mm"].sum()),
        "deep_drainage_mm": float(trace["drainage_mm"].sum()),
        "runoff_mm": float(trace["runoff_mm"].sum()),
        **cover_indicators(in_crop, trace["in_initial_stage"].to_numpy(dtype=bool), trace["crop_id"].to_numpy()),
    }


METRIC_UNITS = {
    "irrigation_mm": "mm",
    "allocation_shortfall_days": "days",
    "water_stress_days": "days",
    "aet_mm": "mm",
    "deep_drainage_mm": "mm",
    "runoff_mm": "mm",
    "cover_days": "days",
    "possible_low_cover_days": "days",
    "crop_diversity_count": "crops",
}


def summarize(outcomes: list[PathOutcome]) -> dict[str, dict[str, dict[str, object]]]:
    """strategy -> metric -> {p10, p50, p90, unit, sample_count, range_label}.

    p10/p90 are None below ``MIN_PATHS_FOR_RANGE`` paths; p50 is then the median of the paths run.
    """
    out: dict[str, dict[str, dict[str, object]]] = {}
    if not outcomes:
        return out
    enough = len(outcomes) >= MIN_PATHS_FOR_RANGE
    for sid in outcomes[0].metrics:
        out[sid] = {}
        for metric in outcomes[0].metrics[sid]:
            vals = np.array([o.metrics[sid][metric] for o in outcomes])
            p10, p50, p90 = (float(v) for v in np.percentile(vals, [10, 50, 90]))
            out[sid][metric] = {
                "p10": p10 if enough else None,
                "p50": p50,
                "p90": p90 if enough else None,
                "unit": METRIC_UNITS[metric],
                "sample_count": len(vals),
                "range_label": RANGE_LABEL,
            }
    return out


def _run_paths(
    weather: pd.DataFrame,
    paths: list[tuple[int, ...]],
    strategies: list[Strategy],
    crops: Mapping[str, CropEntry],
    config: SoilRunConfig,
    *,
    horizon: tuple[date, date],
    mode: SimulationMode,
    allocation_mm_per_season: float | None,
    keep_traces: bool,
) -> list[PathOutcome]:
    anchor_md = horizon[0].strftime("%m-%d")
    outcomes = []
    for years in paths:
        pf = build_path_forcing(weather, years, anchor_md=anchor_md, base_year=horizon[0].year)
        traces, notes = run_strategies_on_path(
            pf, strategies, crops, config, mode=mode, allocation_mm_per_season=allocation_mm_per_season
        )
        metrics = {sid: path_metrics(t) for sid, t in traces.items()}
        outcomes.append(PathOutcome(years, metrics, notes, traces if keep_traces else {}))
    return outcomes


def run_ensemble(
    forcing: pd.DataFrame,
    et0: pd.DataFrame,
    strategies: list[Strategy],
    crops: Mapping[str, CropEntry],
    config: SoilRunConfig,
    *,
    horizon: tuple[date, date],
    mode: SimulationMode,
    allocation_mm_per_season: float | None,
    n_paths: int,
    seed: int,
    pool_range: tuple[int, int] | None = None,
    keep_traces: bool = False,
) -> tuple[BlockPool, list[PathOutcome]]:
    """Seeded bootstrap of whole season blocks from the sample pool; strategies share each path's weather."""
    pool = usable_blocks(forcing, et0, horizon[0].strftime("%m-%d"), pool_range)
    paths = bootstrap_paths(pool, n_paths=n_paths, horizon_years=horizon_blocks(horizon), seed=seed)
    outcomes = _run_paths(
        daily_weather(forcing, et0),
        paths,
        strategies,
        crops,
        config,
        horizon=horizon,
        mode=mode,
        allocation_mm_per_season=allocation_mm_per_season,
        keep_traces=keep_traces,
    )
    return pool, outcomes


def run_replay(
    forcing: pd.DataFrame,
    et0: pd.DataFrame,
    strategies: list[Strategy],
    crops: Mapping[str, CropEntry],
    config: SoilRunConfig,
    *,
    horizon: tuple[date, date],
    mode: SimulationMode,
    allocation_mm_per_season: float | None,
    years: tuple[int, ...],
    pool_range: tuple[int, int] | None = None,
    keep_traces: bool = True,
) -> tuple[BlockPool, PathOutcome]:
    """Replay one consecutive run of historical years (held-out years allowed: replay builds no range).

    A disabled window raises with its reason.
    """
    pool = usable_blocks(forcing, et0, horizon[0].strftime("%m-%d"), pool_range)
    n = horizon_blocks(horizon)
    if len(years) != n or any(b - a != 1 for a, b in pairwise(years)):
        raise ValueError(f"replay needs {n} consecutive years, got {years}")
    window = replay_windows(pool, horizon_years=n, first=years[0], last=years[-1])[0]
    if not window["enabled"]:
        raise ValueError(str(window["reason"]))
    (outcome,) = _run_paths(
        daily_weather(forcing, et0),
        [years],
        strategies,
        crops,
        config,
        horizon=horizon,
        mode=mode,
        allocation_mm_per_season=allocation_mm_per_season,
        keep_traces=keep_traces,
    )
    return pool, outcome


def ensemble_weather_paths(
    forcing: pd.DataFrame, et0: pd.DataFrame, config: EnsembleConfig
) -> tuple[BlockPool, list[tuple[tuple[int, ...], pd.DataFrame]]]:
    """The exact weather paths a run with ``config`` uses, without simulating strategies.

    For M5's coverage evaluation: aggregate each path's weather over a season window and compare the
    p10-p90 of those totals with the held-out observed season (validation plan section 3).
    """
    pool = usable_blocks(forcing, et0, config.anchor_md, config.pool_range)
    years = bootstrap_paths(
        pool, n_paths=config.n_paths, horizon_years=horizon_blocks(config.horizon), seed=config.seed
    )
    weather = daily_weather(forcing, et0)
    return pool, [
        (y, build_path_forcing(weather, y, anchor_md=config.anchor_md, base_year=config.horizon[0].year)) for y in years
    ]


class SeasonWindowLike(Protocol):
    """Anything with ``bounds(year) -> (start, end)`` for the season *ending* in ``year`` (M5's SeasonWindow)."""

    def bounds(self, year: int) -> tuple[date, date]: ...


SEASONAL_TARGETS = ("rain_mm", "et0_mm", "rain_minus_et0_mm")


def seasonal_totals_by_year(weather: pd.DataFrame, window: SeasonWindowLike, target: str) -> pd.Series:
    """Season totals of ``target`` keyed by the year the season ends. Any unusable day -> NaN (never 0)."""
    if target not in SEASONAL_TARGETS:
        raise ValueError(f"target must be one of {SEASONAL_TARGETS}")
    daily = weather["rain_mm"] - weather["et0_mm"] if target == "rain_minus_et0_mm" else weather[target]
    out = {}
    for y in sorted({int(t.year) for t in weather.index}):
        a, b = (pd.Timestamp(d) for d in window.bounds(y))
        part = daily.loc[a:b]
        complete = a >= weather.index[0] and b <= weather.index[-1] and part.notna().all()
        out[y] = float(part.sum()) if complete else np.nan
    return pd.Series(out, name=target, dtype="float64")


def seasonal_ensemble_fn(
    forcing: pd.DataFrame, et0: pd.DataFrame, window: SeasonWindowLike, target: str, *, n_paths: int, seed: int
) -> Callable[[Sequence[int], int], np.ndarray]:
    """``ensemble_fn(pool_years, target_year)`` for M5's coverage evaluation (validation plan section 3).

    The same season-aligned block bootstrap as a run, with a one-season horizon: whole historical seasons
    (all days of the window together) are drawn with replacement from ``pool_years`` by
    ``numpy.random.default_rng(seed)``. Seasons with any unusable day are not drawn. A pool year at or after
    the target year is refused, so the held-out season can never inform its own range.
    """
    totals = seasonal_totals_by_year(daily_weather(forcing, et0), window, target)

    def ensemble_fn(pool_years: Sequence[int], target_year: int) -> np.ndarray:
        if any(y >= target_year for y in pool_years):
            raise ValueError(f"pool years must precede the target year {target_year} (no leakage)")
        usable_pool = [y for y in pool_years if y in totals.index and np.isfinite(totals[y])]
        if not usable_pool:
            raise ValueError(f"no complete {target} season in the pool before {target_year}")
        draws = np.random.default_rng(seed).choice(np.asarray(usable_pool), size=n_paths, replace=True)
        return np.asarray(totals.loc[draws].to_numpy(), dtype="float64")

    return ensemble_fn
