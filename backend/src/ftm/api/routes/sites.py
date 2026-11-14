from datetime import UTC, date, datetime
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ftm.api.auth import UserDep, site_access, visible_sites
from ftm.api.routes._geo import as_geojson
from ftm.api.services import prediction as prediction_svc
from ftm.api.services import rotations as rotation_svc
from ftm.api.services import sites as site_svc
from ftm.api.services.decisions import catalog_crops
from ftm.contracts.models import (
    EnvironmentalTimeline,
    FarmerContext,
    FarmUpdate,
    NewSiteRequest,
    PredictionHorizon,
    RotationsUpdate,
    Site,
    SiteLoadStatus,
    Strategy,
    WeatherOutlook,
)
from ftm.data.engine_inputs import EngineInputsNotAvailableError, latest_weather_source_id
from ftm.data.forcing import FLAG_SUFFIX, ForcingNotAvailableError, get_daily_forcing
from ftm.data.vegetation import VegetationNotAvailableError, get_vi_composites
from ftm.db.models import SiteRow, SourceRow
from ftm.db.session import get_session
from ftm.engine.forcing import RAIN, TMAX, TMIN

router = APIRouter(prefix="/sites", tags=["sites"])
SessionDep = Annotated[Session, Depends(get_session)]


def _to_contract(session: Session, row: SiteRow) -> Site:
    return Site(
        id=row.id,
        owner_user_id=row.owner_user_id,
        archived=row.archived,
        name=row.name,
        latitude=row.latitude,
        longitude=row.longitude,
        boundary_geojson=as_geojson(session, row.boundary),
        timezone=row.timezone,
        area_ha=row.area_ha,
        farmer_context=row.farmer_context,
        is_demo=row.is_demo,
    )


@router.get("", response_model=list[Site])
def list_sites(session: SessionDep, user: UserDep, include_archived: bool = False) -> list[Site]:
    stmt = select(SiteRow).where(visible_sites(user)).order_by(SiteRow.id)
    if not include_archived:
        stmt = stmt.where(SiteRow.archived.is_(False))
    return [_to_contract(session, r) for r in session.scalars(stmt)]


@router.post("", response_model=SiteLoadStatus, status_code=202)
def create_site(req: NewSiteRequest, session: SessionDep, user: UserDep) -> SiteLoadStatus:
    """Register a farm picked on the map and start loading its data in the background (D13: observe only).

    Weather (NASA POWER, global), soil (SSURGO in the contiguous US, SoilGrids elsewhere; D8) and MODIS
    vegetation (needs Earth Engine on the server). Poll ``GET /sites/{id}/load``. The same point again returns
    the existing farm instead of loading twice.
    """
    try:
        return site_svc.create_site(session, req, owner_user_id=user.id)
    except site_svc.SiteRequestError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/{site_id}/load", response_model=SiteLoadStatus)
def get_load_status(site_id: str, session: SessionDep, user: UserDep) -> SiteLoadStatus:
    site_access(session, site_id, user)
    try:
        return site_svc.load_status(session, site_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None


@router.post("/{site_id}/refresh", response_model=SiteLoadStatus, status_code=202)
def refresh(site_id: str, session: SessionDep, user: UserDep) -> SiteLoadStatus:
    """Fetch newer weather (older than 3 days) and a newer seasonal forecast (older than 7 days) in the
    background (D16). Editing stays possible meanwhile; the outlook and runs use the newest data once stored."""
    site_access(session, site_id, user)
    try:
        return site_svc.refresh_site(session, site_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None


@router.get("/{site_id}/horizon", response_model=PredictionHorizon)
def get_horizon(site_id: str, session: SessionDep, user: UserDep) -> PredictionHorizon:
    """The comparison period on the real calendar: from the day after the last observed weather day (D16)."""
    site_access(session, site_id, user)
    _ready(session, site_id)
    try:
        return prediction_svc.horizon_for(session, site_id)
    except (EngineInputsNotAvailableError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/{site_id}/outlook", response_model=WeatherOutlook)
def get_outlook(site_id: str, session: SessionDep, user: UserDep) -> WeatherOutlook:
    """Forecast odds for the coming months and daily bands from forecast-weighted past years (D16)."""
    site_access(session, site_id, user)
    _ready(session, site_id)
    try:
        return prediction_svc.outlook_for(session, site_id)
    except (EngineInputsNotAvailableError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from None


def _ready(session: Session, site_id: str) -> None:
    if site_svc.load_status(session, site_id).status != "done":
        raise HTTPException(409, "Wait for the farm's data load to finish")


@router.get("/{site_id}", response_model=Site)
def get_site(site_id: str, session: SessionDep, user: UserDep) -> Site:
    return _to_contract(session, site_access(session, site_id, user))


@router.get("/{site_id}/farmer-context", response_model=FarmerContext)
def get_farmer_context(site_id: str, session: SessionDep, user: UserDep) -> FarmerContext:
    """Farmer-confirmed inputs. Unconfirmed fields are null (never filled with a guess)."""
    row = site_access(session, site_id, user)
    try:
        return FarmerContext.model_validate(row.farmer_context or {})
    except ValueError:
        return FarmerContext()  # legacy free-form context is not a farmer confirmation


@router.put("/{site_id}/farmer-context", response_model=FarmerContext)
def put_farmer_context(site_id: str, ctx: FarmerContext, session: SessionDep, user: UserDep) -> FarmerContext:
    """Store the farmer's confirmation. Changing it makes earlier runs outdated (the UI says so)."""
    row = site_access(session, site_id, user)
    known = set(catalog_crops())
    if ctx.available_crop_ids is not None and (bad := sorted(set(ctx.available_crop_ids) - known)):
        raise HTTPException(422, f"unknown crop id(s) {bad}; known: {sorted(known)}")
    if ctx.current_crop_id is not None and ctx.current_crop_id not in known:
        raise HTTPException(422, f"unknown crop {ctx.current_crop_id!r} on the field now; known: {sorted(known)}")
    if ctx.current_crop_id is not None and ctx.current_plant_date is None:
        raise HTTPException(422, "Give the planting date of the crop on the field now")
    if ctx.current_plant_date and ctx.last_harvest_date and ctx.last_harvest_date < ctx.current_plant_date:
        raise HTTPException(422, "The harvest date is before the planting date")
    ctx = ctx.model_copy(update={"updated_at": datetime.now(UTC)})
    row.farmer_context = ctx.model_dump(mode="json")
    session.commit()
    return ctx


@router.get("/{site_id}/timeline", response_model=EnvironmentalTimeline)
def get_timeline(
    site_id: str, session: SessionDep, user: UserDep, start: date | None = None, end: date | None = None
) -> EnvironmentalTimeline:
    """Daily rain and temperature (one weather source) plus quality-checked NDVI composites.

    Defaults to the last three years of the weather record. Missing rain is null, never zero.
    """
    row = site_access(session, site_id, user)
    src_id = latest_weather_source_id(session, site_id)
    src = session.get(SourceRow, src_id) if src_id else None
    if src is None:
        return EnvironmentalTimeline(
            site_id=site_id, start=start or date.today(), end=end or date.today(), weather_source_id=None,
            processing_run_id=None, dates=[], rain_mm=[], rain_flag=[], tmax_c=[], tmin_c=[], source_ids=[],
            vegetation_note="No weather loaded for this site.", is_demo=row.is_demo,
        )  # fmt: skip
    end = end or src.coverage_end or date.today()
    start = start or date(end.year - 2, 1, 1)
    if end < start or (end - start).days > 366 * 10:
        raise HTTPException(422, "start must precede end, and the window can span at most 10 years")
    try:
        f = get_daily_forcing(site_id, start, end, src.id, session=session)
    except ForcingNotAvailableError as exc:
        raise HTTPException(409, str(exc)) from None

    def col(name: str) -> list[float | None]:
        if name not in f.columns:
            return [None] * len(f)
        return [None if pd.isna(v) else round(float(v), 2) for v in f[name]]

    flags = f.get(f"{RAIN}{FLAG_SUFFIX}")
    tl = EnvironmentalTimeline(
        site_id=site_id,
        start=start,
        end=end,
        weather_source_id=src.id,
        processing_run_id=f.attrs.get("processing_run_id"),
        dates=[pd.Timestamp(d).date() for d in f.index],
        rain_mm=col(RAIN),
        rain_flag=[None if flags is None or pd.isna(v) else str(v) for v in (flags if flags is not None else f.index)],
        tmax_c=col(TMAX),
        tmin_c=col(TMIN),
        source_ids=[src.id],
        is_demo=row.is_demo,
    )
    try:
        vi = get_vi_composites(site_id, session=session)
    except VegetationNotAvailableError as exc:
        return tl.model_copy(update={"vegetation_note": f"{exc}: satellite vegetation not shown."})
    # Loaders may return composite_start as datetime64 or as plain `date` objects; compare as datetime64.
    vi = vi.assign(composite_start=pd.to_datetime(vi["composite_start"]))
    vi = vi[(vi["composite_start"] >= pd.Timestamp(start)) & (vi["composite_start"] <= pd.Timestamp(end))]
    vsrc = (vi.attrs.get("source_ids") or [None])[0]
    return tl.model_copy(
        update={
            "vegetation_source_id": vsrc,
            "vegetation_dates": [pd.Timestamp(d).date() for d in vi["composite_start"]],
            "ndvi": [
                round(float(v), 3) if ok and not pd.isna(v) else None
                for v, ok in zip(vi["ndvi"], vi["qa_pass"], strict=True)
            ],
            "vegetation_note": "NDVI composites failing the MODIS quality check (cloud, snow) are shown as gaps.",
            "source_ids": [src.id, *([vsrc] if vsrc else [])],
        }
    )


def _site_or_404(session: Session, site_id: str) -> SiteRow:
    row = session.get(SiteRow, site_id)
    if row is None:
        raise HTTPException(404, f"Site {site_id!r} not found")
    return row


@router.put("/{site_id}", response_model=Site)
def update_site(site_id: str, req: FarmUpdate, session: SessionDep, user: UserDep) -> Site:
    row = site_access(session, site_id, user)
    status = site_svc.load_status(session, site_id)
    if status.status in ("queued", "running"):
        raise HTTPException(409, "Wait for the farm's data load to finish before editing or archiving it")
    row.name = req.name
    row.archived = req.archived
    session.commit()
    return _to_contract(session, row)


@router.put("/{site_id}/rotations", response_model=list[Strategy])
def put_rotations(site_id: str, req: RotationsUpdate, session: SessionDep, user: UserDep) -> list[Strategy]:
    """Save the farm's 1-3 user-built rotations (the first is current practice). Replaces the earlier set (D15)."""
    row = site_access(session, site_id, user)
    if row.archived:
        raise HTTPException(409, "Restore this farm before changing its rotations")
    if site_svc.load_status(session, site_id).status != "done":
        raise HTTPException(409, "Wait for the farm's data load to finish before building rotations")
    try:
        return rotation_svc.save_rotations(session, row, req)
    except rotation_svc.RotationError as exc:
        raise HTTPException(422, str(exc)) from None
