"""Crop, soil and runoff parameter catalog loader. Owner: M4.

Reads the cited JSON files in ``engine/catalog/``. Every parameter with a value must carry a reference
and the expected unit; a value without a citation is rejected (DEVELOPMENT_GUIDE.md section 7). Null values
are allowed: the claim that needs them is blocked later by the feasibility check.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ftm.contracts.models import CropProfile, ParamValue, SoilProfile, Source, ValueKind

CATALOG_DIR = Path(__file__).parent / "catalog"
CROP_FILES = ("maize_grain.json", "sorghum_grain.json", "winter_wheat.json")
LOCAL_CROP_FILES = ("winter_wheat_ks.json",)  # site-local season lengths (D4), see local_calendar
EXPECTED_UNITS = {"kc_ini": "-", "kc_mid": "-", "kc_end": "-", "max_root_depth_m": "m", "depletion_fraction_p": "-"}

# Literature the engine actually uses (AGENTS.md rule 2). Kind LITERATURE keeps them distinct from data.
FAO56 = Source(
    id="lit-fao56-1998",
    provider="FAO",
    product="Crop evapotranspiration, FAO Irrigation and Drainage Paper 56",
    variables=["ET0 method", "Kc", "stage lengths", "root depth", "p", "soil water ranges", "bare-soil Kc"],
    units={},
    kind=ValueKind.LITERATURE,
    url="https://www.fao.org/4/x0490e/x0490e00.htm",
    attribution="Allen, R.G., Pereira, L.S., Raes, D., Smith, M. (1998). FAO, Rome.",
    limitations="Generic table values; local calibration is recommended by the source itself.",
)
TR55 = Source(
    id="lit-usda-tr55-1986",
    provider="USDA SCS (now NRCS)",
    product="Urban Hydrology for Small Watersheds, Technical Release 55, 2nd ed.",
    version="June 1986",
    variables=["runoff curve number", "runoff equation"],
    units={},
    kind=ValueKind.LITERATURE,
    url="https://ponce.sdsu.edu/tr55.pdf",
    attribution="USDA Soil Conservation Service (1986).",
    limitations="Average runoff condition; snowmelt and frozen ground not covered; less accurate below 0.5 in.",
)
LITERATURE_SOURCES = (FAO56, TR55)

Annex7Class = Literal["coarse", "medium"]
HSG = Literal["A", "B", "C", "D"]


class CatalogError(ValueError):
    """A catalog entry is malformed: a value without a citation, a wrong unit, an unknown cover class."""


@dataclass(frozen=True)
class CropEntry:
    profile: CropProfile
    max_height_m: ParamValue
    tr55_cover: str


@dataclass(frozen=True)
class SoilSpec:
    """Soil inputs the engine needs. AWC comes from ``SoilProfile``; the rest is declared with a source."""

    profile: SoilProfile
    data_depth_m: float  # depth over which AWC was integrated (M3 adapters: 1.0 m)
    hsg: HSG  # TR-55 hydrologic soil group, for curve numbers
    annex7_class: Annex7Class  # FAO-56 Annex 7 / Fig. 30 texture class, for bare-soil Kc
    notes: tuple[str, ...] = ()


def _check_param(name: str, p: ParamValue, unit: str) -> None:
    if p.unit != unit:
        raise CatalogError(f"{name}: unit {p.unit!r}, expected {unit!r}")
    if p.value is not None and not p.reference:
        raise CatalogError(f"{name}: value {p.value} has no reference; uncited values are not allowed")


def validate_crop(entry: CropEntry) -> None:
    prof = entry.profile
    for field, unit in EXPECTED_UNITS.items():
        _check_param(f"{prof.id}.{field}", getattr(prof, field), unit)
    for stage, p in prof.stage_lengths_days.items():
        _check_param(f"{prof.id}.stage_lengths_days.{stage}", p, "days")
    _check_param(f"{prof.id}.max_height_m", entry.max_height_m, "m")
    if entry.tr55_cover not in load_curve_numbers()["covers"]:
        raise CatalogError(f"{prof.id}: unknown TR-55 cover class {entry.tr55_cover!r}")


def split_season(season_days: int, proportions: list[int]) -> list[int]:
    """Split a local season length in fixed stage proportions; rounding goes to the last stage, sum exact."""
    if season_days <= 0 or len(proportions) != 4 or min(proportions) <= 0:
        raise CatalogError("season_days must be > 0 and proportions four positive numbers")
    total = sum(proportions)
    parts = [round(season_days * p / total) for p in proportions[:3]]
    return [*parts, season_days - sum(parts)]


def _apply_local_calendar(raw: dict[str, Any]) -> None:
    """Fill stage lengths from ``engine_extras.local_calendar`` when a cited season length is present."""
    cal = raw.get("engine_extras", {}).get("local_calendar")
    if not cal or cal.get("season_days") is None:
        return
    if not cal.get("reference"):
        raise CatalogError(f"{raw['profile']['id']}: local season length {cal['season_days']} has no reference")
    lengths = split_season(int(cal["season_days"]), list(cal["split_proportions"]))
    ref = f"Derived: {cal['reference']} season of {cal['season_days']} d, split as {cal['split_from']}"
    for stage, days in zip(("ini", "dev", "mid", "late"), lengths, strict=True):
        raw["profile"]["stage_lengths_days"][stage] = {
            "value": days,
            "unit": "days",
            "reference": ref,
            "region_relevance": "Site-local season length (D4)",
            "uncertainty": "Stage split assumes the FAO-56 row's proportions hold locally",
        }


def load_crop(path: Path) -> CropEntry:
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    _apply_local_calendar(raw)
    extras = raw.get("engine_extras", {})
    entry = CropEntry(
        profile=CropProfile.model_validate(raw["profile"]),
        max_height_m=ParamValue.model_validate(
            extras.get("max_height_m", {"value": None, "unit": "m", "reference": None})
        ),
        tr55_cover=str(extras.get("tr55_cover", "")),
    )
    validate_crop(entry)
    return entry


def load_crops(directory: Path = CATALOG_DIR, files: tuple[str, ...] = CROP_FILES) -> dict[str, CropEntry]:
    crops = [load_crop(directory / f) for f in files]
    return {c.profile.id: c for c in crops}


def load_local_crops(directory: Path = CATALOG_DIR) -> dict[str, CropEntry]:
    return load_crops(directory, LOCAL_CROP_FILES)


def load_curve_numbers(directory: Path = CATALOG_DIR) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((directory / "curve_numbers_tr55.json").read_text(encoding="utf-8"))
    return data


def curve_number(cover: str, hsg: HSG) -> float:
    """TR-55 Table 2-2b curve number (average runoff condition, Ia = 0.2S)."""
    covers = load_curve_numbers()["covers"]
    if cover not in covers:
        raise CatalogError(f"unknown TR-55 cover class {cover!r}")
    return float(covers[cover][hsg])


def load_soil_textures(directory: Path = CATALOG_DIR) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((directory / "soil_textures_fao56.json").read_text(encoding="utf-8"))
    return data


def demo_soil(site_id: str, texture: str = "silt_loam", bound: Literal["low", "mid", "high"] = "mid") -> SoilSpec:
    """DEMO soil assumption from FAO-56 Table 19 (no site soil data yet; D8 data comes from M3).

    AWC = 1000 (theta_FC - theta_WP) per metre (FAO-56 eq. 82 per unit depth), at the low/mid/high end
    of the printed range. The texture itself is an assumption, not an observation.
    """
    tex = load_soil_textures()["textures"][texture]
    lo, hi = (1000.0 * v for v in tex["awc_m3_m3"])
    value = {"low": lo, "mid": (lo + hi) / 2.0, "high": hi}[bound]
    profile = SoilProfile(
        id=f"demo-soil-{texture}-{bound}",
        site_id=site_id,
        available_water_capacity_mm_per_m=ParamValue(
            value=value,
            unit="mm/m",
            reference=f"FAO-56 Table 19, {texture.replace('_', ' ')} (theta_FC - theta_WP) {bound} of range",
            region_relevance="DEMO assumption: texture not observed at the site",
            uncertainty=f"FAO-56 Table 19 range {lo:.0f}-{hi:.0f} mm/m",
        ),
        root_zone_depth_m=ParamValue(
            value=None, unit="m", reference=None, uncertainty="Crop-dependent: set from the crop catalog (M4)"
        ),
        texture=texture.replace("_", " "),
        source_ids=[],
        is_demo=True,
    )
    return SoilSpec(
        profile=profile,
        data_depth_m=1.0,
        hsg=tex["tr55_hsg"],
        annex7_class=tex["annex7_class"],
        notes=(
            f"DEMO soil: FAO-56 Table 19 {texture.replace('_', ' ')} assumed; not site data.",
            f"Hydrologic soil group {tex['tr55_hsg']} from the TR-55 Appendix A texture table (assumption).",
        ),
    )


def _texture_key(texture: str | None) -> str | None:
    return None if texture is None else texture.strip().lower().replace(" ", "_")


def soil_spec_from_profile(
    profile: SoilProfile, *, data_depth_m: float, hsg: HSG | None = None, extra_notes: tuple[str, ...] = ()
) -> SoilSpec:
    """Engine soil inputs from a stored ``SoilProfile`` (e.g. M3's SSURGO profile).

    AWC and texture come from the profile. The FAO-56 Annex 7 class comes from the texture. The TR-55
    hydrologic soil group should come from the soil survey; when it is not given it is inferred from the
    texture (TR-55 Appendix A, disturbed profiles) and disclosed. An unknown texture blocks the run.
    """
    key = _texture_key(profile.texture)
    textures = load_soil_textures()["textures"]
    if key not in textures:
        raise CatalogError(
            f"soil texture {profile.texture!r} is not in the FAO-56 Table 19 catalog; "
            "the bare-soil class and hydrologic group are unknown"
        )
    tex = textures[key]
    notes = list(extra_notes)
    if hsg is None:
        hsg = tex["tr55_hsg"]
        notes.append(
            f"Hydrologic soil group {hsg} inferred from texture '{profile.texture}' (TR-55 Appendix A); "
            "the soil survey's own group is not loaded yet."
        )
    return SoilSpec(
        profile=profile, data_depth_m=data_depth_m, hsg=hsg, annex7_class=tex["annex7_class"], notes=tuple(notes)
    )


def with_awc(soil: SoilSpec, awc_mm_per_m: float, label: str) -> SoilSpec:
    """Same soil with AWC replaced (sensitivity). ``label`` says where the value comes from."""
    if not awc_mm_per_m > 0:
        raise ValueError("AWC must be > 0 mm/m")
    old = soil.profile.available_water_capacity_mm_per_m
    new_param = old.model_copy(update={"value": float(awc_mm_per_m), "region_relevance": label})
    profile = soil.profile.model_copy(
        update={"id": f"{soil.profile.id}@awc{awc_mm_per_m:g}", "available_water_capacity_mm_per_m": new_param}
    )
    note = f"Sensitivity: AWC set to {awc_mm_per_m:g} mm/m ({label})."
    return SoilSpec(profile, soil.data_depth_m, soil.hsg, soil.annex7_class, (*soil.notes, note))
