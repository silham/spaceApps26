import pytest

from ftm.contracts.models import ParamValue, SoilProfile
from ftm.data.soil_texture import usda_texture_class
from ftm.engine.params import CatalogError, soil_spec_from_profile


@pytest.mark.parametrize(
    ("sand", "silt", "clay", "expected"),
    [
        (92, 5, 3, "sand"),
        (82, 12, 6, "loamy sand"),
        (65, 25, 10, "sandy loam"),
        (40, 40, 20, "loam"),
        (20, 65, 15, "silt loam"),
        (8, 87, 5, "silt"),
        (60, 15, 25, "sandy clay loam"),
        (33, 34, 33, "clay loam"),
        (10, 55, 35, "silty clay loam"),
        (52, 6, 42, "sandy clay"),
        (6, 47, 47, "silty clay"),
        (20, 20, 60, "clay"),
    ],
)
def test_usda_texture_triangle_reference_points(sand: float, silt: float, clay: float, expected: str) -> None:
    assert usda_texture_class(sand, silt, clay) == expected


def test_percentages_that_do_not_sum_to_100_are_refused() -> None:
    assert usda_texture_class(50, 50, 50) is None
    assert usda_texture_class(-5, 60, 45) is None


def _profile(texture: str | None) -> SoilProfile:
    awc = ParamValue(value=150.0, unit="mm/m", reference="TEST")
    zr = ParamValue(value=None, unit="m", reference=None)
    return SoilProfile(
        id="s", site_id="x", available_water_capacity_mm_per_m=awc, root_zone_depth_m=zr, texture=texture, source_ids=[]
    )


def test_soilgrids_style_texture_resolves_to_the_catalog_class() -> None:
    spec = soil_spec_from_profile(
        _profile("silty clay loam (clay 33%, sand 10%, silt 57%; 0-30 cm, SoilGrids mean)"), data_depth_m=1.0
    )
    assert spec.hsg == "D"
    assert spec.annex7_class == "medium"
    assert soil_spec_from_profile(_profile("Sand"), data_depth_m=1.0).annex7_class == "coarse"


def test_tr55_groups_for_the_finer_textures() -> None:
    # TR-55 Appendix A: C = sandy clay loam; D = clay loam, silty clay loam, sandy clay, silty clay, clay.
    for texture, hsg in (("sandy clay loam", "C"), ("clay loam", "D"), ("sandy clay", "D"), ("clay", "D")):
        assert soil_spec_from_profile(_profile(texture), data_depth_m=1.0).hsg == hsg


def test_a_texture_tr55_does_not_list_blocks_the_soil() -> None:
    with pytest.raises(CatalogError, match="cannot be simulated"):
        soil_spec_from_profile(_profile("silt (clay 5%, sand 8%, silt 87%)"), data_depth_m=1.0)
