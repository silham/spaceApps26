from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ftm.api.routes._geo import as_geojson
from ftm.contracts.models import Source
from ftm.db.models import SourceRow
from ftm.db.session import get_session

router = APIRouter(prefix="/sources", tags=["sources"])
SessionDep = Annotated[Session, Depends(get_session)]

_COLUMNS = [f for f in Source.model_fields if f != "footprint_geojson"]


def _to_contract(session: Session, row: SourceRow) -> Source:
    data = {f: getattr(row, f) for f in _COLUMNS}
    return Source(**data, footprint_geojson=as_geojson(session, row.footprint))


@router.get("", response_model=list[Source])
def list_sources(session: SessionDep) -> list[Source]:
    return [_to_contract(session, r) for r in session.scalars(select(SourceRow).order_by(SourceRow.id))]


@router.get("/{source_id}", response_model=Source)
def get_source(source_id: str, session: SessionDep) -> Source:
    row = session.get(SourceRow, source_id)
    if row is None:
        raise HTTPException(404, f"Source {source_id!r} not found")
    return _to_contract(session, row)
