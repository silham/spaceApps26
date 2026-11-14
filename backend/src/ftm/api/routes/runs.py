"""Comparison runs (D6 supported edits), results, paired differences and replay. Owner: M1."""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ftm.api.services import runs as svc
from ftm.contracts.models import PairedDelta, ReplayTrace, Result, RunDetail, RunRequest
from ftm.db.session import get_session

router = APIRouter(prefix="/runs", tags=["runs"])
SessionDep = Annotated[Session, Depends(get_session)]
YEARS = re.compile(r"^\d{4}(-\d{4})*$")


@router.post("", response_model=RunDetail, status_code=201)
def create_run(req: RunRequest, session: SessionDep) -> RunDetail:
    """Run the site's strategies on shared historical weather paths with the requested D6 edits.

    Unsupported edits are rejected by the request schema (422); a run the engine cannot compute as stated is
    422 with the reason; a site whose inputs are not loaded is 409. An identical earlier run is returned
    from the cache (``cached: true``).
    """
    try:
        return svc.create_run(session, req)
    except svc.SiteNotReadyError as exc:
        raise HTTPException(409, str(exc)) from None
    except svc.RunBlockedError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("", response_model=list[RunDetail])
def list_runs(site_id: str, session: SessionDep) -> list[RunDetail]:
    """Stored runs for a site, newest first."""
    return svc.list_runs(session, site_id)


@router.get("/{run_id}", response_model=RunDetail)
def get_run(run_id: str, session: SessionDep) -> RunDetail:
    try:
        return svc.detail_from_row(svc.get_run_row(session, run_id))
    except svc.RunNotFoundError as exc:
        raise HTTPException(404, str(exc)) from None


@router.get("/{run_id}/results", response_model=list[Result])
def get_results(run_id: str, session: SessionDep) -> list[Result]:
    rows = svc.get_results(session, run_id)
    if not rows:
        raise HTTPException(404, f"No results for run {run_id!r}")
    return rows


@router.get("/{run_id}/deltas", response_model=list[PairedDelta])
def get_deltas(run_id: str, session: SessionDep) -> list[PairedDelta]:
    """Strategy minus baseline, per weather path, summarised. Empty when the baseline was not simulated."""
    try:
        svc.get_run_row(session, run_id)
    except svc.RunNotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    return svc.get_deltas(session, run_id)


@router.get("/{run_id}/replay", response_model=ReplayTrace)
def get_replay(
    run_id: str,
    session: SessionDep,
    years: Annotated[str, Query(description="Consecutive years of a replay window, e.g. 2011-2012")],
) -> ReplayTrace:
    """Replay one historical window day by day for every feasible strategy. Disabled windows are 422."""
    if not YEARS.match(years):
        raise HTTPException(422, "years must look like 2011-2012")
    try:
        return svc.replay(session, run_id, tuple(int(y) for y in years.split("-")))
    except svc.RunNotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    except svc.SiteNotReadyError as exc:
        raise HTTPException(409, str(exc)) from None
    except svc.RunBlockedError as exc:
        raise HTTPException(422, str(exc)) from None
