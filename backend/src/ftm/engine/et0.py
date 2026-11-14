"""Daily reference evapotranspiration (ET0). Owner: M4.

Primary: FAO-56 Penman-Monteith via ``pyfao56.refet.ascedaily('S', ...)`` (ASCE standardized short
reference; Cn=900, Cd=0.34 is the FAO-56 grass reference at a daily step). Allen et al. (1998) FAO
Irrigation and Drainage Paper 56, https://www.fao.org/4/x0490e/x0490e00.htm

``ascedaily`` silently substitutes Tdew = Tmin - 2 degC for missing humidity and 2 m/s for missing wind.
We never pass NaN into it: every input is checked against its quality flag first, so gaps cannot turn
into unflagged estimates.

Per-day fallback (agreed by M4, proposed on PR #2): if Rs, wind or humidity is unusable but Tmax/Tmin are
usable, Hargreaves (FAO-56 eq. 52) is used for that day and the method is recorded. If Tmax or Tmin is
unusable, ET0 is NaN and the season block is excluded downstream (``ensemble.usable_blocks``).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from pyfao56.refet import ascedaily

from ftm.engine.forcing import RH, RS, TDEW, TMAX, TMIN, WIND, usable_values

PM_TDEW = "penman_monteith_tdew"
PM_RH = "penman_monteith_rhmean"
HARGREAVES = "hargreaves"

GSC_MJ_M2_MIN = 0.0820  # solar constant, FAO-56 eq. 21
MJ_M2_DAY_TO_MM_DAY = 0.408  # equivalent evaporation, FAO-56 eq. 20 (1 / lambda, lambda = 2.45 MJ/kg)


def sat_vapour_pressure_kpa(t_c: np.ndarray | float) -> np.ndarray:
    """e°(T) in kPa, FAO-56 eq. 11."""
    t = np.asarray(t_c, dtype="float64")
    return np.asarray(0.6108 * np.exp(17.27 * t / (t + 237.3)), dtype="float64")


def ea_from_tdew_kpa(tdew_c: np.ndarray | float) -> np.ndarray:
    """Actual vapour pressure from dew point, FAO-56 eq. 14."""
    return sat_vapour_pressure_kpa(tdew_c)


def ea_from_rhmean_kpa(rh_mean_pct: np.ndarray, tmax_c: np.ndarray, tmin_c: np.ndarray) -> np.ndarray:
    """Actual vapour pressure from mean relative humidity, FAO-56 eq. 19 (least preferred humidity route)."""
    es = (sat_vapour_pressure_kpa(tmax_c) + sat_vapour_pressure_kpa(tmin_c)) / 2.0
    return np.asarray(np.asarray(rh_mean_pct, dtype="float64") / 100.0 * es, dtype="float64")


def ra_mj_m2_day(latitude_deg: float, doy: np.ndarray | int) -> np.ndarray:
    """Extraterrestrial radiation Ra in MJ m-2 day-1, FAO-56 eqs. 21-25."""
    j = np.asarray(doy, dtype="float64")
    phi = math.radians(latitude_deg)
    dr = 1.0 + 0.033 * np.cos(2.0 * math.pi * j / 365.0)  # eq. 23
    delta = 0.409 * np.sin(2.0 * math.pi * j / 365.0 - 1.39)  # eq. 24
    ws = np.arccos(np.clip(-math.tan(phi) * np.tan(delta), -1.0, 1.0))  # eq. 25, clipped for polar days
    return (
        (24.0 * 60.0 / math.pi)
        * GSC_MJ_M2_MIN
        * dr
        * (ws * math.sin(phi) * np.sin(delta) + math.cos(phi) * np.cos(delta) * np.sin(ws))
    )


def hargreaves_et0_mm_day(tmax_c: np.ndarray, tmin_c: np.ndarray, ra_mj_m2_day_: np.ndarray) -> np.ndarray:
    """Hargreaves ET0, FAO-56 eq. 52. Ra is converted from MJ m-2 day-1 to mm day-1 (x0.408, eq. 20).

    FAO-56 notes this equation can over-predict in humid conditions; fallback days are counted and disclosed.
    """
    tmax = np.asarray(tmax_c, dtype="float64")
    tmin = np.asarray(tmin_c, dtype="float64")
    tmean = (tmax + tmin) / 2.0  # FAO-56 eq. 9
    trange = tmax - tmin
    ra_mm = MJ_M2_DAY_TO_MM_DAY * np.asarray(ra_mj_m2_day_, dtype="float64")
    with np.errstate(invalid="ignore"):
        out = 0.0023 * (tmean + 17.8) * np.sqrt(trange) * ra_mm
    return np.where(trange >= 0, out, np.nan)


def compute_et0(forcing: pd.DataFrame, *, latitude_deg: float, elevation_m: float) -> pd.DataFrame:
    """Return ``et0_mm_day``, ``et0_method`` and ``ea_kpa`` per day (index = forcing index).

    ``ea_kpa`` is the actual vapour pressure from dew point (eq. 14) or, failing that, mean RH (eq. 19);
    NaN when neither is usable. It is reused for RHmin in the Kc climate adjustment (FAO-56 eq. 63).

    ``forcing`` must already pass ``assert_forcing_contract``. ``elevation_m`` is required: the engine never
    assumes sea level. Its source must be disclosed by the caller (farm elevation, POWER grid fallback).
    """
    if not math.isfinite(elevation_m):
        raise ValueError("elevation_m is required for Penman-Monteith; it is never assumed")
    tmax = usable_values(forcing, TMAX)
    tmin = usable_values(forcing, TMIN)
    rs = usable_values(forcing, RS)
    u2 = usable_values(forcing, WIND)
    ea_dew = ea_from_tdew_kpa(usable_values(forcing, TDEW))
    ea_rh = ea_from_rhmean_kpa(usable_values(forcing, RH), tmax, tmin)
    doy = forcing.index.day_of_year.to_numpy()

    temps_ok = np.isfinite(tmax) & np.isfinite(tmin) & (tmax >= tmin)
    et0 = np.full(len(forcing), np.nan)
    method = np.full(len(forcing), None, dtype=object)

    for i in np.flatnonzero(temps_ok & np.isfinite(rs) & np.isfinite(u2)):
        if np.isfinite(ea_dew[i]):
            ea, m = ea_dew[i], PM_TDEW
        elif np.isfinite(ea_rh[i]):
            ea, m = ea_rh[i], PM_RH
        else:
            continue
        et0[i] = ascedaily(
            "S", elevation_m, latitude_deg, int(doy[i]), rs[i], tmax[i], tmin[i], vapr=ea, wndsp=u2[i], wndht=2.0
        )
        method[i] = m

    fallback = temps_ok & ~np.isfinite(et0)
    if fallback.any():
        ra = ra_mj_m2_day(latitude_deg, doy[fallback])
        et0[fallback] = hargreaves_et0_mm_day(tmax[fallback], tmin[fallback], ra)
        method[fallback] = HARGREAVES

    ea_used = np.where(np.isfinite(ea_dew), ea_dew, ea_rh)
    return pd.DataFrame({"et0_mm_day": et0, "et0_method": method, "ea_kpa": ea_used}, index=forcing.index)
