"""Suggested rotations (D16): constraints filter, priorities order, irrigation only where the floor needs it."""

from __future__ import annotations

from datetime import date

import pytest

from ftm.engine.ensemble import SoilRunConfig, usable_blocks
from ftm.engine.et0 import compute_et0
from ftm.engine.params import load_crops
from ftm.engine.recommend import Constraints, _dominates, in_table11_months, order_key, suggest

from ._synthetic import make_forcing, soil

CROPS = load_crops()
H = (date(2026, 1, 1), date(2027, 12, 31))


@pytest.fixture(scope="module")
def setup():  # type: ignore[no-untyped-def]
    f = make_forcing("1981-01-01", "2025-12-31", seed=11)
    e = compute_et0(f, latitude_deg=38.0, elevation_m=800.0)
    return f, e, usable_blocks(f, e, "01-01")


def _c(**kw) -> Constraints:  # type: ignore[no-untyped-def]
    base = dict(
        priorities=("cover", "irrigation", "soil_health"),
        irrigation_allowed=True,
        max_irrigation_mm=None,
        exclude=frozenset(),
        require=None,
        max_seasons=2,
        min_relative_yield_pct=60.0,
    )
    return Constraints(**{**base, **kw})  # type: ignore[arg-type]


def _run(setup, c):  # type: ignore[no-untyped-def]
    f, e, pool = setup
    cfg = SoilRunConfig(soil=soil(), initial_fraction=0.6, warmup=False)
    return suggest(f, e, pool, CROPS, cfg, c, site_id="x", horizon=H, first_block_weights=None, seed=1)


def test_suggestions_respect_constraints_and_are_ordered(setup) -> None:  # type: ignore[no-untyped-def]
    s = _run(setup, _c(exclude=frozenset({"cotton"})))
    assert s.ranked and s.considered > len(s.ranked)
    for r in s.ranked:
        assert all(x.crop_id != "cotton" for x in r.strategy.seasons)
        assert all(x.crop_id != "groundnut" for x in r.strategy.seasons)  # no cited base temperature: never suggested
        assert all(H[0] <= x.plant_date and x.end_date <= H[1] for x in r.strategy.seasons)
        assert all(in_table11_months(CROPS[x.crop_id], x.plant_date, False) for x in r.strategy.seasons if x.crop_id)
    keys = [order_key(r.objectives, ("cover", "irrigation", "soil_health")) for r in s.ranked]
    assert keys == sorted(keys)
    sequences = [tuple(x.crop_id for x in r.strategy.seasons) for r in s.ranked]
    assert len(sequences) == len(set(sequences))  # options differ in their crops


def test_no_irrigation_means_rainfed_only_and_floor_holds(setup) -> None:  # type: ignore[no-untyped-def]
    s = _run(setup, _c(irrigation_allowed=False, min_relative_yield_pct=30.0))
    for r in s.ranked:
        assert all(x.irrigation_rule is None for x in r.strategy.seasons)
        assert r.objectives["irrigation"] == 0.0


def test_dominance() -> None:
    a = {"cover": 100.0, "irrigation": 50.0, "soil_health": 2.0}
    assert _dominates(a, {"cover": 120.0, "irrigation": 50.0, "soil_health": 2.0})
    assert not _dominates(a, a)
    assert not _dominates(a, {"cover": 90.0, "irrigation": 80.0, "soil_health": 2.0})


def test_southern_hemisphere_shifts_planting_months() -> None:
    maize = CROPS["maize-grain"]  # FAO-56 Table 11 row: April planting
    assert in_table11_months(maize, date(2026, 4, 15), False) and not in_table11_months(
        maize, date(2026, 10, 15), False
    )
    assert in_table11_months(maize, date(2026, 10, 15), True)
