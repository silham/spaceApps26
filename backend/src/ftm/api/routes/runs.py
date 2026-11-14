"""Comparison runs (D6 supported edits), results, paired differences and replay. Owner: M1."""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ftm.api.auth import UserDep, run_access, site_access, visible_runs
from ftm.api.services import runs as svc
from ftm.contracts.models import PairedDelta, ReplayTrace, Result, RunDetail, RunRequest
from ftm.db.models import SimulationRunRow
from ftm.db.session import get_session

router = APIRouter(prefix="/runs", tags=["runs"])
SessionDep = Annotated[Session, Depends(get_session)]
YEARS = re.compile(r"^\d{4}(-\d{4})*$")


@router.post("", response_model=RunDetail, status_code=201)
def create_run(req: RunRequest, session: SessionDep, user: UserDep) -> RunDetail:
    """Run the site's strategies on shared historical weather paths with the requested D6 edits.

    Unsupported edits are rejected by the request schema (422); a run the engine cannot compute as stated is
    422 with the reason; a site whose inputs are not loaded is 409. An identical earlier run is returned
    from the cache (``cached: true``).
    """
    site = site_access(session, req.site_id, user)
    if site.archived:
        raise HTTPException(409, "Restore this farm before starting a new comparison")
    try:
        return svc.create_run(session, req, owner_user_id=user.id)
    except svc.SiteNotReadyError as exc:
        raise HTTPException(409, str(exc)) from None
    except svc.RunBlockedError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("", response_model=list[RunDetail])
def list_runs(site_id: str, session: SessionDep, user: UserDep) -> list[RunDetail]:
    """Stored runs for a site, newest first."""
    site_access(session, site_id, user)
    rows = session.scalars(
        select(SimulationRunRow)
        .where(SimulationRunRow.site_id == site_id, SimulationRunRow.detail.is_not(None), visible_runs(user))
        .order_by(SimulationRunRow.created_at.desc())
        .limit(20)
    )
    return [svc.detail_from_row(row) for row in rows]


@router.get("/{run_id}", response_model=RunDetail)
def get_run(run_id: str, session: SessionDep, user: UserDep) -> RunDetail:
    run_access(session, run_id, user)
    try:
        return svc.detail_from_row(svc.get_run_row(session, run_id))
    except svc.RunNotFoundError as exc:
        raise HTTPException(404, str(exc)) from None


@router.get("/{run_id}/results", response_model=list[Result])
def get_results(run_id: str, session: SessionDep, user: UserDep) -> list[Result]:
    run_access(session, run_id, user)
    rows = svc.get_results(session, run_id)
    if not rows:
        raise HTTPException(404, f"No results for run {run_id!r}")
    return rows


@router.get("/{run_id}/deltas", response_model=list[PairedDelta])
def get_deltas(run_id: str, session: SessionDep, user: UserDep) -> list[PairedDelta]:
    """Strategy minus baseline, per weather path, summarised. Empty when the baseline was not simulated."""
    run_access(session, run_id, user)
    try:
        svc.get_run_row(session, run_id)
    except svc.RunNotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    return svc.get_deltas(session, run_id)


@router.get("/{run_id}/replay", response_model=ReplayTrace)
def get_replay(
    run_id: str,
    session: SessionDep,
    user: UserDep,
    years: Annotated[str, Query(description="Consecutive years of a replay window, e.g. 2011-2012")],
) -> ReplayTrace:
    """Replay one historical window day by day for every feasible strategy. Disabled windows are 422."""
    if not YEARS.match(years):
        raise HTTPException(422, "years must look like 2011-2012")
    run_access(session, run_id, user)
    try:
        return svc.replay(session, run_id, tuple(int(y) for y in years.split("-")))
    except svc.RunNotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    except svc.SiteNotReadyError as exc:
        raise HTTPException(409, str(exc)) from None
    except svc.RunBlockedError as exc:
        raise HTTPException(422, str(exc)) from None
