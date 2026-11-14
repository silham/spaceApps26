"""Forecast-weighted draws, real-calendar horizon and today's soil water (D16). Owner: M4."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from ftm.engine.ensemble import SoilRunConfig, bootstrap_paths, usable_blocks
from ftm.engine.et0 import compute_et0
from ftm.engine.forcing import RAIN, TMAX, TMIN
from ftm.engine.forecast_weights import (
    Window,
    member_anomalies,
    power_window_values,
    uniform,
    windows,
    year_weights,
)
from ftm.engine.outlook import FieldNow, observed_end, observed_initial_fraction, outlook, prediction_horizon

from ._synthetic import crop, make_forcing, soil

CROPS = {"crop-a": crop("crop-a")}


def _fe() -> tuple[pd.DataFrame, pd.DataFrame]:
    f = make_forcing("1981-01-01", "2006-06-14", seed=5)
    return f, compute_et0(f, latitude_deg=38.0, elevation_m=800.0)


def test_unweighted_draws_unchanged_and_weights_steer_first_block() -> None:
    f, e = _fe()
    pool = usable_blocks(f, e, "06-15")
    plain = bootstrap_paths(pool, n_paths=50, horizon_years=2, seed=9)
    assert plain == bootstrap_paths(pool, n_paths=50, horizon_years=2, seed=9, first_block_weights=None)
    only = pool.pool_years[3]
    weighted = bootstrap_paths(pool, n_paths=50, horizon_years=2, seed=9, first_block_weights={only: 1.0})
    assert {p[0] for p in weighted} == {only}
    assert [p[1] for p in weighted] == [p[1] for p in plain]  # later blocks keep the unweighted draws
    with pytest.raises(ValueError, match="no pool year"):
        bootstrap_paths(pool, n_paths=5, horizon_years=2, seed=1, first_block_weights={1900: 1.0})


def test_horizon_starts_after_last_usable_day() -> None:
    f, _ = _fe()
    f = f.copy()
    f.loc["2006-06-10":, RAIN] = np.nan  # POWER's trailing missing days are missing, never zero
    end = observed_end(f)
    assert end == date(2006, 6, 9)
    assert prediction_horizon(end) == (date(2006, 6, 10), date(2008, 6, 9))


def test_initial_state_bounded_and_crop_draws_down() -> None:
    f, e = _fe()
    cfg = SoilRunConfig(soil=soil(), initial_fraction=0.5)
    bare = observed_initial_fraction(f, e, cfg, CROPS, site_id="s", field=None)
    cropped = observed_initial_fraction(f, e, cfg, CROPS, site_id="s", field=FieldNow("crop-a", date(2006, 3, 1), None))
    assert 0.0 <= cropped.fraction <= bare.fraction <= 1.0
    assert "bare fallow" in bare.assumption and "farmer input" in cropped.assumption
    assert bare.as_of == date(2006, 6, 14)


def test_outlook_bands_ordered() -> None:
    f, e = _fe()
    start, end = prediction_horizon(observed_end(f))
    pool = usable_blocks(f, e, start.strftime("%m-%d"))
    cfg = SoilRunConfig(soil=soil(), initial_fraction=0.4, warmup=False)
    b = outlook(f, e, pool, cfg, CROPS, site_id="s", horizon=(start, end), field=None,
                first_block_weights=None, seed=1, days=60, n_paths=20)  # fmt: skip
    assert b.dates[0] == start and len(b.dates) == 60
    for band in (b.rain_mm, b.tmax_c, b.storage_mm):
        lo, mid, hi = (np.array(band[p], dtype=float) for p in (10, 50, 90))
        assert (lo <= mid + 1e-9).all() and (mid <= hi + 1e-9).all()
    assert b.storage_mm[50][0] <= 0.4 * 150.0 + 1e-6


def _members(n: int, start: str, days: int, rain: float, temp: float) -> dict[str, pd.DataFrame]:
    idx = pd.date_range(start, periods=days, freq="D")
    rng = np.random.default_rng(0)

    # column names as the API delivers them: they differ between variables
    def cols(v: str) -> list[str]:
        return [f"{v}_member{k:02d}" for k in range(n)]

    return {
        "precipitation_sum": pd.DataFrame(rain + rng.random((days, n)), index=idx, columns=cols("precipitation_sum")),
        "temperature_2m_max": pd.DataFrame(
            temp + 5 + rng.random((days, n)), index=idx, columns=cols("temperature_2m_max")
        ),
        "temperature_2m_min": pd.DataFrame(
            temp - 5 + rng.random((days, n)), index=idx, columns=cols("temperature_2m_min")
        ),
    }


def test_member_anomaly_removes_model_mean_bias() -> None:
    daily = _members(11, "2026-11-01", 120, rain=9.0, temp=30.0)  # biased model: very wet and hot
    monthly = pd.DataFrame(
        {"precipitation_mm": [-20.0, -20.0, -20.0], "temperature_k": [-1.0, -1.0, -1.0]},
        index=pd.to_datetime(["2026-11-01", "2026-12-01", "2027-01-01"]),
    )
    (w,) = windows(monthly.index, date(2026, 11, 12), daily["precipitation_sum"].index)
    assert w.label == "Nov–Jan"
    a = member_anomalies(daily, monthly, w)
    # the model's normal is its ensemble mean minus the hindcast anomaly, whatever the model's own level
    ens = sum(daily["precipitation_sum"].loc[f"{m:%Y-%m}"].to_numpy().sum(axis=0) for m in w.months).mean()
    assert a["rain"].mean() == pytest.approx(ens / (ens + 60.0))  # 60 mm below the model's normal
    assert a["temperature"].mean() == pytest.approx(-1.0)


def test_dry_forecast_weights_dry_years_up() -> None:
    idx = pd.date_range("1981-01-01", "2016-12-31", freq="D")
    rng = np.random.default_rng(1)
    year_rain = {y: rng.uniform(0.5, 3.0) for y in range(1981, 2017)}
    rain = pd.Series([year_rain[d.year] for d in idx], index=idx)
    tmax = pd.Series(20.0 + rng.normal(0, 0.1, len(idx)), index=idx)
    tmin = tmax - 10
    w = Window("Jan–Mar", tuple(pd.Timestamp(2027, m, 1) for m in (1, 2, 3)))
    vals = power_window_values(rain, tmax, tmin, w.month_numbers)
    assert set(vals.index) == set(range(1981, 2017))
    dry = np.full(30, (vals["rain"] / vals["rain"].mean()).min())  # every member below normal (share of normal)
    t_anom = vals["temperature"] - vals["temperature"].mean()
    neutral = np.quantile(t_anom, np.linspace(0.02, 0.98, 30))  # temperature odds ~1/3 each
    yw = year_weights(list(vals.index), {w: vals}, {w: {"rain": dry, "temperature": neutral}})
    weights = yw.as_dict()
    driest, wettest = vals["rain"].idxmin(), vals["rain"].idxmax()
    assert weights[driest] > 1 / len(vals) > weights[wettest]
    assert sum(weights.values()) == pytest.approx(1.0)
    assert yw.odds[0].probabilities == (1.0, 0.0, 0.0)
    assert 10.0 - 1e-6 <= yw.effective_sample_size < len(vals)  # never rests on a handful of years


def test_concentrated_weights_are_blended_to_ten_effective_years() -> None:
    from ftm.engine.forecast_weights import _limit_concentration

    w = np.array([0.97] + [0.03 / 35] * 35)
    out, blend = _limit_concentration(w, 10.0)
    assert 0 < blend < 1 and out.sum() == pytest.approx(1.0)
    assert 1 / np.sum(out**2) == pytest.approx(10.0, rel=1e-3)
    assert out[0] == out.max()  # the forecast's preferred year stays the most likely


def test_missing_rain_year_is_left_out_not_zero() -> None:
    idx = pd.date_range("1990-01-01", "1991-12-31", freq="D")
    rain = pd.Series(1.0, index=idx)
    rain.loc["1990-02-10"] = np.nan
    t = pd.Series(10.0, index=idx)
    vals = power_window_values(rain, t, t, (1, 2, 3))
    assert 1990 not in vals.index and 1991 in vals.index


def test_uniform_weights() -> None:
    u = uniform([2000, 2001, 2002, 2003])
    assert u.weights == [0.25] * 4 and u.effective_sample_size == 4


def test_variable_names() -> None:
    assert (RAIN, TMAX, TMIN) == ("PRECTOTCORR", "T2M_MAX", "T2M_MIN")
