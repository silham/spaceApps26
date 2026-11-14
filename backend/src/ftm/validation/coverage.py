"""Held-out weather-coverage evaluation (chronological / rolling splits). Owner: M5.

Report empirical coverage, interval width and sample counts on an untouched test period. This is NOT
crop/water-model validation (guide section 8.4).

Pre-registered in docs/validation-plan.md section 3:
- Targets are weather-derived seasonal totals (rain, reference ET0, rain - ET0) per season window.
- The ensemble for a target year is built only from years before it (rolling origin), or from the sample
  pool for the final test. The ensemble itself comes from the simulation engine (M4), passed in here as
  ``ensemble_fn(pool_years, target_year) -> array of simulated seasonal values``.
- Reading of the 95 % Clopper-Pearson interval on the hit rate: upper bound < 0.80 -> "under-covers";
  lower bound > 0.80 -> "over-covers (ranges wider than needed)"; otherwise "consistent with 80 %, small n".
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
from scipy.stats import binomtest

from ftm.validation.phenology import TEST_YEARS, TestPeriodLockedError

NOMINAL = 0.80
LOW_Q, HIGH_Q = 0.10, 0.90

EnsembleFn = Callable[[Sequence[int], int], np.ndarray]


@dataclass(frozen=True)
class SeasonWindow:
    """A season as month/day bounds; may cross the new year (e.g. winter wheat Oct 1 - Jun 30)."""

    start_md: tuple[int, int]
    end_md: tuple[int, int]

    def bounds(self, year: int) -> tuple[date, date]:
        """Window ending in ``year`` (a window crossing new year starts the previous year)."""
        crosses = self.end_md < self.start_md
        return date(year - 1 if crosses else year, *self.start_md), date(year, *self.end_md)


def seasonal_totals(daily: pd.DataFrame, window: SeasonWindow, columns: Sequence[str]) -> pd.DataFrame:
    """Per-year totals of ``columns`` inside the window. A window with any missing day gives NaN (never 0)."""
    idx = pd.to_datetime(daily.index)
    rows = []
    for y in sorted({d.year for d in idx}):
        a, b = window.bounds(y)
        part = daily[(idx >= pd.Timestamp(a)) & (idx <= pd.Timestamp(b))]
        expected = (b - a).days + 1
        rows.append(
            {
                "year": y,
                **{c: (part[c].sum() if len(part) == expected and part[c].notna().all() else np.nan) for c in columns},
            }
        )
    return pd.DataFrame(rows).set_index("year")


def coverage_summary(observed: dict[int, float], ensembles: dict[int, np.ndarray]) -> dict[str, object]:
    """Hit rate of observed values inside each year's ensemble p10-p90, with a 95 % Clopper-Pearson interval."""
    years = sorted(y for y in observed if y in ensembles and not np.isnan(observed[y]))
    hits, widths, rows = 0, [], []
    for y in years:
        sims = np.asarray(ensembles[y], dtype=float)
        lo, hi = np.quantile(sims, [LOW_Q, HIGH_Q])
        hit = bool(lo <= observed[y] <= hi)
        hits += hit
        widths.append(hi - lo)
        rows.append({"year": y, "observed": observed[y], "p10": lo, "p90": hi, "inside": hit, "n_paths": len(sims)})
    n = len(years)
    if n == 0:
        return {"n": 0, "reading": "not evaluated: no held-out seasons with complete data", "rows": []}
    ci = binomtest(hits, n).proportion_ci(confidence_level=0.95, method="exact")
    if ci.high < NOMINAL:
        reading = "under-covers: observed values fall outside the range more often than 20 % of the time"
    elif ci.low > NOMINAL:
        reading = "over-covers: ranges are wider than needed"
    else:
        reading = f"consistent with 80 %, but n = {n} is small"
    return {
        "n": n,
        "hits": hits,
        "empirical_coverage": round(hits / n, 3),
        "ci95": (round(float(ci.low), 3), round(float(ci.high), 3)),
        "mean_interval_width": round(float(np.mean(widths)), 2),
        "reading": reading,
        "rows": rows,
    }


def rolling_origin(
    observed: pd.Series,
    ensemble_fn: EnsembleFn,
    target_years: Iterable[int],
    *,
    pool_start: int,
    unlock_test: bool = False,
) -> dict[str, object]:
    """For each target year t, build the ensemble from pool_start..t-1 only, then score coverage."""
    targets = sorted(target_years)
    touched = [y for y in targets if y in TEST_YEARS]
    if touched and not unlock_test:
        raise TestPeriodLockedError(f"held-out test years {touched} are locked (validation plan section 1)")
    ensembles = {t: ensemble_fn(list(range(pool_start, t)), t) for t in targets}
    obs = {int(y): float(v) for y, v in observed.items() if int(y) in targets}
    return coverage_summary(obs, ensembles)
