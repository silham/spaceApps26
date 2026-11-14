"""Required water-balance tests (AGENTS.md section 7): units, mass balance, bounds, carry-over, modes. Owner: M4."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays

from ftm.contracts.models import SimulationMode
from ftm.engine.et0 import MJ_M2_DAY_TO_MM_DAY, hargreaves_et0_mm_day, ra_mj_m2_day
from ftm.engine.forcing import ForcingGapError
from ftm.engine.kc import adjusted_p
from ftm.engine.water_balance import (
    BucketInputs,
    SoilState,
    end_state,
    ks_fao56,
    runoff_mm,
    simulate_bucket,
    state_at_fraction,
)

TOL = 1e-9
AWC, DEPTH = 150.0, 1.0


def _inputs(
    rain: np.ndarray,
    et0: np.ndarray,
    kc: np.ndarray,
    *,
    zr: np.ndarray | None = None,
    crop_day: np.ndarray | None = None,
    season: np.ndarray | None = None,
) -> BucketInputs:
    n = len(rain)
    crop = np.ones(n, dtype=bool) if crop_day is None else crop_day
    return BucketInputs(
        rain_mm=rain,
        et0_mm=et0,
        kc=kc,
        p_table=np.where(crop, 0.5, np.nan),
        zr_m=np.full(n, 0.8) if zr is None else zr,
        cn=np.full(n, 80.0),
        crop_day=crop,
        irrigable=crop.copy(),
        season_id=np.zeros(n, dtype=int) if season is None else season,
    )


def _run(
    inputs: BucketInputs,
    *,
    mode: SimulationMode,
    state: SoilState | None = None,
    allocation_mm_per_season: float | None = None,
) -> pd.DataFrame:
    start = state or state_at_fraction(0.5, awc_mm_per_m=AWC, profile_depth_m=DEPTH, depth_m=float(inputs.zr_m[0]))
    return simulate_bucket(
        inputs,
        awc_mm_per_m=AWC,
        profile_depth_m=DEPTH,
        initial_state=start,
        mode=mode,
        allocation_mm_per_season=allocation_mm_per_season,
    )


@st.composite
def bucket_case(draw: st.DrawFn) -> tuple[BucketInputs, SoilState]:
    """Random weather, Kc and a crop/fallow pattern so the active depth changes during the run."""
    n = draw(st.integers(10, 120))
    rain = draw(arrays(np.float64, n, elements=st.floats(0, 150, allow_nan=False)))
    et0 = draw(arrays(np.float64, n, elements=st.floats(0, 12, allow_nan=False)))
    kc = draw(arrays(np.float64, n, elements=st.floats(0.05, 1.3, allow_nan=False)))
    crop = draw(arrays(np.bool_, n))
    root = draw(st.floats(0.2, DEPTH))
    zr = np.where(crop, root, 0.15)
    frac = draw(st.floats(0, 1))
    state = state_at_fraction(frac, awc_mm_per_m=AWC, profile_depth_m=DEPTH, depth_m=float(zr[0]))
    return _inputs(rain, et0, kc, zr=zr, crop_day=crop), state


@settings(max_examples=80, deadline=None)
@given(case=bucket_case(), mode=st.sampled_from(list(SimulationMode)), alloc=st.floats(0, 400))
def test_mass_balance_closes(case: tuple[BucketInputs, SoilState], mode: SimulationMode, alloc: float) -> None:
    inputs, state = case
    t = _run(inputs, state=state, mode=mode, allocation_mm_per_season=alloc)
    lhs = t["storage_end_mm"] - t["storage_start_mm"]
    rhs = t["infiltration_mm"] + t["irrigation_mm"] - t["aet_mm"] - t["drainage_mm"]
    assert np.allclose(lhs, rhs, atol=1e-9)
    assert np.allclose(t["rain_mm"], t["runoff_mm"] + t["infiltration_mm"])
    total = t["storage_end_mm"].iloc[-1] - (state.active_mm + state.subsoil_mm)
    assert total == pytest.approx(rhs.sum(), abs=1e-6)


@settings(max_examples=80, deadline=None)
@given(case=bucket_case(), mode=st.sampled_from(list(SimulationMode)))
def test_storages_stay_within_physical_bounds(case: tuple[BucketInputs, SoilState], mode: SimulationMode) -> None:
    inputs, state = case
    t = _run(inputs, state=state, mode=mode, allocation_mm_per_season=50.0)
    assert (t["active_storage_mm"] >= -TOL).all() and (t["subsoil_storage_mm"] >= -TOL).all()
    assert (t["active_storage_mm"] <= t["active_taw_mm"] + TOL).all()
    assert (t["subsoil_storage_mm"] <= AWC * (DEPTH - t["active_depth_m"]) + TOL).all()
    assert (t["storage_end_mm"] <= AWC * DEPTH + TOL).all()
    assert ((t["ks"] >= 0) & (t["ks"] <= 1)).all()
    assert (t["aet_mm"] <= t["etc_mm"] + TOL).all()
    cols = ["runoff_mm", "irrigation_mm", "aet_mm", "percolation_mm", "drainage_mm"]
    assert (t[cols] >= -TOL).all().all()


def test_depth_change_redistributes_without_creating_water() -> None:
    n = 6
    zr = np.array([1.0, 1.0, 0.15, 0.15, 0.6, 1.0])
    crop = np.array([True, True, False, False, True, True])
    zeros = np.zeros(n)
    start = state_at_fraction(0.7, awc_mm_per_m=AWC, profile_depth_m=DEPTH, depth_m=1.0)
    t = _run(_inputs(zeros, zeros, zeros, zr=zr, crop_day=crop), state=start, mode=SimulationMode.IRRIGATION_NEEDED)
    assert np.allclose(t["storage_end_mm"], 0.7 * AWC * DEPTH)
    # Uniform profile stays uniform: active store holds 70% of its capacity at every depth.
    assert np.allclose(t["active_storage_mm"], 0.7 * t["active_taw_mm"])


def test_fallow_days_have_no_water_stress_and_no_irrigation() -> None:
    n = 60
    crop = np.zeros(n, dtype=bool)
    inputs = _inputs(np.zeros(n), np.full(n, 6.0), np.full(n, 0.5), zr=np.full(n, 0.15), crop_day=crop)
    inputs = BucketInputs(**{**inputs.__dict__, "irrigable": np.ones(n, dtype=bool)})
    t = _run(inputs, mode=SimulationMode.IRRIGATION_NEEDED)
    assert (t["ks"] == 1.0).all() and t["irrigation_mm"].sum() == 0
    # Bare soil only dries the evaporation layer; subsoil water is kept for the next crop.
    assert t["aet_mm"].sum() <= 0.5 * AWC * 0.15 + TOL


def test_runoff_matches_tr55_table_2_1() -> None:
    # TR-55 Table 2-1: CN 80 -> 0.08 in of runoff from 1.0 in of rain and 2.04 in from 4.0 in.
    inch = 25.4
    assert runoff_mm(1.0 * inch, 80)[()] / inch == pytest.approx(0.08, abs=0.005)
    assert runoff_mm(4.0 * inch, 80)[()] / inch == pytest.approx(2.04, abs=0.005)
    assert runoff_mm(0.0, 80)[()] == 0.0
    assert runoff_mm(100.0, 90)[()] > runoff_mm(100.0, 70)[()]


def test_ks_and_p_adjustment_follow_fao56() -> None:
    assert ks_fao56(40.0, 100.0, 0.5) == 1.0  # Dr <= RAW
    assert ks_fao56(75.0, 100.0, 0.5) == pytest.approx(0.5)  # eq. 84
    assert ks_fao56(100.0, 100.0, 0.5) == 0.0
    # Table 22 footnote 2: p = p_table + 0.04 (5 - ETc), limited to 0.1-0.8.
    assert adjusted_p(0.55, 7.0) == pytest.approx(0.47)
    assert adjusted_p(0.55, 1.0) == pytest.approx(0.71)
    assert adjusted_p(0.75, 0.0) == 0.8 and adjusted_p(0.2, 15.0) == 0.1


def test_hargreaves_ra_unit_conversion() -> None:
    # FAO-56 Example 8: 20 deg S on 3 September (day 246) -> Ra = 32.2 MJ m-2 day-1.
    assert ra_mj_m2_day(-20.0, 246) == pytest.approx(32.2, abs=0.1)
    assert pytest.approx(1 / 2.45, abs=1e-3) == MJ_M2_DAY_TO_MM_DAY  # FAO-56 eq. 20
    tmax, tmin, ra = np.array([30.0]), np.array([15.0]), np.array([32.2])
    expected = 0.0023 * (22.5 + 17.8) * np.sqrt(15.0) * 0.408 * 32.2
    assert hargreaves_et0_mm_day(tmax, tmin, ra)[0] == pytest.approx(expected)
    # Forgetting the conversion would inflate ET0 ~2.45x; guard against that.
    assert hargreaves_et0_mm_day(tmax, tmin, ra)[0] < 0.0023 * 40.3 * np.sqrt(15.0) * 32.2 / 2
    assert np.isnan(hargreaves_et0_mm_day(np.array([10.0]), np.array([12.0]), ra)[0])  # Tmin > Tmax


def test_storage_carries_over_between_seasons() -> None:
    rng = np.random.default_rng(1)
    n, split = 120, 60
    rain, et0, kc = rng.gamma(0.5, 6, n), rng.uniform(2, 7, n), rng.uniform(0.3, 1.2, n)
    crop = np.r_[np.ones(50, dtype=bool), np.zeros(20, dtype=bool), np.ones(50, dtype=bool)]
    zr = np.where(crop, 0.9, 0.15)
    season = np.r_[np.zeros(split, dtype=int), np.ones(n - split, dtype=int)]
    fixed = SimulationMode.FIXED_ALLOCATION
    whole = _run(_inputs(rain, et0, kc, zr=zr, crop_day=crop, season=season), mode=fixed, allocation_mm_per_season=40.0)
    start = whole["storage_start_mm"].iloc[1:].to_numpy()
    assert np.allclose(start, whole["storage_end_mm"].iloc[:-1].to_numpy())

    def part(a: int, b: int) -> BucketInputs:
        return _inputs(rain[a:b], et0[a:b], kc[a:b], zr=zr[a:b], crop_day=crop[a:b], season=season[a:b])

    first = _run(part(0, split), mode=fixed, allocation_mm_per_season=40.0)
    second = _run(part(split, n), state=end_state(first), mode=fixed, allocation_mm_per_season=40.0)
    assert np.allclose(whole["storage_end_mm"].iloc[split:].to_numpy(), second["storage_end_mm"].to_numpy())


@settings(max_examples=80, deadline=None)
@given(case=bucket_case(), alloc=st.floats(0, 200), split=st.integers(1, 9))
def test_fixed_allocation_never_exceeds_allocation(
    case: tuple[BucketInputs, SoilState], alloc: float, split: int
) -> None:
    inputs, state = case
    season = np.where(np.arange(len(inputs.rain_mm)) < split, 0, 1)
    inputs = BucketInputs(**{**inputs.__dict__, "season_id": season})
    t = _run(inputs, state=state, mode=SimulationMode.FIXED_ALLOCATION, allocation_mm_per_season=alloc)
    for sid in (0, 1):
        assert t["irrigation_mm"][season == sid].sum() <= alloc + 1e-6


def test_exhausted_allocation_means_stress_not_water() -> None:
    n = 90
    inputs = _inputs(np.zeros(n), np.full(n, 6.0), np.full(n, 1.1))
    full = state_at_fraction(1.0, awc_mm_per_m=AWC, profile_depth_m=DEPTH, depth_m=0.8)
    t = _run(inputs, state=full, mode=SimulationMode.FIXED_ALLOCATION, allocation_mm_per_season=0.0)
    assert t["irrigation_mm"].sum() == 0
    assert (t["irrigation_shortfall_mm"] > 0).any() and (t["ks"] < 1).any()
    needed = _run(inputs, state=full, mode=SimulationMode.IRRIGATION_NEEDED)
    assert needed["irrigation_mm"].sum() > 0 and (needed["irrigation_shortfall_mm"] == 0).all()


def test_nan_rain_is_never_zero() -> None:
    rain = np.full(10, 2.0)
    rain[4] = np.nan
    with pytest.raises(ForcingGapError):
        _run(_inputs(rain, np.full(10, 4.0), np.ones(10)), mode=SimulationMode.IRRIGATION_NEEDED)


def test_invalid_inputs_are_rejected() -> None:
    n = 10
    ok = _inputs(np.ones(n), np.full(n, 4.0), np.ones(n))
    mode = SimulationMode.IRRIGATION_NEEDED
    bad_cases = {
        "same length": {"et0_mm": np.ones(n - 1)},
        "zr_m": {"zr_m": np.r_[np.full(n - 1, 0.8), 1.5]},  # deeper than the soil data
        "curve numbers": {"cn": np.full(n, 0.0)},
        "depletion fraction": {"p_table": np.full(n, np.nan)},  # crop days need p
        ">= 0": {"rain_mm": np.full(n, -1.0)},
    }
    for msg, change in bad_cases.items():
        with pytest.raises(ValueError, match=msg):
            _run(BucketInputs(**{**ok.__dict__, **change}), mode=mode)
    with pytest.raises(ValueError, match="allocation"):
        _run(ok, mode=SimulationMode.FIXED_ALLOCATION, allocation_mm_per_season=None)
    with pytest.raises(ValueError, match="capacity"):
        _run(ok, state=SoilState(500.0, 0.0, 0.8), mode=mode)
