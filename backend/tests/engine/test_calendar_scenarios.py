"""FAO-56 temperature planting rules, local season lengths and the ks-field-2 scenarios. Owner: M4."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ftm.engine.calendar import planting_date
from ftm.engine.forcing import TMAX, TMIN, flag_col
from ftm.engine.params import CATALOG_DIR, CatalogError, load_crop, load_local_crops, split_season
from ftm.engine.rotation import check_feasibility
from ftm.engine.scenarios import SCENARIO_HORIZON, build_ks_field_2

from ._synthetic import make_forcing, soil


def _ramp_forcing(years: range) -> pd.DataFrame:
    """Mean temperature = 0 degC on 1 Jan rising 0.1 degC/day to 1 Jul, then falling 0.1 degC/day."""
    f = make_forcing(f"{years.start}-01-01", f"{years.stop - 1}-12-31")
    doy = f.index.day_of_year.to_numpy()
    tmean = np.where(doy <= 182, 0.1 * (doy - 1), 18.1 - 0.1 * (doy - 182))
    f[TMAX], f[TMIN] = tmean + 5.0, tmean - 5.0
    return f


def test_maize_and_wheat_rules_follow_fao56_footnote() -> None:
    f = _ramp_forcing(range(2001, 2004))
    maize = planting_date(f, "maize_spring_13c", [2001, 2002, 2003])
    # Daily mean 0.1 (doy - 1); the 10-day trailing mean is 0.1 (doy - 5.5) >= 13 first on doy 136 = 16 May.
    assert maize.month_day == "05-16" and maize.years_without_date == []
    assert "FAO-56 Table 11 footnote 2" in maize.reference

    fall = make_forcing("2001-01-01", "2001-12-31")
    t = (fall.index - pd.Timestamp("2001-09-01")).days.to_numpy()
    tmean = np.where(t < 0, 25.0, 25.0 - 0.5 * t)  # cools 0.5 degC/day from 1 Sep
    fall[TMAX], fall[TMIN] = tmean + 5.0, tmean - 5.0
    # 10-day trailing mean = 25 - 0.5 (t - 4.5) <= 17 first at t = 21 -> 22 Sep.
    assert planting_date(fall, "winter_wheat_fall_17c", [2001]).month_day == "09-22"


def test_wheat_rule_falls_back_to_december_1() -> None:
    f = make_forcing("2001-01-01", "2001-12-31")
    f[TMAX], f[TMIN] = 30.0, 20.0  # never cools to 17 degC
    assert planting_date(f, "winter_wheat_fall_17c", [2001]).month_day == "12-01"


def test_temperature_gap_gives_no_date_rather_than_a_filled_one() -> None:
    f = _ramp_forcing(range(2001, 2003))
    day = pd.Timestamp("2001-05-10")
    f.loc[day, TMAX] = np.nan
    f.loc[day, flag_col(TMAX)] = "missing"
    p = planting_date(f, "maize_spring_13c", [2001, 2002])
    assert p.years_without_date == [2001] and list(p.per_year) == [2002]
    with pytest.raises(ValueError, match="planting date unknown"):
        planting_date(f, "maize_spring_13c", [2001])


def test_split_season_keeps_the_sum_exact() -> None:
    assert split_season(335, [160, 75, 75, 25]) == [160, 75, 75, 25]
    parts = split_season(270, [160, 75, 75, 25])
    assert sum(parts) == 270 and parts == [129, 60, 60, 21]
    with pytest.raises(CatalogError):
        split_season(0, [1, 1, 1, 1])


def test_kansas_wheat_season_is_cited_and_needs_a_reference(tmp_path: Path) -> None:
    entry = load_local_crops()["winter-wheat-ks"]
    lengths = {k: v.value for k, v in entry.profile.stage_lengths_days.items()}
    assert lengths == {"ini": 128, "dev": 60, "mid": 60, "late": 20}  # NASS median 268 d, 160:75:75:25
    assert "USDA NASS" in str(entry.profile.stage_lengths_days["ini"].reference)
    raw = json.loads((CATALOG_DIR / "winter_wheat_ks.json").read_text(encoding="utf-8"))
    raw["engine_extras"]["local_calendar"]["season_days"] = 270
    raw["engine_extras"]["local_calendar"]["reference"] = None
    path = tmp_path / "w.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(CatalogError, match="no reference"):
        load_crop(path)
    raw["engine_extras"]["local_calendar"]["reference"] = "TEST ONLY: synthetic season length"
    path.write_text(json.dumps(raw), encoding="utf-8")
    filled = load_crop(path)
    lengths = [filled.profile.stage_lengths_days[s].value for s in ("ini", "dev", "mid", "late")]
    assert lengths == [129, 60, 60, 21]
    assert "TEST ONLY" in str(filled.profile.stage_lengths_days["ini"].reference)


def test_ks_field_2_scenarios_are_paired_and_feasible() -> None:
    f = make_forcing("1984-01-01", "2019-12-31", seed=5)
    scen = build_ks_field_2(f, list(range(1984, 2020)))
    ids = [s.id for s in scen.strategies]
    assert ids == ["ks2-current-corn-wheat", "ks2-alt-a-double-crop", "ks2-alt-b-sorghum-wheat"]
    assert scen.strategies[0].is_baseline and all(s.site_id == "ks-field-2" for s in scen.strategies)
    for s in scen.strategies:  # Kansas wheat (NASS season) fits all three inside the 2027-2028 horizon
        feas = check_feasibility(s, scen.crops, horizon=SCENARIO_HORIZON, soil=soil())
        assert feas.feasible, (s.id, feas.reasons)
    alt_a = scen.strategies[1].seasons
    assert alt_a[2].crop_id == "sorghum-grain" and alt_a[2].plant_date > alt_a[1].end_date
    idaho = build_ks_field_2(f, list(range(1984, 2020)), wheat="fao56-idaho")
    feas = {s.id: check_feasibility(s, idaho.crops, horizon=SCENARIO_HORIZON, soil=soil()) for s in idaho.strategies}
    assert feas["ks2-current-corn-wheat"].feasible and feas["ks2-alt-b-sorghum-wheat"].feasible
    assert "outside the comparison horizon" in " ".join(feas["ks2-alt-a-double-crop"].reasons)
    base = idaho.strategies[0]
    assert base.seasons[0].crop_id == "maize-grain" and base.seasons[0].irrigation_rule is not None
    assert base.seasons[0].plant_date.year == 2027 and base.seasons[1].plant_date > base.seasons[0].end_date
    assert idaho.strategies[2].seasons[0].plant_date == date(2027, 6, 1)
    assert idaho.strategies[2].seasons[0].irrigation_rule is None  # rainfed sorghum
