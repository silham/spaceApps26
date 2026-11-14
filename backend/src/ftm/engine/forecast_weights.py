"""Seasonal-forecast odds -> weights on historical years (D16). Owner: M4.

Method: tercile-conditioned resampling of historical years, as in FResampler1 ("conditional block sampling":
daily weather drawn from historical years of a given tercile, in proportion to the forecast tercile
probabilities; Han & Ines 2017, Climate Risk Management 18:51-65, doi:10.1016/j.crm.2017.09.003). Here each
historical NASA POWER year is weighted by how likely its own tercile is under the forecast, relative to the
climatological 1/3. Engine extensions (not in that paper): rain and temperature, two windows, factors
multiplied, and a cap on concentration. The water balance runs on real POWER days only, so forecast and
reanalysis are never mixed and the forecast's level bias does not reach results.

Forecast anomalies are taken against the model's own hindcast climatology, from Open-Meteo's monthly
ensemble-mean anomaly (model climatology = ensemble mean - anomaly). Rain is compared as a share of normal
(member total / model climatology, against POWER total / POWER mean), because the model's climatology can
differ from POWER's by tens of percent and a millimetre offset would then misplace members; temperature is
compared as an additive anomaly (degC). The member spread is used as delivered (not calibrated).

Assumptions (recorded with every run): rain and temperature terciles, and the windows, are treated as
independent when weights are multiplied.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from itertools import pairwise

import numpy as np
import pandas as pd

TERCILES = ("below", "near", "above")
VARIABLES = ("rain", "temperature")
WINDOW_MONTHS = 3
MAX_WINDOWS = 2
# SEAS5 hindcasts cover 1981-2016 (Johnson et al. 2019, doi:10.5194/gmd-12-1087-2019): POWER anomalies use the
# same years where available, so both anomalies refer to a similar period.
REFERENCE_YEARS = (1981, 2016)
# Engine safeguard (D16), not a calibrated value: multiplying several window/variable odds can leave the outlook
# resting on one or two past years. The weights are then blended with equal weights just enough that at least
# this many years carry them, which also reflects the limited skill of seasonal forecasts. Recorded with runs.
MIN_EFFECTIVE_YEARS = 10.0
METHOD = "tercile-conditioned year weights (conditional block sampling, Han & Ines 2017)"


@dataclass(frozen=True)
class Window:
    label: str  # e.g. "Nov–Jan"
    months: tuple[pd.Timestamp, ...]  # first day of each forecast month

    @property
    def month_numbers(self) -> tuple[int, ...]:
        return tuple(m.month for m in self.months)


@dataclass(frozen=True)
class WindowOdds:
    window: Window
    variable: str
    probabilities: tuple[float, float, float]  # below, near, above
    thresholds: tuple[float, float]  # POWER terciles: rain as share of normal, temperature as anomaly (degC)
    member_anomalies: list[float]


@dataclass(frozen=True)
class YearWeights:
    years: list[int]
    weights: list[float]  # normalised, same order as years
    odds: list[WindowOdds]
    effective_sample_size: float
    assumptions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[int, float]:
        return dict(zip(self.years, self.weights, strict=True))


def windows(monthly_index: pd.DatetimeIndex, start: date, daily_index: pd.DatetimeIndex) -> list[Window]:
    """Consecutive 3-month windows from the month holding ``start``, fully covered by the daily members."""
    first = pd.Timestamp(start.year, start.month, 1)
    months = [m for m in monthly_index if m >= first]
    out: list[Window] = []
    for k in range(MAX_WINDOWS):
        group = tuple(months[k * WINDOW_MONTHS : (k + 1) * WINDOW_MONTHS])
        if len(group) < WINDOW_MONTHS or any(not _month_covered(daily_index, m) for m in group):
            break
        if any((b.year * 12 + b.month) - (a.year * 12 + a.month) != 1 for a, b in pairwise(group)):
            break
        out.append(Window(f"{group[0]:%b}–{group[-1]:%b}", group))
    return out


def _month_covered(daily_index: pd.DatetimeIndex, month: pd.Timestamp) -> bool:
    days = pd.date_range(month, month + pd.offsets.MonthEnd(0), freq="D")
    return bool(days.isin(daily_index).all())


def _month_slice(df: pd.DataFrame, month: pd.Timestamp) -> pd.DataFrame:
    return df.loc[month : month + pd.offsets.MonthEnd(0)]


def member_anomalies(
    daily: dict[str, pd.DataFrame], monthly_anomaly: pd.DataFrame, window: Window
) -> dict[str, np.ndarray]:
    """Per member: rain as a share of the model's normal for the window (1.0 = normal), temperature as the
    mean anomaly (degC) against the model's normal."""
    totals, clim, temp = [], 0.0, []
    for m in window.months:
        if m not in monthly_anomaly.index:
            raise ValueError(f"no monthly anomaly for {m:%Y-%m}")
        p = _month_slice(daily["precipitation_sum"], m)
        tx = _month_slice(daily["temperature_2m_max"], m)
        tn = _month_slice(daily["temperature_2m_min"], m)
        if p.isna().any().any() or tx.isna().any().any() or tn.isna().any().any():
            raise ValueError(f"forecast members have missing days in {m:%Y-%m}")
        if not (p.shape[1] == tx.shape[1] == tn.shape[1]):
            raise ValueError(f"forecast member counts differ between variables in {m:%Y-%m}")
        total = p.to_numpy().sum(axis=0)
        # positional, not by column label: Tmax and Tmin member columns carry different names
        mid = ((tx.to_numpy() + tn.to_numpy()) / 2).mean(axis=0)
        totals.append(total)
        clim += float(total.mean()) - float(monthly_anomaly.loc[m, "precipitation_mm"])
        temp.append(mid - mid.mean() + float(monthly_anomaly.loc[m, "temperature_k"]))
    if clim <= 0:
        raise ValueError(f"the model's normal rain for {window.label} is not positive; no share of normal")
    out = {"rain": np.sum(totals, axis=0) / clim, "temperature": np.mean(temp, axis=0)}
    for var, values in out.items():
        if not np.isfinite(values).all():
            raise ValueError(f"non-finite forecast {var} anomaly in window {window.label}")
    return out


def power_window_values(
    rain_mm: pd.Series, tmax_c: pd.Series, tmin_c: pd.Series, month_numbers: Sequence[int]
) -> pd.DataFrame:
    """Per historical year Y (the year of the window's first month): rain total and mean mid-range temp.

    A month that crosses into the next calendar year (e.g. Nov, Dec, Jan) is taken from Y+1. Any missing day
    leaves that year's value NaN: missing rain is not zero rain.
    """
    first = month_numbers[0]
    rows = {}
    years = sorted(set(rain_mm.index.year))
    for y in years:
        r_tot, t_vals, ok = 0.0, [], True
        for mn in month_numbers:
            yy = y if mn >= first else y + 1
            start = pd.Timestamp(yy, mn, 1)
            sl = slice(start, start + pd.offsets.MonthEnd(0))
            r, tx, tn = rain_mm.loc[sl], tmax_c.loc[sl], tmin_c.loc[sl]
            n_days = (start + pd.offsets.MonthEnd(0)).day
            if len(r) < n_days or r.isna().any() or tx.isna().any() or tn.isna().any():
                ok = False
                break
            r_tot += float(r.sum())
            t_vals.append(float(((tx + tn) / 2).mean()))
        if ok:
            rows[y] = {"rain": r_tot, "temperature": float(np.mean(t_vals))}
    return pd.DataFrame.from_dict(rows, orient="index", columns=list(VARIABLES))


def _tercile(value: float, thresholds: tuple[float, float]) -> int:
    if not np.isfinite(value):
        raise ValueError("a missing value has no tercile")  # never counted as "near normal"
    lo, hi = thresholds
    return 0 if value < lo else (2 if value > hi else 1)


def year_weights(
    years: Sequence[int],
    power: dict[Window, pd.DataFrame],
    members: dict[Window, dict[str, np.ndarray]],
    reference_years: tuple[int, int] = REFERENCE_YEARS,
) -> YearWeights:
    """Weight per pool year = prod over windows and variables of P_forecast(tercile of the year) / (1/3)."""
    weights = np.ones(len(years), dtype="float64")
    odds: list[WindowOdds] = []
    for w, vals in power.items():
        ref = vals.loc[[y for y in vals.index if reference_years[0] <= y <= reference_years[1]]]
        if len(ref) < 10:
            raise ValueError(f"window {w.label}: only {len(ref)} complete reference years")
        for var in VARIABLES:
            if var == "rain":  # share of normal, as for the forecast members
                if ref[var].mean() <= 0:
                    raise ValueError(f"window {w.label}: no rain in the reference years; no share of normal")
                anomalies = vals[var] / ref[var].mean()
                ref_anom = ref[var] / ref[var].mean()
            else:
                anomalies = vals[var] - ref[var].mean()
                ref_anom = ref[var] - ref[var].mean()
            lo, hi = (float(q) for q in np.quantile(ref_anom, [1 / 3, 2 / 3]))
            mem = members[w][var]
            cats = np.array([_tercile(float(v), (lo, hi)) for v in mem])
            probs = tuple(float((cats == k).mean()) for k in range(3))
            odds.append(WindowOdds(w, var, probs, (lo, hi), [float(v) for v in mem]))  # type: ignore[arg-type]
            for i, y in enumerate(years):
                if y in anomalies.index and np.isfinite(anomalies.loc[y]):
                    weights[i] *= probs[_tercile(float(anomalies.loc[y]), (lo, hi))] * 3.0
                # a pool year without a complete window keeps its factor 1 (neutral), never dropped silently
    total = weights.sum()
    if total <= 0:
        # every pool year falls in terciles the members never reached: fall back to equal odds, stated
        weights = np.ones(len(years))
        total = weights.sum()
        note = ["No pool year matched the forecast terciles; equal weights used."]
    else:
        note = []
    norm = weights / total
    norm, blend = _limit_concentration(norm, min(MIN_EFFECTIVE_YEARS, float(len(norm))))
    if blend > 0:
        note.append(
            f"The forecast odds were blended {blend:.0%} with equal odds so that at least "
            f"{MIN_EFFECTIVE_YEARS:g} past years carry the outlook."
        )
    ess = _ess(norm)
    return YearWeights(
        years=list(years),
        weights=[float(x) for x in norm],
        odds=odds,
        effective_sample_size=ess,
        assumptions=[
            "Rain and temperature terciles, and successive windows, are treated as independent.",
            "Forecast member spread is used as delivered (not calibrated against observations).",
            f"Forecast against its own hindcast climatology (Open-Meteo); NASA POWER against its "
            f"{reference_years[0]}–{reference_years[1]} mean. Rain as a share of normal, temperature as an anomaly.",
            *note,
        ],
    )


def _ess(w: np.ndarray) -> float:
    return float(1.0 / np.sum(w**2))


def _limit_concentration(w: np.ndarray, min_ess: float) -> tuple[np.ndarray, float]:
    """Smallest blend with equal weights (bisection) whose effective sample size reaches ``min_ess``."""
    if _ess(w) >= min_ess - 1e-9:
        return w, 0.0
    u = np.full(len(w), 1.0 / len(w))
    lo, hi = 0.0, 1.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if _ess((1 - mid) * w + mid * u) >= min_ess:
            hi = mid
        else:
            lo = mid
    return (1 - hi) * w + hi * u, hi


def uniform(years: Sequence[int]) -> YearWeights:
    n = len(years)
    return YearWeights(list(years), [1.0 / n] * n, [], float(n), ["No forecast: every past year equally likely."])
