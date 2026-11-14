"""Crop parameters (with citations) and stored validation results. Owner: M1."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ftm.api.auth import UserDep, site_access
from ftm.api.services.decisions import catalog_crops
from ftm.api.services.rotations import selectable_crops
from ftm.contracts.models import CropProfile, Validation
from ftm.db.models import ValidationRow
from ftm.db.session import get_session

router = APIRouter(tags=["evidence"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/crops", response_model=list[CropProfile])
def list_crops(for_rotations: bool = False) -> list[CropProfile]:
    """The crop catalog: every parameter with its value, unit, reference and uncertainty (null = missing).

    ``for_rotations`` lists only the crops a user can put into a rotation (D15): the generic FAO catalog, without
    the site-local variants that belong to the reviewed ks-field-2 scenario.
    """
    if for_rotations:
        return sorted((e.profile for e in selectable_crops().values()), key=lambda c: c.id)
    return sorted(catalog_crops().values(), key=lambda c: c.id)


@router.get("/validations", response_model=list[Validation])
def list_validations(session: SessionDep, user: UserDep, site_id: str) -> list[Validation]:
    """Stored validation results (ids name the site: ``val_<target>_<site>_<utc>``), newest first."""
    site_access(session, site_id, user)
    stmt = select(ValidationRow).order_by(ValidationRow.created_at.desc())
    if site_id:
        stmt = stmt.where(ValidationRow.id.contains(f"_{site_id}_", autoescape=True))
    return [Validation.model_validate(r.payload) for r in session.scalars(stmt)]
