from fastapi import APIRouter

from ftm import MODEL_VERSION, __version__
from ftm.config import get_settings
from ftm.contracts.models import SCHEMA_VERSION

router = APIRouter(tags=["meta"])


@router.get("/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "api_version": __version__,
        "schema_version": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "demo_mode": get_settings().demo_mode,
    }
