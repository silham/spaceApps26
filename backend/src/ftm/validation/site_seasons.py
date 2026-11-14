"""Detected growing seasons for a stored site, with the tuned parameters. Owner: M5, consumed by M4/M1.

``get_site_seasons(site_id, session)`` uses the newest stored phenology Validation record for the tuned
parameters (falls back to the defaults, and says so). Results are evidence for display and for checking a
crop calendar; they are never planting dates and never identify the crop.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ftm.contracts.models import Validation
from ftm.data.vegetation import get_vi_composites
from ftm.db.models import ValidationRow
from ftm.validation.phenology import PhenologyParams, PhenologyResult, detect_seasons


@dataclass
class SiteSeasons:
    result: PhenologyResult
    params_source: str  # "tuned (<validation id>)" or "default (not tuned yet)"
    validations: list[Validation]


def phenology_validations(site_id: str, session: Session) -> list[Validation]:
    """Stored phenology Validation records for a site, newest first (ids: ``val_phenology_<site>_<utc>``)."""
    rows = session.execute(
        select(ValidationRow)
        .where(ValidationRow.id.like(f"val_phenology_{site_id}_%"))
        .order_by(ValidationRow.created_at.desc())
    ).scalars()
    return [Validation.model_validate(r.payload) for r in rows]


def tuned_params(validations: list[Validation]) -> PhenologyParams:
    if not validations:
        return PhenologyParams()
    m = validations[0].metrics
    return PhenologyParams(int(m["param_window"]), int(m["param_polyorder"]), float(m["param_fraction"]))


def get_site_seasons(site_id: str, session: Session) -> SiteSeasons:
    """Raises ``ftm.data.vegetation.VegetationNotAvailableError`` if the site has no MODIS data."""
    validations = phenology_validations(site_id, session)
    params = tuned_params(validations)
    result = detect_seasons(get_vi_composites(site_id, session=session), params)
    source = f"tuned ({validations[0].id})" if validations else "default (not tuned yet)"
    return SiteSeasons(result=result, params_source=source, validations=validations)
