"""Coverage and sensitivity harnesses with synthetic engines (the real ensemble/engine come from M4)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from ftm.validation.coverage import SeasonWindow, coverage_summary, rolling_origin, seasonal_totals
from ftm.validation.phenology import TestPeriodLockedError
from ftm.validation.sensitivity import Factor, default_factors, full_factorial, one_at_a_time, ranking_stability


def test_season_window_crossing_new_year() -> None:
    w = SeasonWindow((10, 1), (6, 30))
    assert w.bounds(2019) == (date(2018, 10, 1), date(2019, 6, 30))


def test_seasonal_totals_missing_day_is_nan_not_partial_sum() -> None:
    idx = pd.date_range("2018-01-01", "2019-12-31", freq="D")
    daily = pd.DataFrame({"rain_mm": 1.0}, index=idx)
    daily.loc["2019-05-10", "rain_mm"] = np.nan
    tot = seasonal_totals(daily, SeasonWindow((4, 1), (9, 30)), ["rain_mm"])
    assert tot.loc[2018, "rain_mm"] == 183.0
    assert np.isnan(tot.loc[2019, "rain_mm"])


def test_coverage_counts_hits_and_reads_ci() -> None:
    rng = np.random.default_rng(0)
    years = range(2005, 2020)
    ens = {y: rng.normal(500, 100, 300) for y in years}
    inside = {y: 500.0 for y in years}  # always inside -> over-covers? n=15 all hits: CI low ~0.78 -> consistent
    s = coverage_summary(inside, ens)
    assert s["n"] == 15 and s["hits"] == 15 and s["empirical_coverage"] == 1.0
    assert s["ci95"][0] < 0.8 and "consistent" in s["reading"]
    outside = {y: 2000.0 for y in years}
    assert "under-covers" in coverage_summary(outside, ens)["reading"]


def test_rolling_origin_uses_only_past_years_and_locks_test() -> None:
    seen: list[tuple[list[int], int]] = []

    def ens(pool: list[int], target: int) -> np.ndarray:
        seen.append((pool, target))
        assert max(pool) < target  # no peeking at the target or later years
        return np.linspace(0, 1000, 101)

    obs = pd.Series({y: 500.0 for y in range(2005, 2020)})
    out = rolling_origin(obs, ens, range(2005, 2020), pool_start=1984)
    assert out["n"] == 15 and len(seen) == 15
    with pytest.raises(TestPeriodLockedError):
        rolling_origin(obs, ens, [2021], pool_start=1984)


def test_default_factors_use_provider_bounds_or_declared_assumption() -> None:
    with_bounds = default_factors(194.3, 214.4, 239.3, allocation_mm=300)
    assert with_bounds[0].low == 194.3 and "provider" in with_bounds[0].basis
    no_bounds = default_factors(None, 134.0, None, allocation_mm=None)
    assert no_bounds[0].low == pytest.approx(107.2) and "assumption" in no_bounds[0].basis
    assert [f.name for f in no_bounds] == ["awc_mm_per_m", "initial_soil_water_frac_taw", "planting_shift_days"]


def test_designs_sizes() -> None:
    fs = default_factors(194.3, 214.4, 239.3, allocation_mm=300)
    assert len(one_at_a_time(fs)) == 1 + 2 * 4
    assert len(full_factorial(fs)) == 81


def test_ranking_stability_reports_flips_and_driver() -> None:
    fs = [Factor("awc_mm_per_m", 100, 200, 300, "x"), Factor("planting_shift_days", -14, 0, 14, "x")]

    def engine(inp: dict) -> dict:
        # water-saving wins on stress days unless soil holds a lot of water
        ws = 10 if inp["awc_mm_per_m"] < 300 else 20
        return {
            "baseline": {"stress_days": 15},
            "water_saving": {"stress_days": ws},
            "soil_protecting": {"stress_days": 17},
        }

    rep = ranking_stability(engine, one_at_a_time(fs), {"stress_days": False})["stress_days"]
    assert rep.baseline_order == ["water_saving", "baseline", "soil_protecting"]
    assert rep.total == 5 and rep.unchanged == 4
    assert "awc_mm_per_m" in rep.sentence and "4 of 5" in rep.sentence
