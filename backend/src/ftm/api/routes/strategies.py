from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ftm.contracts.models import Strategy
from ftm.db.models import StrategyRow
from ftm.db.session import get_session

router = APIRouter(prefix="/strategies", tags=["strategies"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[Strategy])
def list_strategies(session: SessionDep, site_id: str | None = None) -> list[Strategy]:
    stmt = select(StrategyRow).order_by(StrategyRow.is_baseline.desc(), StrategyRow.id)
    if site_id:
        stmt = stmt.where(StrategyRow.site_id == site_id)
    return [Strategy.model_validate(r) for r in session.scalars(stmt)]
