"""Crop coefficients and depletion fraction (FAO-56 chapters 6-8, Annex 7). Owner: M4.

Allen, Pereira, Raes & Smith (1998), FAO Irrigation and Drainage Paper 56,
https://www.fao.org/4/x0490e/x0490e00.htm
"""

from __future__ import annotations

import math

import numpy as np

from ftm.engine.params import Annex7Class

KC_INI_MAX = 1.15  # Annex 7: Kc ini from eq. 7-3 is limited to <= 1.15


def kc_curve(
    lengths_days: tuple[int, int, int, int], kc_ini: float, kc_mid: float, kc_end: float, n_days: int
) -> tuple[np.ndarray, np.ndarray]:
    """Daily Kc after planting (FAO-56 eq. 66) and the stage index (0 ini, 1 dev, 2 mid, 3 late, 4 after).

    Kc_end is held from maturity to harvest (declared assumption).
    """
    l_ini, l_dev, l_mid, l_late = lengths_days
    day = np.arange(n_days, dtype="float64")
    t_mid, t_late, t_end = l_ini + l_dev, l_ini + l_dev + l_mid, l_ini + l_dev + l_mid + l_late
    kc = np.full(n_days, kc_end)
    stage = np.full(n_days, 4, dtype=int)
    ini = day < l_ini
    dev = (day >= l_ini) & (day < t_mid)
    mid = (day >= t_mid) & (day < t_late)
    late = (day >= t_late) & (day < t_end)
    kc[ini] = kc_ini
    kc[dev] = kc_ini + (day[dev] - l_ini) / l_dev * (kc_mid - kc_ini)
    kc[mid] = kc_mid
    kc[late] = kc_mid + (day[late] - t_late) / l_late * (kc_end - kc_mid)
    for idx, mask in enumerate((ini, dev, mid, late)):
        stage[mask] = idx
    return kc, stage


def climate_adjusted_kc(kc_table: float, u2_m_s: float, rhmin_pct: float, height_m: float) -> float:
    """FAO-56 eq. 62 (Kc mid) / eq. 65 (Kc end), with inputs held to their stated validity ranges.

    Kc = Kc_tab + [0.04 (u2 - 2) - 0.004 (RHmin - 45)] (h/3)^0.3,
    for 1 <= u2 <= 6 m/s, 20 <= RHmin <= 80 %, 0.1 <= h <= 10 m.
    """
    u2 = min(max(u2_m_s, 1.0), 6.0)
    rh = min(max(rhmin_pct, 20.0), 80.0)
    h = min(max(height_m, 0.1), 10.0)
    return float(kc_table + (0.04 * (u2 - 2.0) - 0.004 * (rh - 45.0)) * (h / 3.0) ** 0.3)


def rhmin_pct(ea_kpa: np.ndarray, tmax_c: np.ndarray) -> np.ndarray:
    """Daily minimum relative humidity from actual vapour pressure and e°(Tmax) (FAO-56 eq. 63 form)."""
    es_tmax = 0.6108 * np.exp(17.27 * tmax_c / (tmax_c + 237.3))
    return np.asarray(np.clip(100.0 * ea_kpa / es_tmax, 0.0, 100.0), dtype="float64")


def adjusted_p(p_table: float, etc_mm_day: float) -> float:
    """FAO-56 Table 22 footnote 2: p = p_table + 0.04 (5 - ETc), limited to 0.1 <= p <= 0.8."""
    return min(max(p_table + 0.04 * (5.0 - etc_mm_day), 0.1), 0.8)


def wetting_events(infiltration_mm: np.ndarray, et0_mm: np.ndarray) -> tuple[int, float]:
    """Count wetting events and their mean infiltrated depth (FAO-56 Annex 7, eq. 7-7 counting rule).

    Events below 0.2 ET0 are ignored; events on adjoining days count as one event.
    """
    wet = infiltration_mm >= 0.2 * et0_mm
    wet &= infiltration_mm > 0.0
    events: list[float] = []
    depth = 0.0
    for i, w in enumerate(wet):
        if w:
            depth += float(infiltration_mm[i])
            if i == len(wet) - 1 or not wet[i + 1]:
                events.append(depth)
                depth = 0.0
    return len(events), (float(np.mean(events)) if events else 0.0)


def _kc_ini_eq73(tew: float, rew: float, et0: float, tw: float) -> float:
    """FAO-56 Annex 7 eq. 7-3 (and 7-4 when tw <= t1). Eso = 1.15 ET0 (eq. 7-1), t1 = REW / Eso."""
    eso = 1.15 * et0
    t1 = rew / eso
    if tw <= t1:
        return KC_INI_MAX
    num = tew - (tew - rew) * math.exp(-(tw - t1) * eso * (1.0 + rew / (tew - rew)) / tew)
    return min(num / (tw * et0), KC_INI_MAX)


def bare_soil_kc(et0_mean: float, tw_days: float, infil_mean_mm: float, soil: Annex7Class) -> float:
    """Kc for bare soil from wetting interval (FAO-56 Annex 7 parameter sets for Fig. 29 and 30; eq. 59).

    Light events (<= 10 mm): TEW = 10, REW = min(max(2.5, 6/ET0^0.5), 7)            (Fig. 29)
    Large events (>= 40 mm), coarse: TEW = min(15, 7 ET0^0.5), REW = min(6, TEW - 0.01)  (Fig. 30a)
    Large events (>= 40 mm), medium/fine: TEW = min(28, 13 ET0^0.5), REW = min(9, TEW - 0.01) (Fig. 30b)
    Between 10 and 40 mm: linear interpolation (FAO-56 eq. 59). Chapter 11 uses this Kc for bare soil.
    """
    if et0_mean <= 0:
        return 0.0
    tew29 = 10.0
    rew29 = min(max(2.5, 6.0 / et0_mean**0.5), 7.0)
    kc29 = _kc_ini_eq73(tew29, rew29, et0_mean, tw_days)
    if soil == "coarse":
        tew30 = min(15.0, 7.0 * et0_mean**0.5)
        rew30 = min(6.0, tew30 - 0.01)
    else:
        tew30 = min(28.0, 13.0 * et0_mean**0.5)
        rew30 = min(9.0, tew30 - 0.01)
    kc30 = _kc_ini_eq73(tew30, rew30, et0_mean, tw_days)
    if infil_mean_mm <= 10.0:
        return kc29
    if infil_mean_mm >= 40.0:
        return kc30
    return kc29 + (infil_mean_mm - 10.0) / 30.0 * (kc30 - kc29)
