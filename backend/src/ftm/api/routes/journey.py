from fastapi import APIRouter, HTTPException

from ftm.contracts.models import JourneyStage

router = APIRouter(prefix="/journey", tags=["data journey"])


@router.get("/{site_id}", response_model=list[JourneyStage])
def get_journey(site_id: str) -> list[JourneyStage]:
    """Nine Data Journey stages for a site.

    TODO(M1 with M3/M4/M5): assemble from pipeline stats (collect..align, M3),
    phenology (extract, M5), simulation (simulate, M4), validation (validate, M5).
    """
    raise HTTPException(501, "Data Journey not implemented yet (owners: M1/M3/M4/M5)")
