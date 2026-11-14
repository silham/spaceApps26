"""Planting dates from local temperature, FAO-56 Table 11 footnote 2. Owner: M4.

FAO-56 (Allen et al. 1998), Table 11, footnote 2, used when local planting dates are not available:
- spring planting of maize (grain) is presumed when the 10-day running average of mean daily air
  temperature *increases* to 13 degC;
- fall planting of winter wheat (northern temperate climates) is presumed when that average *decreases*
  to 17 degC, or on December 1, whichever comes first.

Mean daily temperature is (Tmax + Tmin) / 2 (FAO-56 eq. 9). The running average is trailing (the 10 days
ending on the day), so the rule only uses temperatures known on that day. The date is the first day in the
planting window (maize 1 Feb-31 Jul, winter wheat 1 Aug-1 Dec) on which the average is at or past the
threshold. Each pool year gives one date;
the strategy calendar uses the median day of year across the pool years (declared engine choice), and the
spread is reported. Years with any unusable temperature in the search window give no date (not filled).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

import numpy as np
import pandas as pd

from ftm.engine.forcing import TMAX, TMIN, usable_values

Rule = Literal["maize_spring_13c", "winter_wheat_fall_17c"]
RULE_TEXT: dict[Rule, str] = {
    "maize_spring_13c": "FAO-56 Table 11 footnote 2: 10-day running mean air temperature rises to 13 degC",
    "winter_wheat_fall_17c": (
        "FAO-56 Table 11 footnote 2: 10-day running mean air temperature falls to 17 degC, or 1 Dec"
    ),
}
WINDOW_DAYS = 10


@dataclass(frozen=True)
class PlantingDate:
    rule: Rule
    month_day: str  # MM-DD used on the strategy calendar (median day of year over the pool)
    per_year: dict[int, str]  # year -> MM-DD where the rule fired
    years_without_date: list[int]  # temperature gap in the search window: no date, never filled
    spread: tuple[str, str]  # p10 and p90 MM-DD across years (spread, not an uncertainty claim)
    reference: str

    def on(self, year: int) -> date:
        return date.fromisoformat(f"{year}-{self.month_day}")


def _md(doy: float, year: int = 2001) -> str:  # non-leap reference year for day-of-year -> MM-DD
    return (date(year, 1, 1) + timedelta(days=round(doy) - 1)).strftime("%m-%d")


def _year_date(tmean_10d: pd.Series, rule: Rule, year: int) -> pd.Timestamp | None:
    if rule == "maize_spring_13c":
        win = tmean_10d.loc[f"{year}-02-01" : f"{year}-07-31"]
        if win.isna().any():
            return None
        hits = win[win >= 13.0]
    else:
        win = tmean_10d.loc[f"{year}-08-01" : f"{year}-12-01"]
        if win.isna().any():
            return None
        hits = win[win <= 17.0]
        if hits.empty:
            return pd.Timestamp(f"{year}-12-01")  # "or December 1, whichever comes first"
    return None if hits.empty else pd.Timestamp(hits.index[0])


def planting_date(forcing: pd.DataFrame, rule: Rule, years: list[int]) -> PlantingDate:
    """Apply the FAO-56 footnote rule to each year of ``years`` and summarise it on a strategy calendar."""
    tmean = pd.Series((usable_values(forcing, TMAX) + usable_values(forcing, TMIN)) / 2.0, index=forcing.index)
    tmean_10d = tmean.rolling(WINDOW_DAYS, min_periods=WINDOW_DAYS).mean()
    per_year: dict[int, str] = {}
    missing: list[int] = []
    doys: list[int] = []
    for y in years:
        hit = _year_date(tmean_10d, rule, y)
        if hit is None:
            missing.append(y)
            continue
        per_year[y] = hit.strftime("%m-%d")
        doys.append(hit.day_of_year - (1 if hit.is_leap_year and hit.month > 2 else 0))
    if not doys:
        raise ValueError(f"{RULE_TEXT[rule]}: no year with usable temperatures; planting date unknown")
    p10, p50, p90 = np.percentile(doys, [10, 50, 90])
    return PlantingDate(
        rule=rule,
        month_day=_md(p50),
        per_year=per_year,
        years_without_date=missing,
        spread=(_md(p10), _md(p90)),
        reference=f"{RULE_TEXT[rule]}; median over {len(doys)} year(s) {min(per_year)}-{max(per_year)}",
    )
