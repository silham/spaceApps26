"""Crop-coefficient methods checked against FAO-56 worked examples; catalog citation rules. Owner: M4."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from ftm.engine.kc import _kc_ini_eq73, bare_soil_kc, climate_adjusted_kc, rhmin_pct, wetting_events
from ftm.engine.params import CATALOG_DIR, CROP_FILES, CatalogError, curve_number, demo_soil, load_crop, load_crops


def test_kc_mid_climate_adjustment_matches_fao56_example_27() -> None:
    # FAO-56 Example 27: maize, Kc mid (Table 12) 1.20, h = 2 m.
    assert climate_adjusted_kc(1.20, 1.3, 75.0, 2.0) == pytest.approx(1.07, abs=0.005)  # Taipei
    assert climate_adjusted_kc(1.20, 4.6, 44.0, 2.0) == pytest.approx(1.30, abs=0.005)  # Mocha
    # Inputs are held to the eq. 62 validity ranges (u2 1-6 m/s, RHmin 20-80 %).
    assert climate_adjusted_kc(1.2, 9.0, 5.0, 2.0) == climate_adjusted_kc(1.2, 6.0, 20.0, 2.0)


def test_bare_soil_kc_matches_fao56_annex7_example_7_1() -> None:
    # Annex 7 Example 7-1: coarse soil, 20 mm twice a week (tw = 3.5 d), ET0 = 5 mm/day.
    # Fig. 30a set: the page prints 0.75 and its printed equation reproduces it.
    assert bare_soil_kc(5.0, 3.5, 40.0, "coarse") == pytest.approx(0.75, abs=0.005)
    # Fig. 29 set: the page prints 0.57, but its own printed inputs in its printed eq. 7-3,
    # (10 - 7.3 exp[-(3.03)(5.75)(1 + 2.7/7.3)/10]) / 17.5, evaluate to 0.533 (arithmetic slip in the
    # source, checked 2026-11-14; see docs/model.md). We test the equation, not the misprint.
    kc29 = bare_soil_kc(5.0, 3.5, 10.0, "coarse")
    assert kc29 == pytest.approx(0.533, abs=0.005)
    # Eq. 59 interpolation at I = 20 mm (page prints 0.63 from its 0.57).
    assert bare_soil_kc(5.0, 3.5, 20.0, "coarse") == pytest.approx(kc29 + (10 / 30) * (0.75 - kc29), abs=0.005)
    assert _kc_ini_eq73(10.0, 2.7, 5.0, 0.2) == 1.15  # tw <= t1: energy-limited, Kc ini = 1.15
    assert bare_soil_kc(5.0, 30.0, 0.0, "medium") < bare_soil_kc(5.0, 3.0, 0.0, "medium")  # drier = lower


def test_wetting_events_follow_annex7_counting_rule() -> None:
    et0 = np.full(8, 5.0)
    infil = np.array([0.5, 12.0, 8.0, 0.0, 0.0, 20.0, 0.0, 0.9])  # 0.5 and 0.9 < 0.2 ET0 are ignored
    n, depth = wetting_events(infil, et0)
    assert n == 2  # days 1-2 adjoin and count as one event
    assert depth == pytest.approx((20.0 + 20.0) / 2)


def test_rhmin_from_ea_and_tmax() -> None:
    es = 0.6108 * np.exp(17.27 * 30.0 / (30.0 + 237.3))
    assert rhmin_pct(np.array([0.5 * es]), np.array([30.0]))[0] == pytest.approx(50.0)


def test_catalog_crops_are_fully_cited() -> None:
    crops = load_crops()
    assert set(crops) == {"maize-grain", "sorghum-grain", "winter-wheat"}
    for entry in crops.values():
        p = entry.profile
        for param in (p.kc_ini, p.kc_mid, p.kc_end, p.max_root_depth_m, p.depletion_fraction_p, entry.max_height_m):
            assert param.value is not None and param.reference and "FAO-56" in param.reference
        assert all(v.reference for v in p.stage_lengths_days.values())


def _write_crop(tmp_path: Path, mutate: dict[str, object]) -> Path:
    raw = json.loads((CATALOG_DIR / CROP_FILES[0]).read_text(encoding="utf-8"))
    for dotted, value in mutate.items():
        target = raw
        *parents, leaf = dotted.split(".")
        for key in parents:
            target = target[key]
        target[leaf] = value
    path = tmp_path / "crop.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def test_catalog_rejects_uncited_or_mislabelled_values(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="no reference"):
        load_crop(_write_crop(tmp_path, {"profile.kc_mid.reference": None}))
    with pytest.raises(CatalogError, match="unit"):
        load_crop(_write_crop(tmp_path, {"profile.max_root_depth_m.unit": "cm"}))
    with pytest.raises(CatalogError, match="cover class"):
        load_crop(_write_crop(tmp_path, {"engine_extras.tr55_cover": "made_up"}))
    # A null value with no reference is allowed: the claim is blocked later by feasibility.
    entry = load_crop(_write_crop(tmp_path, {"profile.kc_mid.value": None, "profile.kc_mid.reference": None}))
    assert entry.profile.kc_mid.value is None


def test_curve_numbers_and_demo_soil_come_from_cited_tables() -> None:
    assert curve_number("row_crops_straight_row_good", "B") == 78  # TR-55 Table 2-2b
    assert curve_number("small_grain_straight_row_good", "B") == 75
    assert curve_number("fallow_bare_soil", "B") == 86
    with pytest.raises(CatalogError):
        curve_number("made_up", "B")
    lo, mid, hi = (demo_soil("s", bound=b) for b in ("low", "mid", "high"))  # type: ignore[arg-type]
    assert lo.profile.available_water_capacity_mm_per_m.value == pytest.approx(130.0)  # Table 19 silt loam
    assert mid.profile.available_water_capacity_mm_per_m.value == pytest.approx(160.0)
    assert hi.profile.available_water_capacity_mm_per_m.value == pytest.approx(190.0)
    assert mid.profile.is_demo and mid.profile.root_zone_depth_m.value is None
