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
from ftm.engine.sensitivity import (
    AwcBounds,
    SensitivityCase,
    apply_case,
    full_grid,
    one_at_a_time,
    ranking,
    run_sensitivity,
    shift_planting,
)

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


def test_case_grids_and_planting_shift() -> None:
    assert len(one_at_a_time(include_allocation=True)) == 9
    assert len(one_at_a_time(include_allocation=False)) == 7
    grid = full_grid(include_allocation=True)
    assert len(grid) == 81 and grid[0].name == "baseline" and len(set(grid)) == 81
    s = strategy(
        "s", [("crop-a", date(2027, 4, 1), date(2027, 8, 31), IRR), (None, date(2027, 9, 1), date(2027, 9, 30), None)]
    )
    moved = shift_planting(s, 14)
    assert moved.seasons[0].plant_date == date(2027, 4, 15) and moved.seasons[0].end_date == date(2027, 9, 14)
    assert moved.seasons[1] == s.seasons[1]  # fallow stays


def test_apply_case_changes_only_the_named_input() -> None:
    base = _request()
    bounds = AwcBounds(120.0, 150.0, 180.0, "test bounds")
    req = apply_case(base, SensitivityCase(allocation="high", initial_water="low"), bounds)
    assert req.allocation_mm_per_season == pytest.approx(120.0) and req.initial_fraction == 0.25
    assert req.soil is base.soil and req.forcing is base.forcing and req.seed == base.seed
    assert (
        apply_case(base, SensitivityCase(awc="low"), bounds).soil.profile.available_water_capacity_mm_per_m.value == 120
    )
    needed = dataclasses.replace(base, mode=SimulationMode.IRRIGATION_NEEDED, allocation_mm_per_season=None)
    with pytest.raises(ValueError, match="fixed_allocation"):
        apply_case(needed, SensitivityCase(allocation="low"), bounds)


def test_sensitivity_uses_identical_weather_paths_and_reports_rankings() -> None:
    base = _request(n_paths=5)
    cases = one_at_a_time(include_allocation=True)
    report = run_sensitivity(base, cases, AwcBounds(120.0, 150.0, 180.0, "test bounds"))
    assert len(report.cases) == 9
    assert all(c.path_years == report.cases[0].path_years for c in report.cases)
    for m in ("irrigation_mm", "water_stress_days", "cover_days", "possible_low_cover_days"):
        assert m in report.summary and "ranking unchanged in" in report.summary[m]
        r = report.cases[0].rankings[m]
        assert r is not None and sorted(sid for g in r for sid in g) == ["alt", "base"]
    with pytest.raises(ValueError, match="baseline"):
        run_sensitivity(base, cases[1:], AwcBounds(120.0, 150.0, 180.0, "x"))


def test_ranking_groups_ties_and_skips_infeasible() -> None:
    bad = strategy("bad", [("crop-a", date(2027, 4, 1), date(2027, 5, 1), IRR)])
    out = run_engine(_request(strategies=[*_request().strategies, bad], n_paths=3))
    r = ranking(out, "crop_diversity_count")
    assert r is not None and all("bad" not in g for g in r)
