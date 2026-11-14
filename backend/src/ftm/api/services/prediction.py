"""The coming seasons for a user's farm (D16): horizon, forecast weights, today's soil water, outlook. Owner: M1.

Everything a comparison run and the Outlook card share is computed once here and cached per (weather
processing run, forecast snapshot, field-now input), so both show the same prediction:

* the horizon starts the day after the last observed NASA POWER day and runs 24 months;
* the latest ECMWF SEAS5 snapshot (Open-Meteo) gives the odds of below / near / above normal months, which
  weight the past years drawn for the first block (``engine.forecast_weights``); no snapshot = equal odds;
* today's soil water is simulated from the last observed year under what the farmer says is on the field.

The hidden reviewed farm (ks-field-2, D14) keeps its fixed 2027-2028 model calendar and is not handled here.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ftm.config import get_settings
from ftm.contracts.models import (
    FarmerContext,
    ForecastOdds,
    OutlookBand,
    PredictionHorizon,
    SeasonPlan,
    WeatherOutlook,
)
from ftm.data.adapters import forecast_openmeteo as fo
from ftm.data.engine_inputs import DEFAULT_POOL, SiteEngineInputs, load_site_engine_inputs
from ftm.data.raw_cache import RawSnapshot
from ftm.db.models import ForecastSnapshotRow, SiteRow, SourceRow
from ftm.engine.ensemble import SoilRunConfig, usable_blocks
from ftm.engine.et0 import compute_et0
from ftm.engine.forcing import RAIN, TMAX, TMIN, usable_values
from ftm.engine.forecast_weights import (
    METHOD,
    YearWeights,
    member_anomalies,
    power_window_values,
    windows,
    year_weights,
)
from ftm.engine.outlook import (
    FieldNow,
    InitialState,
    observed_end,
    observed_initial_fraction,
    outlook,
    prediction_horizon,
)
from ftm.engine.params import CropEntry, load_crops
from ftm.engine.rotation import stage_lengths

OUTLOOK_SEED = 20261115


@dataclass(frozen=True)
class Prediction:
    observed_end: date
    horizon: tuple[date, date]
    weights: YearWeights | None
    forecast_source_id: str | None
    forecast_retrieved_at: datetime | None
    forecast_attribution: str | None
    initial: InitialState
    notes: tuple[str, ...]
    standing: SeasonPlan | None = None  # crop on the field now, still growing at the horizon start


_lock = threading.Lock()
_inputs_cache: dict[tuple[str, str], tuple[SiteEngineInputs, pd.DataFrame]] = {}
_prediction_cache: dict[tuple[object, ...], Prediction] = {}
_outlook_cache: dict[tuple[object, ...], WeatherOutlook] = {}


def inputs_and_et0(session: Session, site_id: str) -> tuple[SiteEngineInputs, pd.DataFrame]:
    """Engine inputs plus ET0, cached per weather processing run (loading 45 years takes about a second)."""
    inputs = load_site_engine_inputs(session, site_id)
    key = (site_id, str(inputs.forcing.attrs.get("processing_run_id") or inputs.weather_source.id))
    with _lock:
        hit = _inputs_cache.get(key)
    if hit is not None:
        return hit
    et0 = compute_et0(inputs.forcing, latitude_deg=inputs.site.latitude, elevation_m=inputs.elevation_m)
    with _lock:
        _inputs_cache[key] = (inputs, et0)
    return inputs, et0


def latest_snapshot(session: Session, site_id: str) -> ForecastSnapshotRow | None:
    return session.scalars(
        select(ForecastSnapshotRow)
        .where(ForecastSnapshotRow.site_id == site_id)
        .order_by(ForecastSnapshotRow.retrieved_at.desc(), ForecastSnapshotRow.created_at.desc())
        .limit(1)
    ).first()


def field_now(ctx: FarmerContext | None) -> FieldNow | None:
    if ctx is None or not ctx.current_crop_id:
        return None
    return FieldNow(ctx.current_crop_id, ctx.current_plant_date, ctx.last_harvest_date)


def _farmer(session: Session, site_id: str) -> FarmerContext | None:
    row = session.get(SiteRow, site_id)
    if row is None or not row.farmer_context:
        return None
    try:
        return FarmerContext.model_validate(row.farmer_context)
    except ValueError:
        return None


def _snapshot(path: str, sha: str, retrieved: datetime) -> RawSnapshot:
    root = get_settings().raw_dir
    return RawSnapshot(root.parent / path, path, sha, retrieved)


def _weights(
    session: Session, snap: ForecastSnapshotRow, inputs: SiteEngineInputs, et0: pd.DataFrame, horizon: tuple[date, date]
) -> tuple[YearWeights | None, list[str]]:
    src = session.get(SourceRow, snap.source_id)
    if src is None or not src.raw_path or not src.raw_sha256:
        return None, ["The stored forecast snapshot has no raw file; past years are equally likely."]
    fc = fo.load(
        _snapshot(src.raw_path, src.raw_sha256, snap.retrieved_at),
        _snapshot(snap.monthly_raw_path, snap.monthly_raw_sha256, snap.retrieved_at),
    )
    complete = fc.daily["precipitation_sum"].dropna(how="any").index
    for v in ("temperature_2m_max", "temperature_2m_min"):
        complete = complete.intersection(fc.daily[v].dropna(how="any").index)
    found = windows(fc.monthly_anomaly.dropna().index, horizon[0], complete)
    if not found:
        return None, ["The forecast does not cover a whole window from the horizon start; past years equally likely."]
    pool = usable_blocks(inputs.forcing, et0, horizon[0].strftime("%m-%d"), DEFAULT_POOL)
    f = inputs.forcing
    rain = pd.Series(usable_values(f, RAIN), index=f.index)
    tmax = pd.Series(usable_values(f, TMAX), index=f.index)
    tmin = pd.Series(usable_values(f, TMIN), index=f.index)
    power, members = {}, {}
    for w in found:
        vals = power_window_values(rain, tmax, tmin, w.month_numbers)
        # Block year Y starts on the horizon's month-day in year Y; a window starting in a later calendar year than
        # the horizon (e.g. a January window after a December start) belongs to the block of the year before.
        vals.index = vals.index - (w.months[0].year - horizon[0].year)
        power[w] = vals
        members[w] = member_anomalies(fc.daily, fc.monthly_anomaly, w)
    return year_weights(pool.pool_years, power, members), []


def prediction_for(
    session: Session, site_id: str, crops: dict[str, CropEntry] | None = None
) -> tuple[Prediction, SiteEngineInputs, pd.DataFrame]:
    inputs, et0 = inputs_and_et0(session, site_id)
    snap = latest_snapshot(session, site_id)
    fn = field_now(_farmer(session, site_id))
    key = (site_id, inputs.forcing.attrs.get("processing_run_id"), snap.id if snap else None, fn)
    with _lock:
        hit = _prediction_cache.get(key)
    if hit is not None:
        return hit, inputs, et0
    catalog = crops or load_crops()
    end = observed_end(inputs.forcing)
    horizon = prediction_horizon(end)
    notes: list[str] = []
    weights: YearWeights | None = None
    src = session.get(SourceRow, snap.source_id) if snap else None
    if snap is None:
        notes.append("No seasonal forecast is stored for this farm: every past year is equally likely.")
    else:
        try:
            weights, extra = _weights(session, snap, inputs, et0, horizon)
            notes += extra
        except (ValueError, OSError) as exc:
            notes.append(f"Seasonal forecast not used ({exc}); every past year is equally likely.")
    if weights is not None:
        notes += [f"Forecast weighting: {METHOD}.", *weights.assumptions]
        notes.append(f"Effective number of past years after weighting: {weights.effective_sample_size:.1f}.")
    cfg = SoilRunConfig(soil=inputs.soil, initial_fraction=0.5)
    initial = observed_initial_fraction(inputs.forcing, et0, cfg, catalog, site_id=site_id, field=fn)
    standing = standing_season(fn, catalog, horizon[0])
    pred = Prediction(
        observed_end=end,
        horizon=horizon,
        weights=weights,
        forecast_source_id=src.id if (src and weights is not None) else None,
        forecast_retrieved_at=snap.retrieved_at if snap else None,
        forecast_attribution=src.attribution if src else None,
        initial=initial,
        notes=tuple(notes),
        standing=standing,
    )
    with _lock:
        _prediction_cache[key] = pred
    return pred, inputs, et0


def standing_season(fn: FieldNow | None, crops: dict[str, CropEntry], start: date) -> SeasonPlan | None:
    """The field-now crop as a season, when it is still in the ground on the horizon's first day."""
    if fn is None or not fn.crop_id or fn.plant_date is None or fn.crop_id not in crops:
        return None
    end = fn.harvest_date or fn.plant_date + timedelta(days=sum(stage_lengths(crops[fn.crop_id])) - 1)
    if end < start:
        return None
    return SeasonPlan(crop_id=fn.crop_id, plant_date=fn.plant_date, end_date=end)


def horizon_for(session: Session, site_id: str) -> PredictionHorizon:
    pred, inputs, _ = prediction_for(session, site_id)
    return PredictionHorizon(
        site_id=site_id,
        observed_end=pred.observed_end,
        start=pred.horizon[0],
        end=pred.horizon[1],
        weather_source_id=inputs.weather_source.id,
    )


def _band(b: dict[int, list[float | None]]) -> OutlookBand:
    return OutlookBand(p10=b[10], p50=b[50], p90=b[90])


def outlook_for(session: Session, site_id: str) -> WeatherOutlook:
    crops = load_crops()
    pred, inputs, et0 = prediction_for(session, site_id, crops)
    key = (site_id, inputs.forcing.attrs.get("processing_run_id"), pred.forecast_source_id, pred.initial)
    with _lock:
        hit = _outlook_cache.get(key)
    if hit is not None:
        return hit
    pool = usable_blocks(inputs.forcing, et0, pred.horizon[0].strftime("%m-%d"), DEFAULT_POOL)
    cfg = SoilRunConfig(soil=inputs.soil, initial_fraction=pred.initial.fraction, warmup=False)
    fn = field_now(_farmer(session, site_id))
    bands = outlook(
        inputs.forcing,
        et0,
        pool,
        cfg,
        crops,
        site_id=site_id,
        horizon=pred.horizon,
        field=fn,
        first_block_weights=pred.weights.as_dict() if pred.weights else None,
        seed=OUTLOOK_SEED,
    )
    odds = [
        ForecastOdds(
            window=o.window.label,
            months=[m.date() for m in o.window.months],
            variable=o.variable,
            below=round(o.probabilities[0], 3),
            near=round(o.probabilities[1], 3),
            above=round(o.probabilities[2], 3),
            member_count=len(o.member_anomalies),
        )
        for o in (pred.weights.odds if pred.weights else [])
    ]
    capacity = cfg.awc_mm_per_m * inputs.soil.data_depth_m
    sources = [inputs.weather_source.id, *([pred.forecast_source_id] if pred.forecast_source_id else [])]
    out = WeatherOutlook(
        site_id=site_id,
        observed_end=pred.observed_end,
        horizon_start=pred.horizon[0],
        horizon_end=pred.horizon[1],
        forecast_source_id=pred.forecast_source_id,
        forecast_retrieved_at=pred.forecast_retrieved_at,
        odds=odds,
        effective_sample_size=round(pred.weights.effective_sample_size, 1) if pred.weights else None,
        dates=bands.dates,
        rain_mm=_band(bands.rain_mm),
        rain_cumulative_mm=_band(bands.rain_cumulative_mm),
        tmin_c=_band(bands.tmin_c),
        tmax_c=_band(bands.tmax_c),
        storage_mm=_band(bands.storage_mm),
        soil_water_now_mm=round(float(np.clip(pred.initial.storage_mm, 0, capacity)), 1),
        soil_water_capacity_mm=round(capacity, 1),
        initial_assumption=pred.initial.assumption,
        n_paths=bands.n_paths,
        assumptions=list(pred.notes),
        source_ids=[*sources, *inputs.soil_profile.source_ids],
        attribution=pred.forecast_attribution if pred.forecast_source_id else None,
        limitations=[
            "Daily values are past NASA POWER years drawn with the forecast's odds; no day is a weather forecast.",
            "Soil water is simulated by the FAO-56 water balance, not measured.",
            "Seasonal forecasts have limited skill in many regions and seasons; the odds can be close to 1/3 each.",
        ],
    )
    with _lock:
        _outlook_cache[key] = out
    return out
