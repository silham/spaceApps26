"""Decision cards: record the choice and reason, export JSON + PDF. Owner: M1."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ftm.api.services import decisions as svc
from ftm.api.services import runs as run_svc
from ftm.contracts.models import DecisionCard, DecisionCardRequest
from ftm.db.session import get_session

router = APIRouter(prefix="/decision-cards", tags=["decisions"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.post("", response_model=DecisionCard, status_code=201)
def create_decision_card(req: DecisionCardRequest, session: SessionDep) -> DecisionCard:
    """Freeze the chosen strategy, the farmer's reason and the evidence of the run it was chosen from.

    Refused (409) for an infeasible strategy or a strategy/site not in the run; 404 for an unknown run.
    """
    try:
        return svc.create_card(session, req)
    except run_svc.RunNotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    except svc.DecisionRefusedError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("", response_model=list[DecisionCard])
def list_decision_cards(site_id: str, session: SessionDep) -> list[DecisionCard]:
    return svc.list_cards(session, site_id)


@router.get("/{card_id}.json")
def download_json(card_id: str, session: SessionDep) -> FileResponse:
    return _file(session, card_id, "json")


@router.get("/{card_id}.pdf")
def download_pdf(card_id: str, session: SessionDep) -> FileResponse:
    return _file(session, card_id, "pdf")


@router.get("/{card_id}", response_model=DecisionCard)
def get_decision_card(card_id: str, session: SessionDep) -> DecisionCard:
    try:
        card, row = svc.get_card(session, card_id)
    except svc.DecisionNotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    return card.model_copy(update={"sha256": row.sha256})


def _file(session: Session, card_id: str, kind: str) -> FileResponse:
    try:
        _, row = svc.get_card(session, card_id)
    except svc.DecisionNotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    name = row.json_path if kind == "json" else row.pdf_path
    path = svc.exports_dir() / name if name else None
    if path is None or not path.exists():
        raise HTTPException(404, f"{kind.upper()} export for {card_id!r} is missing on disk")
    media = "application/json" if kind == "json" else "application/pdf"
    return FileResponse(path, media_type=media, filename=f"decision-card-{card_id}.{kind}")
