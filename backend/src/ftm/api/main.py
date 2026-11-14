"""FastAPI application. Owner: M1. Interactive docs at /docs."""

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from ftm import __version__
from ftm.api.auth import protect_mutation, require_user
from ftm.api.routes import catalog, decisions, health, journey, runs, sites, sources, strategies, users
from ftm.config import get_settings
from ftm.contracts.models import SCHEMA_VERSION
from ftm.engine.ensemble import MODEL_VERSION


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Farm Time Machine API",
        dependencies=[Depends(protect_mutation)],
        version=__version__,
        description=f"Contracts schema {SCHEMA_VERSION} · model {MODEL_VERSION}",
    )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Validation errors must never echo submitted passwords or other private input.
        return JSONResponse(
            status_code=422,
            content={"detail": [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]},
        )

    @app.middleware("http")
    async def prevent_private_caching(request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Accounts are required for every farm, run and decision (D14). Health, sign-in and the crop catalogue
    # are public; catalogue routes that name a farm check ownership themselves.
    for module in (health, users, catalog):
        app.include_router(module.router)
    for module in (sites, sources, strategies, journey, runs, decisions):
        app.include_router(module.router, dependencies=[Depends(require_user)])
    return app


app = create_app()
