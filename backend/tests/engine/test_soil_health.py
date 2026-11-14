"""Soil-health rules of thumb (D16): conditional statements from cited traits, never numbers. Owner: M4."""

from __future__ import annotations

from datetime import date

from ftm.contracts.models import SeasonPlan, Strategy
from ftm.engine.params import load_crops
from ftm.engine.soil_health import rules_met, soil_rules

CROPS = load_crops()


def _rot(*crop_ids: str) -> Strategy:
    seasons = [
        SeasonPlan(crop_id=c, plant_date=date(2027 + i, 5, 1), end_date=date(2027 + i, 9, 30))
        for i, c in enumerate(crop_ids)
    ]
    return Strategy(id="s", site_id="x", name="r", seasons=seasons)


def _by_id(rules):  # type: ignore[no-untyped-def]
    return {r.rule_id: r for r in rules}


def test_every_catalog_crop_with_traits_has_a_citation() -> None:
    for c in CROPS.values():
        assert c.profile.family and c.profile.legume is not None and c.profile.traits_reference


def test_legume_then_cereal_alternates_families() -> None:
    r = _by_id(soil_rules(_rot("soybean", "maize-grain"), CROPS))
    assert r["family_change"].status == "met"
    assert r["legume_before_nonlegume"].status == "met"
    assert "not quantified" in r["legume_before_nonlegume"].explanation
    assert r["family_diversity"].status == "met"
    assert rules_met(list(r.values())) == 3


def test_cereal_after_cereal_is_flagged() -> None:
    r = _by_id(soil_rules(_rot("maize-grain", "sorghum-grain"), CROPS))
    assert r["family_change"].status == "not_met" and "Poaceae" in r["family_change"].explanation
    assert r["legume_before_nonlegume"].status == "not_met"
    assert r["family_diversity"].status == "not_met"


def test_crop_on_the_field_now_counts_as_the_one_before() -> None:
    before = SeasonPlan(crop_id="soybean", plant_date=date(2026, 5, 1), end_date=date(2026, 9, 30))
    r = _by_id(soil_rules(_rot("maize-grain"), CROPS, before=before))
    assert r["legume_before_nonlegume"].status == "met"


def test_single_crop_has_no_sequence() -> None:
    r = _by_id(soil_rules(_rot("maize-grain"), CROPS))
    assert r["family_change"].status == "unknown"
