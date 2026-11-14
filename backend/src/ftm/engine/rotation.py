"""Rotation sequencing, hard-constraint feasibility and soil-cover indicators. Owner: M4.

A strategy becomes a daily schedule on the strategy calendar of one weather path:

- Crop days: FAO-56 single-Kc curve (eq. 66) from the cited catalog. Kc_mid and Kc_end are adjusted to
  the path's mean u2 and RHmin over the mid and late stages (FAO-56 eqs. 62 and 65; eq. 65 only when
  Kc_end > 0.45). Kc_end is held from maturity to the plan's harvest date (declared assumption). Root depth
  is the catalog maximum from planting (no root growth), capped at the depth over which soil AWC is known;
  the cap is disclosed.
- Fallow days (no crop, or an explicit fallow season): bare-soil Kc from the FAO-56 Annex 7 procedure
  (chapter 11 uses the Kc_ini procedure for bare soil), computed per fallow chunk of at most
  ``FALLOW_CHUNK_DAYS`` from that path's ET0 and infiltration. Active depth = evaporation layer Ze.
- Runoff curve numbers: TR-55 Table 2-2b cover class of the crop, or bare-soil fallow.

Missing parameters are never guessed: they make the strategy infeasible with a readable reason
(``Feasibility.reasons``), which blocks every claim that depends on them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd

from ftm.contracts.models import Feasibility, ParamValue, Strategy
from ftm.engine.kc import bare_soil_kc, climate_adjusted_kc, kc_curve, wetting_events
from ftm.engine.params import CropEntry, SoilSpec, curve_number
from ftm.engine.water_balance import runoff_mm

Stage = Literal["ini", "dev", "mid", "late"]
STAGES: tuple[Stage, ...] = ("ini", "dev", "mid", "late")

SUPPORTED_IRRIGATION_RULE = "refill_to_field_capacity_at_raw"  # the one rule ``water_balance`` implements
FALLOW_COVER = "fallow_bare_soil"  # TR-55 Table 2-2b
# FAO-56 chapter 7 (eq. 73 text): Ze, the surface layer dried by evaporation, is 0.10-0.15 m; upper value.
ZE_BARE_SOIL_M = 0.15
# Engine method choice (not an agronomic value): bare-soil Kc is re-estimated at most every 30 days so the
# seasonal change in ET0 and wetting frequency is followed. FAO-56 averages over the period being estimated.
FALLOW_CHUNK_DAYS = 30
KC_END_ADJUST_THRESHOLD = 0.45  # FAO-56 eq. 65 applies only when Kc_end (Table 12) > 0.45


@dataclass(frozen=True)
class PathWeather:
    """Daily weather of one path, on the strategy calendar. NaN = not usable that day."""

    rain_mm: np.ndarray
    et0_mm: np.ndarray
    u2_m_s: np.ndarray
    rhmin_pct: np.ndarray


@dataclass(frozen=True)
class DailySchedule:
    kc: np.ndarray
    p_table: np.ndarray  # NaN on fallow days (bare-soil days use Ks = 1)
    zr_m: np.ndarray
    cn: np.ndarray
    crop_day: np.ndarray
    irrigable: np.ndarray
    season_id: np.ndarray  # -1 on fallow days
    crop_id: np.ndarray  # object, None on fallow days
    in_initial_stage: np.ndarray  # FAO-56 initial stage: ground cover below ~10%
    notes: tuple[str, ...]  # disclosed assumptions taken for this path (root cap, unadjusted Kc, ...)


class MissingParameterError(ValueError):
    """A parameter needed for a claim is null. The claim is blocked; nothing is filled in."""


def _value(param: ParamValue, what: str) -> float:
    if param.value is None:
        raise MissingParameterError(f"{what} is missing (null in the catalog)")
    return float(param.value)


def missing_parameters(entry: CropEntry) -> list[str]:
    crop = entry.profile
    params: dict[str, ParamValue] = {
        "kc_ini": crop.kc_ini,
        "kc_mid": crop.kc_mid,
        "kc_end": crop.kc_end,
        "max_root_depth_m": crop.max_root_depth_m,
        "depletion_fraction_p": crop.depletion_fraction_p,
        "max_height_m": entry.max_height_m,
    }
    for stage in STAGES:
        params[f"stage_lengths_days.{stage}"] = crop.stage_lengths_days.get(
            stage, ParamValue(value=None, unit="days", reference=None)
        )
    return [name for name, p in params.items() if p.value is None]


def stage_lengths(entry: CropEntry) -> tuple[int, int, int, int]:
    s = entry.profile.stage_lengths_days
    ini, dev, mid, late = (int(_value(s[st], f"{entry.profile.id}.{st} length")) for st in STAGES)
    return ini, dev, mid, late


def _md(d: date) -> str:
    return d.strftime("%m-%d")


def _in_window(md: str, window: tuple[str, str]) -> bool:
    start, end = window
    return start <= md <= end if start <= end else (md >= start or md <= end)  # window may wrap the year


def check_feasibility(
    strategy: Strategy,
    crops: Mapping[str, CropEntry],
    *,
    horizon: tuple[date, date],
    soil: SoilSpec | None,
    available_crop_ids: set[str] | None = None,
) -> Feasibility:
    """Hard constraints only (priorities never filter). Every failure gets a farmer-readable reason."""
    reasons: list[str] = []
    if soil is None or soil.profile.available_water_capacity_mm_per_m.value is None:
        reasons.append("Soil available water capacity is missing; the water balance cannot run.")
    seasons = sorted(strategy.seasons, key=lambda s: s.plant_date)
    for i, s in enumerate(seasons):
        label = f"Season {i + 1} ({s.crop_id or 'fallow'}, {s.plant_date} to {s.end_date})"
        if s.end_date <= s.plant_date:
            reasons.append(f"{label}: ends before it starts.")
            continue
        if s.plant_date < horizon[0] or s.end_date > horizon[1]:
            reasons.append(f"{label}: falls outside the comparison horizon {horizon[0]} to {horizon[1]}.")
        if i > 0 and s.plant_date <= seasons[i - 1].end_date:
            reasons.append(f"{label}: overlaps the previous season, which ends {seasons[i - 1].end_date}.")
        if s.residue_management is not None:
            reasons.append(f"{label}: residue management ('{s.residue_management}') is not modelled yet.")
        if s.irrigation_rule is not None and s.irrigation_rule != SUPPORTED_IRRIGATION_RULE:
            reasons.append(
                f"{label}: irrigation rule '{s.irrigation_rule}' is not supported "
                f"(supported: '{SUPPORTED_IRRIGATION_RULE}')."
            )
        if s.crop_id is None:
            if s.irrigation_rule is not None:
                reasons.append(f"{label}: irrigating a fallow season is not supported.")
            continue
        entry = crops.get(s.crop_id)
        if entry is None:
            reasons.append(f"{label}: crop '{s.crop_id}' is not in the catalog.")
            continue
        crop = entry.profile
        if available_crop_ids is not None and s.crop_id not in available_crop_ids:
            reasons.append(f"{label}: {crop.name} is not available to this farm.")
        missing = missing_parameters(entry)
        if missing:
            reasons.append(f"{label}: {crop.name} is missing cited parameters ({', '.join(missing)}).")
            continue
        needed = sum(stage_lengths(entry))
        have = (s.end_date - s.plant_date).days
        if have < needed:
            reasons.append(f"{label}: {crop.name} needs {needed} days to mature but the season has {have}.")
        if crop.planting_window and not _in_window(_md(s.plant_date), crop.planting_window):
            w = crop.planting_window
            reasons.append(f"{label}: planting on {_md(s.plant_date)} is outside {crop.name}'s window {w[0]}-{w[1]}.")
    return Feasibility(feasible=not reasons, reasons=reasons)


def _mean_or_none(values: np.ndarray) -> float | None:
    finite = values[np.isfinite(values)]
    return float(finite.mean()) if finite.size else None


def _adjusted(kc_table: float, mask: np.ndarray, weather: PathWeather, idx: np.ndarray, h: float) -> tuple[float, bool]:
    u2 = _mean_or_none(weather.u2_m_s[idx][mask])
    rh = _mean_or_none(weather.rhmin_pct[idx][mask])
    if u2 is None or rh is None:
        return kc_table, False
    return climate_adjusted_kc(kc_table, u2, rh, h), True


def _fallow_segments(fallow: np.ndarray) -> list[tuple[int, int]]:
    """[start, stop) runs of fallow days, each split into chunks of at most FALLOW_CHUNK_DAYS."""
    out: list[tuple[int, int]] = []
    i, n = 0, len(fallow)
    while i < n:
        if not fallow[i]:
            i += 1
            continue
        j = i
        while j < n and fallow[j]:
            j += 1
        out.extend((k, min(k + FALLOW_CHUNK_DAYS, j)) for k in range(i, j, FALLOW_CHUNK_DAYS))
        i = j
    return out


def daily_schedule(
    strategy: Strategy,
    crops: Mapping[str, CropEntry],
    soil: SoilSpec,
    strategy_dates: pd.DatetimeIndex,
    weather: PathWeather,
) -> DailySchedule:
    """Map the strategy onto ``strategy_dates`` (one entry per simulated day). Call after feasibility."""
    n = len(strategy_dates)
    kc = np.full(n, np.nan)
    p_table = np.full(n, np.nan)
    zr = np.full(n, min(ZE_BARE_SOIL_M, soil.data_depth_m))
    cn = np.full(n, curve_number(FALLOW_COVER, soil.hsg))
    crop_day = np.zeros(n, dtype=bool)
    irrigable = np.zeros(n, dtype=bool)
    season_id = np.full(n, -1, dtype=int)
    crop_id = np.full(n, None, dtype=object)
    initial = np.zeros(n, dtype=bool)
    notes: list[str] = []
    days = strategy_dates.normalize()

    for sid, s in enumerate(sorted(strategy.seasons, key=lambda x: x.plant_date)):
        start, end = pd.Timestamp(s.plant_date), pd.Timestamp(s.end_date)
        mask = (days >= start) & (days <= end)
        if s.crop_id is None or not mask.any():
            continue
        entry = crops[s.crop_id]
        prof = entry.profile
        idx = np.flatnonzero(mask)
        offset = (days[mask] - start).days.to_numpy()
        lengths = stage_lengths(entry)
        kc_ini = _value(prof.kc_ini, f"{prof.id}.kc_ini")
        kc_mid_t = _value(prof.kc_mid, f"{prof.id}.kc_mid")
        kc_end_t = _value(prof.kc_end, f"{prof.id}.kc_end")
        h = _value(entry.max_height_m, f"{prof.id}.max_height_m")
        _, stage = kc_curve(lengths, kc_ini, kc_mid_t, kc_end_t, int(offset.max()) + 1)
        st = stage[offset]
        kc_mid, ok_mid = _adjusted(kc_mid_t, st == 2, weather, idx, h)
        kc_end, ok_end = kc_end_t, True
        if kc_end_t > KC_END_ADJUST_THRESHOLD:
            kc_end, ok_end = _adjusted(kc_end_t, st == 3, weather, idx, h)
        if not ok_mid or not ok_end:
            notes.append(f"{prof.name}: no usable wind/humidity in a stage; FAO-56 table Kc used unadjusted.")
        curve, stage = kc_curve(lengths, kc_ini, kc_mid, kc_end, int(offset.max()) + 1)
        root = _value(prof.max_root_depth_m, f"{prof.id}.max_root_depth_m")
        if root > soil.data_depth_m:
            notes.append(
                f"{prof.name}: root depth {root:g} m capped at {soil.data_depth_m:g} m, the depth with known soil "
                "water capacity; water below it is not counted."
            )
        kc[mask] = curve[offset]
        initial[mask] = stage[offset] == 0
        p_table[mask] = _value(prof.depletion_fraction_p, f"{prof.id}.depletion_fraction_p")
        zr[mask] = min(root, soil.data_depth_m)
        cn[mask] = curve_number(entry.tr55_cover, soil.hsg)
        crop_day[mask] = True
        irrigable[mask] = s.irrigation_rule == SUPPORTED_IRRIGATION_RULE
        season_id[mask] = sid
        crop_id[mask] = s.crop_id

    fallow_cn = curve_number(FALLOW_COVER, soil.hsg)
    for a, b in _fallow_segments(~crop_day):
        rain, et0 = weather.rain_mm[a:b], weather.et0_mm[a:b]
        infil = rain - runoff_mm(rain, fallow_cn)
        n_events, depth = wetting_events(infil, et0)
        tw = (b - a) / n_events if n_events else float(b - a)
        kc[a:b] = bare_soil_kc(float(np.mean(et0)), tw, depth, soil.annex7_class)
    return DailySchedule(
        kc, p_table, zr, cn, crop_day, irrigable, season_id, crop_id, initial, tuple(dict.fromkeys(notes))
    )


def cover_indicators(in_crop: np.ndarray, in_initial_stage: np.ndarray, crop_id: np.ndarray) -> dict[str, float]:
    """Soil-protection indicators. Low cover is *possible* exposure, not observed bare soil.

    Cover days exclude the FAO-56 initial stage (ground cover below ~10%).
    """
    crop = np.asarray(in_crop, dtype=bool)
    initial = np.asarray(in_initial_stage, dtype=bool) & crop
    return {
        "cover_days": float(np.sum(crop & ~initial)),
        "possible_low_cover_days": float(np.sum(~crop | initial)),
        "crop_diversity_count": float(len({str(c) for c in crop_id[crop] if pd.notna(c)})),
    }
