from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ftm.api.routes._geo import as_geojson
from ftm.contracts.models import Site
from ftm.db.models import SiteRow
from ftm.db.session import get_session

router = APIRouter(prefix="/sites", tags=["sites"])
SessionDep = Annotated[Session, Depends(get_session)]


def _to_contract(session: Session, row: SiteRow) -> Site:
    return Site(
        id=row.id,
        name=row.name,
        latitude=row.latitude,
        longitude=row.longitude,
        boundary_geojson=as_geojson(session, row.boundary),
        timezone=row.timezone,
        area_ha=row.area_ha,
        farmer_context=row.farmer_context,
        is_demo=row.is_demo,
    )


@router.get("", response_model=list[Site])
def list_sites(session: SessionDep) -> list[Site]:
    return [_to_contract(session, r) for r in session.scalars(select(SiteRow).order_by(SiteRow.id))]


@router.get("/{site_id}", response_model=Site)
def get_site(site_id: str, session: SessionDep) -> Site:
    row = session.get(SiteRow, site_id)
    if row is None:
        raise HTTPException(404, f"Site {site_id!r} not found")
    return _to_contract(session, row)
