from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ftm.api.auth import UserDep, site_access, visible_sites
from ftm.contracts.models import Strategy
from ftm.db.models import SiteRow, StrategyRow
from ftm.db.session import get_session

router = APIRouter(prefix="/strategies", tags=["strategies"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[Strategy])
def list_strategies(session: SessionDep, user: UserDep, site_id: str | None = None) -> list[Strategy]:
    stmt = (
        select(StrategyRow)
        .join(SiteRow, StrategyRow.site_id == SiteRow.id)
        .where(visible_sites(user), StrategyRow.superseded.is_(False))
        .order_by(StrategyRow.is_baseline.desc(), StrategyRow.id)
    )
    if site_id:
        site_access(session, site_id, user)
        stmt = stmt.where(StrategyRow.site_id == site_id)
    return [Strategy.model_validate(r) for r in session.scalars(stmt)]
