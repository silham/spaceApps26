from datetime import UTC, date, datetime
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ftm.api.routes._geo import as_geojson
from ftm.api.services.decisions import catalog_crops
from ftm.contracts.models import EnvironmentalTimeline, FarmerContext, Site
from ftm.data.engine_inputs import latest_weather_source_id
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
def list_sites(session: SessionDep) -> list[Site]:
    return [_to_contract(session, r) for r in session.scalars(select(SiteRow).order_by(SiteRow.id))]


@router.get("/{site_id}", response_model=Site)
def get_site(site_id: str, session: SessionDep) -> Site:
    row = session.get(SiteRow, site_id)
    if row is None:
        raise HTTPException(404, f"Site {site_id!r} not found")
    return _to_contract(session, row)


@router.get("/{site_id}/farmer-context", response_model=FarmerContext)
def get_farmer_context(site_id: str, session: SessionDep) -> FarmerContext:
    """Farmer-confirmed inputs. Unconfirmed fields are null (never filled with a guess)."""
    row = _site_or_404(session, site_id)
    try:
        return FarmerContext.model_validate(row.farmer_context or {})
    except ValueError:
        return FarmerContext()  # legacy free-form context is not a farmer confirmation


@router.put("/{site_id}/farmer-context", response_model=FarmerContext)
def put_farmer_context(site_id: str, ctx: FarmerContext, session: SessionDep) -> FarmerContext:
    """Store the farmer's confirmation. Changing it makes earlier runs outdated (the UI says so)."""
    row = _site_or_404(session, site_id)
    known = set(catalog_crops())
    if ctx.available_crop_ids is not None and (bad := sorted(set(ctx.available_crop_ids) - known)):
        raise HTTPException(422, f"unknown crop id(s) {bad}; known: {sorted(known)}")
    ctx = ctx.model_copy(update={"updated_at": datetime.now(UTC)})
    row.farmer_context = ctx.model_dump(mode="json")
    session.commit()
    return ctx


@router.get("/{site_id}/timeline", response_model=EnvironmentalTimeline)
def get_timeline(
    site_id: str, session: SessionDep, start: date | None = None, end: date | None = None
) -> EnvironmentalTimeline:
    """Daily rain and temperature (one weather source) plus quality-checked NDVI composites.

    Defaults to the last three years of the weather record. Missing rain is null, never zero.
    """
    row = _site_or_404(session, site_id)
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
