"""FAO-33 water-limited relative yield. Synthetic traces only."""

from datetime import date

import numpy as np
import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from ftm.contracts.models import SeasonPlan, Strategy
from ftm.engine.params import load_crops
from ftm.engine.yield_response import parse_yield_metric, relative_yield, yield_metrics


def test_worked_example_fao33_eq1() -> None:
    # Ky 1.25 (maize), ETa/ETm = 0.8: 1 - 1.25 * 0.2 = 0.75
    assert relative_yield(1.25, 400.0, 500.0) == pytest.approx(0.75)


def test_no_stress_or_no_sensitivity_gives_full_yield() -> None:
    assert relative_yield(1.25, 500.0, 500.0) == 1.0
    assert relative_yield(0.0, 100.0, 500.0) == 1.0
    assert relative_yield(1.0, 0.0, 0.0) == 1.0  # no water demand, no deficit


@given(ky=st.floats(0, 2), aet=st.floats(0, 800), etc=st.floats(0, 800))
def test_relative_yield_stays_between_zero_and_one(ky: float, aet: float, etc: float) -> None:
    assert 0.0 <= relative_yield(ky, min(aet, etc), etc) <= 1.0


def _strategy(crop: str, usual: float | None) -> Strategy:
    seasons = [
        SeasonPlan(crop_id=crop, plant_date=date(2027, 5, 1), end_date=date(2027, 8, 29), usual_yield_t_ha=usual),
        SeasonPlan(crop_id=None, plant_date=date(2027, 9, 1), end_date=date(2027, 9, 30)),
    ]
    return Strategy(id="s", site_id="x", name="TEST", seasons=seasons)


def _trace(aet_ratio: float) -> pd.DataFrame:
    n = 10
    return pd.DataFrame({"season_id": [0] * 6 + [-1] * 4, "etc_mm": [5.0] * n, "aet_mm": [5.0 * aet_ratio] * n})


def test_yield_metrics_per_season_with_optional_farmer_yield() -> None:
    crops = load_crops()
    out = yield_metrics(_trace(0.8), _strategy("maize-grain", 9.0), crops)
    assert out["relative_yield_pct__s0"] == pytest.approx(75.0)
    assert out["yield_t_ha__s0"] == pytest.approx(0.75 * 9.0)
    assert set(yield_metrics(_trace(0.8), _strategy("maize-grain", None), crops)) == {"relative_yield_pct__s0"}


def test_a_crop_without_ky_gets_no_yield_claim() -> None:
    crops = load_crops()
    crop = crops["maize-grain"]
    no_ky = type(crop)(
        profile=crop.profile.model_copy(update={"ky_season": None}),
        max_height_m=crop.max_height_m,
        tr55_cover=crop.tr55_cover,
    )
    assert yield_metrics(_trace(0.8), _strategy("maize-grain", 9.0), {"maize-grain": no_ky}) == {}


def test_metric_names_round_trip() -> None:
    assert parse_yield_metric("relative_yield_pct__s2") == ("relative_yield_pct", 2)
    assert parse_yield_metric("yield_t_ha__s0") == ("yield_t_ha", 0)
    assert parse_yield_metric("irrigation_mm") is None
    assert not np.isnan(relative_yield(1.0, 1.0, 2.0))
