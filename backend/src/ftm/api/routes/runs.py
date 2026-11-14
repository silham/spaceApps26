from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ftm.contracts.models import Result
from ftm.db.models import ResultRow
from ftm.db.session import get_session

router = APIRouter(prefix="/runs", tags=["runs"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.post("")
def create_run() -> None:
    """Run a supported edit (e.g. irrigation limit, planting window).

    TODO(M1 + M4): validate against the supported-edit set; unsupported -> 422 with a reason
    (never substitute the nearest scenario); look up the cache by inputs_hash; otherwise call the
    engine and persist SimulationRun + Result rows.
    """
    raise HTTPException(501, "Simulation runs not implemented yet (owners: M1/M4)")


@router.get("/{run_id}/results", response_model=list[Result])
def get_results(run_id: str, session: SessionDep) -> list[Result]:
    rows = session.scalars(select(ResultRow).where(ResultRow.run_id == run_id)).all()
    if not rows:
        raise HTTPException(404, f"No results for run {run_id!r}")
    return [Result.model_validate(r) for r in rows]
