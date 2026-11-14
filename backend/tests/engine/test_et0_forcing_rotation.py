"""ET0, forcing-contract, feasibility and block-exclusion tests. Owner: M4."""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from ftm.contracts.models import QualityFlag
from ftm.engine.ensemble import horizon_blocks, replay_windows, usable_blocks
from ftm.engine.et0 import HARGREAVES, PM_RH, PM_TDEW, compute_et0
from ftm.engine.forcing import (
    RAIN,
    RH,
    RS,
    TDEW,
    TMAX,
    TMIN,
    WIND,
    ForcingContractError,
    assert_forcing_contract,
    flag_col,
)
from ftm.engine.kc import kc_curve
from ftm.engine.rotation import check_feasibility

from ._synthetic import IRR, crop, make_forcing, soil, strategy


def _one_day(**values: float) -> pd.DataFrame:
    """FAO-56 Example 18 (Brussels, 6 July): ET0 = 3.9 mm/day."""
    base = {
        TMAX: 21.5,
        TMIN: 12.3,
        RS: 22.07,
        WIND: 2.078,
        RAIN: 0.0,
        RH: 73.5,
        # Tdew giving ea = 1.409 kPa (the example's value) through FAO-56 eq. 14.
        TDEW: 237.3 * math.log(1.409 / 0.6108) / (17.27 - math.log(1.409 / 0.6108)),
    }
    base.update(values)
    df = pd.DataFrame({k: [v] for k, v in base.items()}, index=pd.DatetimeIndex(["2026-07-06"], name="date"))
    for v in base:
        df[flag_col(v)] = QualityFlag.OK.value if not np.isnan(base[v]) else QualityFlag.MISSING.value
    df["source_id"], df["processing_run_id"] = "test-src", "test-run"
    return df


def _et0(df: pd.DataFrame) -> tuple[float, str | None]:
    assert_forcing_contract(df)
    out = compute_et0(df, latitude_deg=50.80, elevation_m=100.0)
    return float(out["et0_mm_day"].iloc[0]), out["et0_method"].iloc[0]


def test_penman_monteith_matches_fao56_example_18() -> None:
    et0, method = _et0(_one_day())
    assert method == PM_TDEW
    assert et0 == pytest.approx(3.9, abs=0.1)


def test_rh_fallback_then_hargreaves_never_silent_tmin_minus_2() -> None:
    _, m = _et0(_one_day(**{TDEW: np.nan}))
    assert m == PM_RH
    _, m = _et0(_one_day(**{TDEW: np.nan, RH: np.nan}))
    assert m == HARGREAVES  # pyfao56 would silently use Tdew = Tmin - 2; we record a fallback instead
    _, m = _et0(_one_day(**{WIND: np.nan}))
    assert m == HARGREAVES  # pyfao56 would silently use 2 m/s
    et0, m = _et0(_one_day(**{TMAX: np.nan}))
    assert np.isnan(et0) and m is None


def test_flagged_temperatures_are_not_used() -> None:
    df = _one_day(**{TMAX: 10.0, TMIN: 12.0})
    df[flag_col(TMAX)] = df[flag_col(TMIN)] = QualityFlag.FLAGGED.value
    et0, m = _et0(df)
    assert np.isnan(et0) and m is None


def test_elevation_is_required() -> None:
    with pytest.raises(ValueError, match="elevation"):
        compute_et0(_one_day(), latitude_deg=50.8, elevation_m=float("nan"))


def test_forcing_contract_rejects_bad_shapes() -> None:
    f = make_forcing("2000-01-01", "2000-03-31")
    assert assert_forcing_contract(f).source_id == "test-src"
    with pytest.raises(ForcingContractError, match="complete"):
        assert_forcing_contract(f.drop(f.index[10]))
    two = f.copy()
    two.loc[two.index[5], "source_id"] = "other-rain-source"
    with pytest.raises(ForcingContractError, match="exactly one"):
        assert_forcing_contract(two)
    lying = f.copy()
    lying.loc[lying.index[3], RAIN] = np.nan  # NaN but still flagged OK
    with pytest.raises(ForcingContractError, match="usable flag"):
        assert_forcing_contract(lying)


def test_nan_rain_excludes_the_whole_season_block_with_reason() -> None:
    f = make_forcing("2000-01-01", "2005-12-31")
    day = pd.Timestamp("2002-06-15")
    f.loc[day, RAIN] = np.nan
    f.loc[day, flag_col(RAIN)] = QualityFlag.MISSING.value
    pool = usable_blocks(f, compute_et0(f, latitude_deg=38.0, elevation_m=800.0), "01-01")
    assert 2002 not in pool.usable_years
    assert pool.usable_years == [2000, 2001, 2003, 2004, 2005]
    assert pool.excluded[0]["year"] == 2002 and "missing rain is not zero rain" in str(pool.excluded[0]["reason"])
    windows = replay_windows(pool, horizon_years=2, first=2000, last=2005)
    disabled = [w for w in windows if not w["enabled"]]
    assert {w["years"] for w in disabled} == {(2001, 2002), (2002, 2003)}
    assert all("2002" in str(w["reason"]) for w in disabled)


def test_horizon_blocks() -> None:
    assert horizon_blocks((date(2027, 4, 1), date(2029, 3, 31))) == 2
    assert horizon_blocks((date(2027, 1, 1), date(2028, 12, 31))) == 2


def test_kc_curve_follows_fao56_eq66() -> None:
    kc, stage = kc_curve((20, 30, 40, 20), 0.4, 1.1, 0.6, 120)
    assert kc[0] == pytest.approx(0.4) and kc[19] == pytest.approx(0.4)
    assert kc[35] == pytest.approx(0.4 + 15 / 30 * (1.1 - 0.4))
    assert kc[60] == pytest.approx(1.1)
    assert kc[100] == pytest.approx(1.1 + 10 / 20 * (0.6 - 1.1))
    assert kc[115] == pytest.approx(0.6)  # held at Kc_end until harvest
    assert (stage == 0).sum() == 20 and (stage == 4).sum() == 10


def test_et0_reports_vapour_pressure_for_rhmin() -> None:
    df = _one_day()
    out = compute_et0(df, latitude_deg=50.80, elevation_m=100.0)
    assert out["ea_kpa"].iloc[0] == pytest.approx(1.409, abs=1e-3)


def test_infeasible_strategies_get_readable_reasons() -> None:
    horizon = (date(2027, 1, 1), date(2027, 12, 31))
    crops = {"a": crop("a", window=("04-01", "05-15")), "nop": crop("nop", p=None), "noh": crop("noh", height=None)}
    s = strategy(
        "s",
        [
            ("a", date(2027, 6, 1), date(2027, 7, 1), IRR),
            ("nop", date(2027, 6, 20), date(2027, 11, 30), None),
            ("ghost", date(2027, 12, 1), date(2027, 12, 30), None),
        ],
    )
    feas = check_feasibility(s, crops, horizon=horizon, soil=soil())
    text = " ".join(feas.reasons)
    assert not feas.feasible
    assert "needs 110 days to mature but the season has 30" in text
    assert "outside Synthetic a's window" in text
    assert "overlaps the previous season" in text
    assert "missing cited parameters (depletion_fraction_p)" in text
    assert "'ghost' is not in the catalog" in text

    ok = strategy("ok", [("a", date(2027, 4, 10), date(2027, 9, 1), IRR)])
    assert check_feasibility(ok, crops, horizon=horizon, soil=soil()).feasible
    assert check_feasibility(ok, crops, horizon=horizon, soil=soil(), available_crop_ids={"nop"}).reasons
    blocked = check_feasibility(ok, crops, horizon=horizon, soil=soil(awc=None))
    assert "available water capacity is missing" in " ".join(blocked.reasons)
    assert not check_feasibility(ok, crops, horizon=horizon, soil=None).feasible

    noh = strategy("noh", [("noh", date(2027, 4, 10), date(2027, 9, 1), None)])
    assert "max_height_m" in " ".join(check_feasibility(noh, crops, horizon=horizon, soil=soil()).reasons)


def test_unsupported_management_is_infeasible_not_silently_replaced() -> None:
    horizon = (date(2027, 1, 1), date(2027, 12, 31))
    crops = {"a": crop("a")}
    drip = strategy("drip", [("a", date(2027, 4, 10), date(2027, 9, 1), "drip 20 mm weekly")])
    assert "is not supported" in " ".join(check_feasibility(drip, crops, horizon=horizon, soil=soil()).reasons)
    wet_fallow = strategy("wf", [(None, date(2027, 4, 10), date(2027, 9, 1), IRR)])
    assert "irrigating a fallow season" in " ".join(
        check_feasibility(wet_fallow, crops, horizon=horizon, soil=soil()).reasons
    )
    s = strategy("res", [("a", date(2027, 4, 10), date(2027, 9, 1), None)])
    res = s.model_copy(update={"seasons": [s.seasons[0].model_copy(update={"residue_management": "retain"})]})
    assert "not modelled" in " ".join(check_feasibility(res, crops, horizon=horizon, soil=soil()).reasons)
