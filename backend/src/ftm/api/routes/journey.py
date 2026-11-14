from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ftm.api.auth import UserDep, site_access
from ftm.contracts.models import JourneyStage
from ftm.data import journey
from ftm.db.session import get_session

router = APIRouter(prefix="/journey", tags=["data journey"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/{site_id}", response_model=list[JourneyStage])
def get_journey(site_id: str, session: SessionDep, user: UserDep) -> list[JourneyStage]:
    """The nine Data Journey stages for a site, Collect -> Compare, built from what is stored.

    Stages whose owner has not produced output yet (Simulate, Compare until M4 lands) come back as
    ``not_started`` naming the owner, so the UI shows an honest empty state.
    """
    site_access(session, site_id, user)
    try:
        return journey.build_journey(site_id, session, owner_user_id=user.id)
    except journey.SiteNotFoundError:
        raise HTTPException(404, f"Site {site_id!r} not found") from None
