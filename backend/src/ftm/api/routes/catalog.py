"""Crop parameters (with citations) and stored validation results. Owner: M1."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ftm.api.services.decisions import catalog_crops
from ftm.contracts.models import CropProfile, Validation
from ftm.db.models import ValidationRow
from ftm.db.session import get_session

router = APIRouter(tags=["evidence"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/crops", response_model=list[CropProfile])
def list_crops() -> list[CropProfile]:
    """The crop catalog: every parameter with its value, unit, reference and uncertainty (null = missing)."""
    return sorted(catalog_crops().values(), key=lambda c: c.id)


@router.get("/validations", response_model=list[Validation])
def list_validations(session: SessionDep, site_id: str | None = None) -> list[Validation]:
    """Stored validation results (ids name the site: ``val_<target>_<site>_<utc>``), newest first."""
    stmt = select(ValidationRow).order_by(ValidationRow.created_at.desc())
    if site_id:
        stmt = stmt.where(ValidationRow.id.like(f"%\\_{site_id}\\_%"))
    return [Validation.model_validate(r.payload) for r in session.scalars(stmt)]
