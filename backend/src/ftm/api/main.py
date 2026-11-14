"""FastAPI application. Owner: M1. Interactive docs at /docs."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ftm import MODEL_VERSION, __version__
from ftm.api.routes import decisions, health, journey, runs, sites, sources, strategies
from ftm.config import get_settings
from ftm.contracts.models import SCHEMA_VERSION


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Farm Time Machine API",
        version=__version__,
        description=f"Contracts schema {SCHEMA_VERSION} · model {MODEL_VERSION}",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (health, sites, sources, strategies, journey, runs, decisions):
        app.include_router(module.router)
    return app


app = create_app()
