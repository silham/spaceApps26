"""Soil adapters and root-zone water arithmetic. Uses small recorded-shape payloads; no network."""

import json
from pathlib import Path

import pytest

from ftm.contracts.models import ValueKind
from ftm.data.adapters import soil_soilgrids, soil_ssurgo
from ftm.data.raw_cache import save_raw
from ftm.data.soil import Layer, water_mm_per_m

# --------------------------------------------------------------------------- arithmetic


def test_water_mm_per_m_depth_weighted() -> None:
    # 0.18 x 20 cm + 0.16 x 59 cm + 0.03 x 21 cm = 13.67 cm over 1 m -> 136.7 mm/m
    layers = [Layer(0, 20, 0.18), Layer(20, 79, 0.16), Layer(79, 152, 0.03)]
    assert water_mm_per_m(layers, 1.0) == pytest.approx(136.7)


def test_water_mm_per_m_unknown_layer_is_not_zero() -> None:
    assert water_mm_per_m([Layer(0, 50, 0.1), Layer(50, 100, None)], 1.0) is None


def test_water_mm_per_m_short_profile_is_not_zero_filled() -> None:
    assert water_mm_per_m([Layer(0, 60, 0.1)], 1.0) is None  # data stops at 60 cm


def test_water_mm_per_m_partial_depth() -> None:
    # Only the top 0.5 m counts: 0.2 x 50 cm = 10 cm over 0.5 m -> 200 mm/m
    assert water_mm_per_m([Layer(0, 100, 0.2)], 0.5) == pytest.approx(200.0)


# --------------------------------------------------------------------------- SSURGO

SDA_COLS = [
    "mukey", "muname", "areasymbol", "saverest", "cokey", "compname", "comppct_r", "majcompflag",
    "hzname", "hzdept_r", "hzdepb_r", "awc_l", "awc_r", "awc_h", "sandtotal_r", "silttotal_r",
    "claytotal_r", "texdesc",
]  # fmt: skip


def _sda_row(cokey: str, pct: str, top: str, bottom: str, awc: tuple[str, str, str], tex: str) -> list[str]:
    return ["1152313", "Las clay loam", "KS055", "2025-09-01", cokey, f"Comp{cokey}", pct, "Yes",
            "H", top, bottom, *awc, "30", "40", "30", tex]  # fmt: skip


def _sda_payload() -> bytes:
    rows = [
        _sda_row("1", "80", "0", "20", ("0.17", "0.18", "0.19"), "Clay loam"),
        _sda_row("1", "80", "20", "79", ("0.12", "0.16", "0.19"), "Clay loam"),
        _sda_row("1", "80", "79", "152", ("0.02", "0.03", "0.04"), "Sand"),
        _sda_row("2", "20", "0", "200", ("0.10", "0.10", "0.10"), "Loam"),
    ]
    return json.dumps({"Table": [SDA_COLS, *rows]}).encode()


def test_ssurgo_component_weighted_awc_and_bounds(tmp_path: Path) -> None:
    snap = save_raw("ssurgo", "x.json", _sda_payload(), tmp_path / "raw")
    res = soil_ssurgo.build("site", snap)
    awc = res.profile.available_water_capacity_mm_per_m
    # comp1 = 136.7 mm/m (80%), comp2 = 100 mm/m (20%) -> 129.36
    assert awc.value == pytest.approx(129.4, abs=0.05)
    assert awc.unit == "mm/m" and awc.reference
    # low: comp1 0.17*20+0.12*59+0.02*21 = 10.9 cm -> 109; comp2 100 -> 107.2
    assert res.awc_low_mm_per_m == pytest.approx(107.2, abs=0.05)
    assert res.awc_high_mm_per_m is not None and res.awc_high_mm_per_m > awc.value
    assert res.profile.texture == "Clay loam"  # dominant component's surface horizon
    assert res.profile.root_zone_depth_m.value is None  # crop parameter, never guessed from soil
    assert res.source.kind == ValueKind.LITERATURE and res.source.raw_sha256 == snap.sha256


def test_ssurgo_outside_us_raises(tmp_path: Path) -> None:
    snap = save_raw("ssurgo", "empty.json", b"{}", tmp_path / "raw")
    with pytest.raises(soil_ssurgo.SsurgoError):
        soil_ssurgo.build("site", snap)


# --------------------------------------------------------------------------- SoilGrids


def _sg_layer(name: str, by_depth: dict[str, tuple[int, int, int]]) -> dict[str, object]:
    return {
        "name": name,
        "unit_measure": {"d_factor": 10, "target_units": "%"},
        "depths": [
            {"label": d, "values": {"mean": m, "Q0.05": lo, "Q0.5": m, "Q0.95": hi}}
            for d, (lo, m, hi) in by_depth.items()
        ],
    }


def _sg_payload(drop_deep_wp: bool = False) -> bytes:
    depths = soil_soilgrids.DEPTHS
    fc = {d: (130, 310, 480) for d in depths}  # 31.0 % vol
    wp = {d: (30, 170, 350) for d in depths}  # 17.0 % vol
    if drop_deep_wp:
        wp.pop("60-100cm")
    layers = [_sg_layer("wv0033", fc), _sg_layer("wv1500", wp)]
    layers += [
        _sg_layer(p, {d: (10, v, 900) for d in depths}) for p, v in (("clay", 270), ("sand", 490), ("silt", 240))
    ]
    return json.dumps({"type": "Feature", "properties": {"layers": layers}}).encode()


def test_soilgrids_awc_from_fc_minus_wp(tmp_path: Path) -> None:
    snap = save_raw("soilgrids", "p.json", _sg_payload(), tmp_path / "raw")
    res = soil_soilgrids.build("site", snap)
    awc = res.profile.available_water_capacity_mm_per_m
    assert awc.value == pytest.approx(140.0)  # (31 - 17) % vol = 0.14 cm3/cm3 over 1 m
    assert res.awc_low_mm_per_m is None and res.awc_high_mm_per_m is None  # no valid interval from source
    assert "clay 27%" in (res.profile.texture or "")
    assert res.source.license == "CC BY 4.0" and res.source.doi


def test_soilgrids_missing_depth_blocks_value(tmp_path: Path) -> None:
    snap = save_raw("soilgrids", "q.json", _sg_payload(drop_deep_wp=True), tmp_path / "raw")
    res = soil_soilgrids.build("site", snap)
    assert res.profile.available_water_capacity_mm_per_m.value is None
    assert res.profile.available_water_capacity_mm_per_m.reference is None


def test_soilgrids_bad_payload_raises() -> None:
    with pytest.raises(soil_soilgrids.SoilGridsError):
        soil_soilgrids.parse(b'{"type": "Feature"}')
