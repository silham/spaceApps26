"""Shared soil helpers: root-zone water from layered data, and storage. Owner: M3.

Available water capacity (AWC) here is the volumetric water held between field capacity and wilting
point, integrated over the top ``depth_m`` of soil and expressed per metre (mm of water per m of soil).
The engine (M4) multiplies by its own crop root depth; root depth itself is a crop parameter.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from geoalchemy2.functions import ST_GeomFromGeoJSON
from sqlalchemy.orm import Session

from ftm.contracts.models import SoilProfile, Source
from ftm.db.models import SoilProfileRow, SourceRow

DEFAULT_DEPTH_M = 1.0


@dataclass(frozen=True)
class Layer:
    top_cm: float
    bottom_cm: float
    awc_cm3_cm3: float | None  # volumetric water between field capacity and wilting point


@dataclass
class SoilResult:
    profile: SoilProfile
    source: Source
    # Machine-readable bounds for sensitivity analysis (validation plan section 4); None if the source
    # gives no valid bounds. Kept beside the contract because ParamValue only has a text field for this.
    awc_low_mm_per_m: float | None
    awc_high_mm_per_m: float | None
    details: dict[str, Any] = field(default_factory=dict)


def water_mm_per_m(layers: Sequence[Layer], depth_m: float = DEFAULT_DEPTH_M) -> float | None:
    """Depth-weighted AWC over 0..depth_m, in mm of water per m of soil.

    Returns None if any layer overlapping the depth lacks a value, or if the layers do not reach the
    full depth: an unknown part of the profile is never counted as zero water.
    """
    if depth_m <= 0:
        raise ValueError("depth_m must be positive")
    depth_cm = depth_m * 100.0
    covered_cm = 0.0
    water_cm = 0.0
    for layer in sorted(layers, key=lambda x: x.top_cm):
        overlap = max(0.0, min(layer.bottom_cm, depth_cm) - max(layer.top_cm, 0.0))
        if overlap == 0:
            continue
        if layer.awc_cm3_cm3 is None:
            return None
        water_cm += layer.awc_cm3_cm3 * overlap
        covered_cm += overlap
    if covered_cm < depth_cm - 1e-6:
        return None
    return water_cm * 10.0 / depth_m  # cm -> mm, then per metre


def upsert_soil(session: Session, result: SoilResult) -> None:
    src = result.source
    session.merge(
        SourceRow(
            **src.model_dump(exclude={"footprint_geojson"}),
            footprint=None if src.footprint_geojson is None else ST_GeomFromGeoJSON(json.dumps(src.footprint_geojson)),
        )
    )
    session.flush()
    p = result.profile
    session.merge(SoilProfileRow(id=p.id, site_id=p.site_id, params=json.loads(p.model_dump_json()), is_demo=p.is_demo))
