from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/decision-card", tags=["decisions"])


@router.post("")
def create_decision_card() -> None:
    """Record the farmer's choice + reason and export a decision card.

    TODO(M1): export must include sources, run/model versions, parameters, ranges, limitations and
    local-review questions (DEVELOPMENT_GUIDE.md section 4 "Decide").
    """
    raise HTTPException(501, "Decision card not implemented yet (owner: M1)")
