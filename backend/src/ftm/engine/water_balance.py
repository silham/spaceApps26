"""Daily soil-water balance, single crop coefficient (FAO-56 chapter 8). Owner: M4.

Why not ``pyfao56.Model``: it implements the dual coefficient (Kcb + evaporation layer) for one crop per
run. The contracts carry single Kc (``CropProfile.kc_*``), rotations need fallow periods, and storage must
carry across crops with different root depths. ET0 still comes from pyfao56 (``engine.et0``).

The soil profile of depth D (the depth over which soil AWC is known) is split into an active zone of
depth Zr (crop root zone, or the evaporation layer Ze on bare soil) and the subsoil below it.
Capacities: TAW_r = AWC * Zr (FAO-56 eq. 82 per unit depth) and TAW_s = AWC * (D - Zr).
When Zr changes (a new crop, or fallow), water moves between the stores in proportion to the depth that
changes hands, assuming uniform water content within each store. Water is conserved by construction.

Per day:

1. runoff RO = (P - 0.2 S)^2 / (P + 0.8 S) for P > 0.2 S, with S = 25.4 (1000/CN - 10) mm
   (TR-55 eqs. 2-3 and 2-4, converted from inches); infiltration = P - RO enters the active zone.
2. irrigation (stated rule, crop days that allow irrigation): if active-zone depletion after infiltration
   exceeds RAW = p * TAW_r, refill to field capacity (net irrigation, 100% efficiency, declared).
   FIXED_ALLOCATION caps the depth by the remaining seasonal allocation; an exhausted allocation means
   stress, never extra water. ``irrigation_shortfall_mm`` is the refill the rule could not deliver that day;
   it is a state that persists across days, so it is never summed (the metric counts shortfall days).
3. ET: on crop days ETc = Kc * ET0 and Ks follows FAO-56 eq. 84, with p adjusted for ETc (FAO-56 Table 22
   footnote 2), evaluated after the day's water inputs. On bare-soil days the FAO-56 Annex 7 / chapter 11
   bare-soil Kc already describes surface drying, so Ks = 1. AET = min(Ks * ETc, active-zone water).
4. water above TAW_r percolates to the subsoil; water above TAW_s leaves the profile as deep drainage
   (FAO-56 eq. 88 applied at the bottom of the profile).

Mass balance per day, exact: S_end - S_start = infiltration + irrigation - AET - drainage,
with S = active-zone + subsoil storage. Missing rain or ET0 raises ``ForcingGapError``; NaN is never
coerced to 0 (guide section 6).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ftm.contracts.models import SimulationMode
from ftm.engine.forcing import ForcingGapError
from ftm.engine.kc import adjusted_p

IRRIGATION_RULE = (
    "refill the root zone to field capacity when depletion exceeds RAW = p x TAW (net irrigation, 100% efficiency)"
)
TRACE_COLUMNS = (
    "storage_start_mm",
    "rain_mm",
    "runoff_mm",
    "infiltration_mm",
    "irrigation_mm",
    "irrigation_shortfall_mm",
    "etc_mm",
    "ks",
    "aet_mm",
    "percolation_mm",
    "drainage_mm",
    "active_depth_m",
    "active_taw_mm",
    "active_storage_mm",
    "subsoil_storage_mm",
    "storage_end_mm",
)


@dataclass(frozen=True)
class BucketInputs:
    """Daily arrays of equal length."""

    rain_mm: np.ndarray
    et0_mm: np.ndarray
    kc: np.ndarray
    p_table: np.ndarray  # FAO-56 Table 22 depletion fraction, crop days only (NaN on bare-soil days)
    zr_m: np.ndarray  # active depth: crop root depth, or evaporation-layer depth on bare soil
    cn: np.ndarray  # TR-55 curve number for that day's cover
    crop_day: np.ndarray  # bool: crop in the ground (Ks applies); False = bare soil
    irrigable: np.ndarray  # bool: irrigation allowed on this day
    season_id: np.ndarray  # int: days sharing one irrigation allocation (-1 = none)


def runoff_mm(rain_mm: np.ndarray | float, cn: np.ndarray | float) -> np.ndarray:
    """TR-55 (1986) eq. 2-3 with eq. 2-4, in millimetres: S = 25.4 (1000/CN - 10), Ia = 0.2 S."""
    p = np.asarray(rain_mm, dtype="float64")
    s = 25.4 * (1000.0 / np.asarray(cn, dtype="float64") - 10.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        q = np.where(p > 0.2 * s, (p - 0.2 * s) ** 2 / (p + 0.8 * s), 0.0)
    return np.asarray(np.minimum(q, p), dtype="float64")


def ks_fao56(depletion_mm: float, taw_mm: float, p: float) -> float:
    """Water-stress coefficient, FAO-56 eq. 84 (Ks = 1 while Dr <= RAW = p TAW)."""
    if depletion_mm <= p * taw_mm:
        return 1.0
    return max(0.0, (taw_mm - depletion_mm) / ((1.0 - p) * taw_mm))


@dataclass(frozen=True)
class SoilState:
    """Water held in the active zone and the subsoil (mm), with the active-zone depth they refer to (m)."""

    active_mm: float
    subsoil_mm: float
    active_depth_m: float


def state_at_fraction(fraction: float, *, awc_mm_per_m: float, profile_depth_m: float, depth_m: float) -> SoilState:
    """Uniform profile at ``fraction`` of field capacity (a declared initial condition)."""
    if not 0.0 <= fraction <= 1.0:
        raise ValueError("initial fraction of field capacity must be within [0, 1]")
    return SoilState(fraction * awc_mm_per_m * depth_m, fraction * awc_mm_per_m * (profile_depth_m - depth_m), depth_m)


def end_state(trace: pd.DataFrame) -> SoilState:
    last = trace.iloc[-1]
    return SoilState(float(last["active_storage_mm"]), float(last["subsoil_storage_mm"]), float(last["active_depth_m"]))


def _validate(
    inputs: BucketInputs,
    awc_mm_per_m: float,
    profile_depth_m: float,
    state: SoilState,
    mode: SimulationMode,
    allocation_mm_per_season: float | None,
) -> None:
    n = len(inputs.rain_mm)
    arrays = (
        inputs.et0_mm,
        inputs.kc,
        inputs.p_table,
        inputs.zr_m,
        inputs.cn,
        inputs.crop_day,
        inputs.irrigable,
        inputs.season_id,
    )
    if any(len(a) != n for a in arrays):
        raise ValueError("all daily input arrays must have the same length")
    if not awc_mm_per_m > 0 or not profile_depth_m > 0:
        raise ValueError("awc_mm_per_m and profile_depth_m must be > 0")
    if not 0 < state.active_depth_m <= profile_depth_m + 1e-9:
        raise ValueError("initial active depth must be in (0, profile_depth_m]")
    tol = 1e-6
    cap_a, cap_s = awc_mm_per_m * state.active_depth_m, awc_mm_per_m * (profile_depth_m - state.active_depth_m)
    if not (-tol <= state.active_mm <= cap_a + tol and -tol <= state.subsoil_mm <= cap_s + tol):
        raise ValueError("initial storages must be within [0, capacity] of their stores")
    for name, arr in (("rain", inputs.rain_mm), ("ET0", inputs.et0_mm), ("Kc", inputs.kc)):
        bad = np.flatnonzero(~np.isfinite(arr))
        if bad.size:
            raise ForcingGapError(f"{name} is NaN on {bad.size} day(s), first at position {bad[0]}; never 0")
    if np.any(inputs.rain_mm < 0) or np.any(inputs.et0_mm < 0) or np.any(inputs.kc < 0):
        raise ValueError("rain, ET0 and Kc must be >= 0")
    if np.any(~np.isfinite(inputs.zr_m)) or np.any((inputs.zr_m <= 0) | (inputs.zr_m > profile_depth_m + 1e-9)):
        raise ValueError("active depth zr_m must be in (0, profile_depth_m]")
    if np.any(~np.isfinite(inputs.cn)) or np.any((inputs.cn <= 0) | (inputs.cn > 100)):
        raise ValueError("curve numbers must be in (0, 100]")
    p_crop = inputs.p_table[inputs.crop_day.astype(bool)]
    if np.any(~np.isfinite(p_crop)) or np.any((p_crop <= 0) | (p_crop >= 1)):
        raise ValueError("depletion fraction p must be in (0, 1) on every crop day")
    if mode is SimulationMode.FIXED_ALLOCATION and (allocation_mm_per_season is None or allocation_mm_per_season < 0):
        raise ValueError("fixed_allocation mode requires allocation_mm_per_season >= 0")


def simulate_bucket(
    inputs: BucketInputs,
    *,
    awc_mm_per_m: float,
    profile_depth_m: float,
    initial_state: SoilState,
    mode: SimulationMode,
    allocation_mm_per_season: float | None = None,
    index: pd.Index | None = None,
) -> pd.DataFrame:
    """Run the daily balance; one row per day with every flux (mm), Ks and both storages.

    ``initial_state`` is redistributed to day 0's active depth like any other depth change.
    """
    _validate(inputs, awc_mm_per_m, profile_depth_m, initial_state, mode, allocation_mm_per_season)
    n = len(inputs.rain_mm)
    ro_all = runoff_mm(inputs.rain_mm, inputs.cn)
    out = {c: np.zeros(n) for c in TRACE_COLUMNS}
    remaining: dict[int, float] = {}
    zr_prev = float(initial_state.active_depth_m)
    active = max(0.0, float(initial_state.active_mm))
    sub = max(0.0, float(initial_state.subsoil_mm))

    for i in range(n):
        zr = float(inputs.zr_m[i])
        if zr > zr_prev:
            moved = sub * (zr - zr_prev) / (profile_depth_m - zr_prev)  # active zone takes over subsoil layer
            active, sub = active + moved, sub - moved
        elif zr < zr_prev:
            moved = active * (zr_prev - zr) / zr_prev  # lower part of the old active zone becomes subsoil
            active, sub = active - moved, sub + moved
        zr_prev = zr
        cap_a = awc_mm_per_m * zr
        cap_s = awc_mm_per_m * (profile_depth_m - zr)
        out["storage_start_mm"][i] = active + sub

        rain = float(inputs.rain_mm[i])
        ro = float(ro_all[i])
        inf = rain - ro
        active += inf

        etc = float(inputs.kc[i] * inputs.et0_mm[i])
        crop = bool(inputs.crop_day[i])
        p = adjusted_p(float(inputs.p_table[i]), etc) if crop else float(inputs.p_table[i])

        irr = short = 0.0
        depletion = max(0.0, cap_a - active)
        if crop and inputs.irrigable[i] and depletion > p * cap_a:
            if mode is SimulationMode.IRRIGATION_NEEDED:
                irr = depletion
            else:
                sid = int(inputs.season_id[i])
                left = remaining.setdefault(sid, float(allocation_mm_per_season or 0.0))
                irr = min(depletion, left)
                remaining[sid] = left - irr
                short = depletion - irr
        active += irr

        ks = ks_fao56(max(0.0, cap_a - active), cap_a, p) if crop else 1.0
        aet = min(ks * etc, active)
        active -= aet
        perc = max(0.0, active - cap_a)
        active -= perc
        sub += perc
        drain = max(0.0, sub - cap_s)
        sub -= drain

        out["rain_mm"][i] = rain
        out["runoff_mm"][i] = ro
        out["infiltration_mm"][i] = inf
        out["irrigation_mm"][i] = irr
        out["irrigation_shortfall_mm"][i] = short
        out["etc_mm"][i] = etc
        out["ks"][i] = ks
        out["aet_mm"][i] = aet
        out["percolation_mm"][i] = perc
        out["drainage_mm"][i] = drain
        out["active_depth_m"][i] = zr
        out["active_taw_mm"][i] = cap_a
        out["active_storage_mm"][i] = active
        out["subsoil_storage_mm"][i] = sub
        out["storage_end_mm"][i] = active + sub

    return pd.DataFrame(out, index=index)
