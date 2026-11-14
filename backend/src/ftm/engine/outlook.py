"""The coming seasons on the real calendar (D16). Owner: M4.

* ``observed_end``: the last day with usable NASA POWER rain and temperatures (POWER lags a few days).
* ``prediction_horizon``: starts the day after it, so there is no unsimulated gap, and runs 24 months.
* ``observed_initial_fraction``: today's simulated soil water, from the observed weather of the last year
  under what the farmer says is on the field (or bare fallow, stated), as a fraction of field capacity.
* ``outlook``: daily p10/p50/p90 rain, Tmin, Tmax and soil water over the coming months from the same
  forecast-weighted historical paths the comparisons use (the forecast never supplies weather values).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from ftm.contracts.models import SeasonPlan, SimulationMode, Strategy
from ftm.engine.ensemble import (
    BlockPool,
    SoilRunConfig,
    bootstrap_paths,
    build_path_forcing,
    daily_weather,
    horizon_blocks,
    run_strategies_on_path,
)
from ftm.engine.forcing import RAIN, TMAX, TMIN, usable, usable_values
from ftm.engine.params import CropEntry
from ftm.engine.rotation import stage_lengths

HORIZON_MONTHS = 24
SPINUP_DAYS = 365
SPINUP_START_FRACTION = 0.5  # declared start of the one-year spin-up; a year of real weather softens it
OUTLOOK_DAYS = 183
OUTLOOK_PATHS = 100
PERCENTILES = (10, 50, 90)


@dataclass(frozen=True)
class FieldNow:
    """Farmer input: the crop on the field now (or last harvested) and its dates. None fields = not stated."""

    crop_id: str | None
    plant_date: date | None
    harvest_date: date | None


@dataclass(frozen=True)
class InitialState:
    fraction: float  # of field capacity over the whole profile
    as_of: date
    storage_mm: float
    assumption: str


def observed_end(forcing: pd.DataFrame) -> date:
    ok = usable(forcing, RAIN) & usable(forcing, TMAX) & usable(forcing, TMIN)
    if not ok.any():
        raise ValueError("no day with usable rain and temperature in the weather record")
    last: date = pd.Timestamp(ok[ok].index[-1]).date()
    return last


def prediction_horizon(end_observed: date) -> tuple[date, date]:
    start = end_observed + timedelta(days=1)
    end = (pd.Timestamp(start) + pd.DateOffset(months=HORIZON_MONTHS) - pd.Timedelta(days=1)).date()
    return start, end


def _field_now_strategy(site_id: str, field: FieldNow | None, crops: Mapping[str, CropEntry]) -> tuple[Strategy, str]:
    if field and field.crop_id and field.plant_date and field.crop_id in crops:
        end = field.harvest_date
        if end is None:
            end = field.plant_date + timedelta(days=sum(stage_lengths(crops[field.crop_id])) - 1)
        name = crops[field.crop_id].profile.name
        season = SeasonPlan(crop_id=field.crop_id, plant_date=field.plant_date, end_date=end)
        return (
            Strategy(id="field-now", site_id=site_id, name="Field now", seasons=[season]),
            f"Soil water now is simulated with {name} planted {field.plant_date} (farmer input), bare soil otherwise.",
        )
    why = (
        f"the crop entered ({field.crop_id}) has no complete parameters in the catalog"
        if field and field.crop_id and field.crop_id not in crops
        else "what is on the field was not entered"
    )
    return (
        Strategy(id="field-now", site_id=site_id, name="Field now", seasons=[]),
        f"Soil water now assumes bare fallow over the last year ({why}).",
    )


def _observed_frame(weather: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    part = weather.loc[pd.Timestamp(start) : pd.Timestamp(end)].copy()
    part["source_date"] = part.index
    part["strategy_date"] = part.index
    part["block"] = 0
    return part.reset_index(drop=True)


def observed_initial_fraction(
    forcing: pd.DataFrame,
    et0: pd.DataFrame,
    soil: SoilRunConfig,
    crops: Mapping[str, CropEntry],
    *,
    site_id: str,
    field: FieldNow | None,
) -> InitialState:
    """One year of observed weather ending on ``observed_end``; days with unusable rain block the estimate."""
    end = observed_end(forcing)
    start = end - timedelta(days=SPINUP_DAYS - 1)
    frame = _observed_frame(daily_weather(forcing, et0), start, end)
    if frame["rain_mm"].isna().any() or frame["et0_mm"].isna().any():
        bad = int(frame["rain_mm"].isna().sum() + frame["et0_mm"].isna().sum())
        raise ValueError(
            f"soil water now cannot be simulated: {bad} day(s) without usable rain or ET0 in the last year"
        )
    strat, assumption = _field_now_strategy(site_id, field, crops)
    cfg = SoilRunConfig(soil=soil.soil, initial_fraction=SPINUP_START_FRACTION, warmup=False)
    traces, _ = run_strategies_on_path(
        frame, [strat], crops, cfg, mode=SimulationMode.IRRIGATION_NEEDED, allocation_mm_per_season=None
    )
    last = traces[strat.id].iloc[-1]
    storage = float(last["active_storage_mm"] + last["subsoil_storage_mm"])
    capacity = soil.awc_mm_per_m * soil.soil.data_depth_m
    return InitialState(
        fraction=float(np.clip(storage / capacity, 0.0, 1.0)),
        as_of=end,
        storage_mm=storage,
        assumption=assumption
        + f" The one-year spin-up starts at {SPINUP_START_FRACTION:g} of field capacity; the carried state is spread"
        " evenly over the profile. Irrigation is not simulated before today.",
    )


@dataclass(frozen=True)
class Bands:
    dates: list[date]
    rain_mm: dict[int, list[float | None]]
    rain_cumulative_mm: dict[int, list[float | None]]  # per path from the horizon start, then percentiles
    tmin_c: dict[int, list[float | None]]
    tmax_c: dict[int, list[float | None]]
    storage_mm: dict[int, list[float | None]]
    n_paths: int


def _pct(stack: np.ndarray) -> dict[int, list[float | None]]:
    out: dict[int, list[float | None]] = {}
    with np.errstate(all="ignore"):
        q = np.nanpercentile(stack, PERCENTILES, axis=0)
    for k, p in enumerate(PERCENTILES):
        out[p] = [None if not np.isfinite(v) else round(float(v), 2) for v in q[k]]
    return out


def outlook(
    forcing: pd.DataFrame,
    et0: pd.DataFrame,
    pool: BlockPool,
    config: SoilRunConfig,
    crops: Mapping[str, CropEntry],
    *,
    site_id: str,
    horizon: tuple[date, date],
    field: FieldNow | None,
    first_block_weights: Mapping[int, float] | None,
    seed: int,
    days: int = OUTLOOK_DAYS,
    n_paths: int = OUTLOOK_PATHS,
) -> Bands:
    """Bands over the first ``days`` of the horizon from weighted historical paths; soil water continues the
    field-now crop (bare soil after it), starting from ``config.initial_fraction`` (no warm-up)."""
    paths = bootstrap_paths(
        pool,
        n_paths=n_paths,
        horizon_years=horizon_blocks(horizon),
        seed=seed,
        first_block_weights=first_block_weights,
    )
    weather = daily_weather(forcing, et0)
    tmax = pd.Series(usable_values(forcing, TMAX), index=forcing.index)
    tmin = pd.Series(usable_values(forcing, TMIN), index=forcing.index)
    strat, _ = _field_now_strategy(site_id, field, crops)
    anchor = horizon[0].strftime("%m-%d")
    rows: dict[str, list[np.ndarray]] = {"rain": [], "rain_cum": [], "tmin": [], "tmax": [], "storage": []}
    dates: list[date] = []
    for years in paths:
        pf = build_path_forcing(weather, years, anchor_md=anchor, base_year=horizon[0].year).iloc[:days]
        traces, _ = run_strategies_on_path(
            pf, [strat], crops, config, mode=SimulationMode.IRRIGATION_NEEDED, allocation_mm_per_season=None
        )
        t = traces[strat.id]
        src = pd.DatetimeIndex(pf["source_date"])
        rain = pf["rain_mm"].to_numpy(dtype="float64")
        rows["rain"].append(rain)
        # pool blocks have usable rain every day, so the running total never treats missing rain as zero; a NaN
        # would propagate (np.cumsum), never be skipped
        rows["rain_cum"].append(np.cumsum(rain))
        rows["tmin"].append(tmin.reindex(src).to_numpy(dtype="float64"))
        rows["tmax"].append(tmax.reindex(src).to_numpy(dtype="float64"))
        rows["storage"].append((t["active_storage_mm"] + t["subsoil_storage_mm"]).to_numpy(dtype="float64"))
        if not dates:
            dates = [pd.Timestamp(d).date() for d in pf["strategy_date"]]
    n = min(len(r) for r in rows["rain"])
    stack = {k: np.vstack([r[:n] for r in v]) for k, v in rows.items()}
    return Bands(
        dates=dates[:n],
        rain_mm=_pct(stack["rain"]),
        rain_cumulative_mm=_pct(stack["rain_cum"]),
        tmin_c=_pct(stack["tmin"]),
        tmax_c=_pct(stack["tmax"]),
        storage_mm=_pct(stack["storage"]),
        n_paths=len(paths),
    )
