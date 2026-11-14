"""M3 forcing adapter, sample pool / held-out years, SSURGO soil and sensitivity. Owner: M4."""

from __future__ import annotations

import dataclasses
from datetime import date

import numpy as np
import pandas as pd
import pytest

from ftm.contracts.models import ParamValue, SimulationMode, SoilProfile
from ftm.data.forcing import to_wide
from ftm.engine.ensemble import EnsembleConfig, bootstrap_paths, ensemble_weather_paths, usable_blocks
from ftm.engine.et0 import compute_et0
from ftm.engine.forcing import EXPECTED_UNITS, ForcingContractError, assert_forcing_contract, from_store_frame
from ftm.engine.params import CatalogError, soil_spec_from_profile, with_awc
from ftm.engine.runner import EngineInputError, run_engine
from ftm.engine.sensitivity import apply_inputs, make_run_fn, medians, shift_planting
from ftm.validation import coverage as m5_coverage
from ftm.validation import sensitivity as m5_sensitivity

from ._synthetic import IRR, make_forcing, strategy
from .test_ensemble_runner import HORIZON, _request

ENGINE_VARS = ("PRECTOTCORR", "T2M_MAX", "T2M_MIN", "T2MDEW", "RH2M", "WS2M", "ALLSKY_SFC_SW_DWN")


def _store_frame(units: dict[str, str] | None = None, sources: list[str] | None = None) -> pd.DataFrame:
    """A frame built by M3's own pivot (``ftm.data.forcing.to_wide``), as get_daily_forcing returns it."""
    f = make_forcing("2000-01-01", "2000-03-31")
    rows = []
    for v in ENGINE_VARS:
        for d, val, flag in zip(f.index.date, f[v], f[f"{v}__flag"], strict=True):
            rows.append({"date": d, "variable": v, "unit": (units or EXPECTED_UNITS)[v], "processed_value": val,
                         "quality_flag": flag})  # fmt: skip
    long = pd.DataFrame(rows)
    long.loc[(long["variable"] == "PRECTOTCORR") & (long["date"] == date(2000, 2, 1)), "processed_value"] = np.nan
    long.loc[(long["variable"] == "PRECTOTCORR") & (long["date"] == date(2000, 2, 1)), "quality_flag"] = "missing"
    wide = to_wide(long, date(2000, 1, 1), date(2000, 3, 31))
    wide.attrs.update(site_id="s", source_ids=sources or ["power-x"], processing_run_id="proc_1")
    return wide


def test_store_frame_is_adapted_without_changing_values() -> None:
    frame = _store_frame()
    out = from_store_frame(frame)
    info = assert_forcing_contract(out)
    assert (info.source_id, info.processing_run_id, info.n_days) == ("power-x", "proc_1", 91)
    assert isinstance(out.index, pd.DatetimeIndex)
    assert np.isnan(out.loc["2000-02-01", "PRECTOTCORR"]) and out.loc["2000-02-01", "PRECTOTCORR__flag"] == "missing"
    np.testing.assert_array_equal(out["T2M_MAX"].to_numpy(), frame["T2M_MAX"].to_numpy())


def test_store_frame_rejects_wrong_units_or_several_sources() -> None:
    with pytest.raises(ForcingContractError, match="not converted"):
        from_store_frame(_store_frame(units={**EXPECTED_UNITS, "ALLSKY_SFC_SW_DWN": "kW-hr/m^2/day"}))
    with pytest.raises(ForcingContractError, match="exactly one weather source"):
        from_store_frame(_store_frame(sources=["power-x", "imerg-y"]))


def test_bootstrap_draws_only_from_the_sample_pool_and_held_out_years_replay_only() -> None:
    f = make_forcing("1990-01-01", "2005-12-31", seed=3)
    e = compute_et0(f, latitude_deg=38.0, elevation_m=800.0)
    pool = usable_blocks(f, e, "01-01", (1992, 2001))
    assert pool.pool_years == list(range(1992, 2002)) and pool.outside_pool_years == [
        1990,
        1991,
        2002,
        2003,
        2004,
        2005,
    ]
    drawn = {y for path in bootstrap_paths(pool, n_paths=200, horizon_years=2, seed=1) for y in path}
    assert drawn <= set(range(1992, 2002))
    held_out = run_engine(_request(pool_range=(1992, 2001), replay_years=(2003, 2004)))
    assert held_out.run.n_paths == 1
    assert any("outside the sample pool" in lim for lim in held_out.limitations)
    run = run_engine(_request(pool_range=(1992, 2001), n_paths=5))
    assert run.run.sample_period == (date(1992, 1, 1), date(2001, 12, 31))
    assert run.run.input_versions["sample_pool"] == "1992-2001"
    assert run.run.input_versions["held_out_or_outside_pool_years"] == "1990,1991,2002,2003,2004,2005"
    assert "block_definition" in run.run.input_versions
    with pytest.raises(EngineInputError, match="sample pool"):
        run_engine(_request(pool_range=(2030, 2040)))


def test_coverage_helper_returns_the_same_paths_as_a_run() -> None:
    f = make_forcing("1990-01-01", "2005-12-31", seed=3)
    e = compute_et0(f, latitude_deg=38.0, elevation_m=800.0)
    cfg = EnsembleConfig(HORIZON, (1992, 2001), n_paths=6, seed=11)
    _, paths = ensemble_weather_paths(f, e, cfg)
    out = run_engine(_request(pool_range=(1992, 2001), n_paths=6, seed=11))
    assert [y for y, _ in paths] == [o.years for o in out.outcomes]
    assert all(np.isfinite(w["rain_mm"]).all() for _, w in paths)


def _profile(texture: str | None, awc: float | None = 214.4) -> SoilProfile:
    return SoilProfile(
        id="soil_ks",
        site_id="test-site",
        available_water_capacity_mm_per_m=ParamValue(value=awc, unit="mm/m", reference="SSURGO test"),
        root_zone_depth_m=ParamValue(value=None, unit="m", reference=None),
        texture=texture,
        source_ids=["ssurgo-x"],
    )


def test_soil_spec_from_ssurgo_profile() -> None:
    spec = soil_spec_from_profile(_profile("Silt loam"), data_depth_m=1.0)
    assert (spec.hsg, spec.annex7_class) == ("B", "medium")
    assert any("inferred from texture" in n for n in spec.notes)
    assert soil_spec_from_profile(_profile("Silt loam"), data_depth_m=1.0, hsg="C").notes == ()
    with pytest.raises(CatalogError, match="not in the FAO-56"):
        soil_spec_from_profile(_profile("Clay"), data_depth_m=1.0)
    low = with_awc(spec, 194.3, "SSURGO awc_l")
    assert low.profile.available_water_capacity_mm_per_m.value == 194.3 and "194.3" in low.notes[-1]


def test_planting_shift_moves_crop_seasons_only() -> None:
    s = strategy(
        "s", [("crop-a", date(2027, 4, 1), date(2027, 8, 31), IRR), (None, date(2027, 9, 1), date(2027, 9, 30), None)]
    )
    moved = shift_planting(s, 14)
    assert moved.seasons[0].plant_date == date(2027, 4, 15) and moved.seasons[0].end_date == date(2027, 9, 14)
    assert moved.seasons[1] == s.seasons[1]  # fallow stays
    assert shift_planting(s, 0) is s


def test_apply_inputs_maps_m5_factor_names() -> None:
    base = _request()
    req = apply_inputs(
        base,
        {
            "awc_mm_per_m": 120.0,
            "initial_soil_water_frac_taw": 0.25,
            "planting_shift_days": -14,
            "irrigation_allocation_mm": 80.0,
        },
    )
    assert req.soil.profile.available_water_capacity_mm_per_m.value == 120.0
    assert req.initial_fraction == 0.25 and req.allocation_mm_per_season == 80.0
    assert req.strategies[0].seasons[0].plant_date == date(2027, 3, 18)
    assert req.forcing is base.forcing and req.seed == base.seed and req.n_paths == base.n_paths
    assert apply_inputs(base, {"awc_mm_per_m": 150.0}).soil is base.soil  # mid value: unchanged soil
    with pytest.raises(ValueError, match="unknown sensitivity input"):
        apply_inputs(base, {"yield_t_ha": 3})
    needed = dataclasses.replace(base, mode=SimulationMode.IRRIGATION_NEEDED, allocation_mm_per_season=None)
    with pytest.raises(ValueError, match="fixed_allocation"):
        apply_inputs(needed, {"irrigation_allocation_mm": 80.0})


def test_m5_ranking_harness_runs_on_identical_weather_paths() -> None:
    base = _request(n_paths=5)
    seen: list[list[tuple[int, ...]]] = []
    run_fn = make_run_fn(base, on_output=lambda out: seen.append([o.years for o in out.outcomes]))
    factors = m5_sensitivity.default_factors(120.0, 150.0, 180.0, 100.0)
    scenarios = m5_sensitivity.one_at_a_time(factors)
    metrics = {"irrigation_mm": False, "water_stress_days": False, "cover_days": True}
    reports = m5_sensitivity.ranking_stability(run_fn, scenarios, metrics)
    assert len(seen) == len(scenarios) == 9 and all(p == seen[0] for p in seen)
    for rep in reports.values():
        assert rep.total == 9 and sorted(rep.baseline_order) == ["alt", "base"]
        assert "ranking unchanged in" in rep.sentence


def test_infeasible_strategies_are_absent_from_medians() -> None:
    bad = strategy("bad", [("crop-a", date(2027, 4, 1), date(2027, 5, 1), IRR)])
    out = run_engine(_request(strategies=[*_request().strategies, bad], n_paths=3))
    m = medians(out)
    assert set(m) == {"base", "alt"} and "irrigation_mm" in m["base"]


def test_m5_coverage_harness_uses_the_engine_ensemble_without_leakage() -> None:
    from ftm.engine.ensemble import seasonal_ensemble_fn, seasonal_totals_by_year

    f = make_forcing("1990-01-01", "2012-12-31", seed=4)
    e = compute_et0(f, latitude_deg=38.0, elevation_m=800.0)
    window = m5_coverage.SeasonWindow((10, 1), (6, 30))  # crosses the new year, like winter wheat
    fn = seasonal_ensemble_fn(f, e, window, "rain_mm", n_paths=200, seed=7)
    from ftm.engine.ensemble import daily_weather

    totals = seasonal_totals_by_year(daily_weather(f, e), window, "rain_mm")
    assert np.isnan(totals[1990])  # season Oct 1989 - Jun 1990 is not fully in the record
    sims = fn(list(range(1991, 2005)), 2005)
    assert sims.shape == (200,) and set(np.round(sims, 6)) <= set(np.round(totals.loc[1991:2004].to_numpy(), 6))
    np.testing.assert_array_equal(sims, fn(list(range(1991, 2005)), 2005))  # seeded
    with pytest.raises(ValueError, match="no leakage"):
        fn(list(range(1991, 2006)), 2005)
    observed = totals.loc[2005:2010]
    res = m5_coverage.rolling_origin(observed, fn, range(2005, 2011), pool_start=1991)
    assert res["n"] == 6 and all(r["n_paths"] == 200 for r in res["rows"])  # type: ignore[index, union-attr]
