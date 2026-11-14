"""Assemble the nine Data Journey stages for a site from what is stored. Owner: M3 (+ M5 stages).

``build_journey(site_id, session)`` is what the ``/journey/{site_id}`` route (M1) can return directly.
Simulate and Compare come from the newest stored comparison run; before any run they are ``not_started``,
so the UI can show its empty state honestly instead of inventing content.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ftm.contracts.models import JourneyStage, JourneyStageName, StageStatus
from ftm.data.vegetation import VegetationNotAvailableError
from ftm.db.models import PairedDeltaRow, ProcessingRunRow, SimulationRunRow, SiteRow, SoilProfileRow, SourceRow
from ftm.validation.phenology import extract_stage
from ftm.validation.report import validate_stage
from ftm.validation.site_seasons import get_site_seasons, phenology_validations

ORDER = [
    JourneyStageName.COLLECT,
    JourneyStageName.CHECK,
    JourneyStageName.CLEAN,
    JourneyStageName.HANDLE_GAPS,
    JourneyStageName.ALIGN,
    JourneyStageName.EXTRACT,
    JourneyStageName.SIMULATE,
    JourneyStageName.VALIDATE,
    JourneyStageName.COMPARE,
]


class SiteNotFoundError(LookupError):
    pass


def build_journey(site_id: str, session: Session) -> list[JourneyStage]:
    site = session.get(SiteRow, site_id)
    if site is None:
        raise SiteNotFoundError(site_id)
    is_demo = bool(site.is_demo)
    weather_run = _latest_run(session, site_id, "power_")
    modis_run = _latest_run(session, site_id, "modis_")
    soil = (
        session.execute(
            select(SoilProfileRow).where(SoilProfileRow.site_id == site_id).order_by(SoilProfileRow.created_at.desc())
        )
        .scalars()
        .first()
    )

    source_ids = [r.input_source_ids[0] for r in (weather_run, modis_run) if r] + (
        list(soil.params.get("source_ids", [])) if soil else []
    )
    sources = {s.id: s for s in session.execute(select(SourceRow).where(SourceRow.id.in_(source_ids))).scalars()}
    stages: dict[JourneyStageName, JourneyStage] = {
        JourneyStageName.COLLECT: collect_stage(sources, weather_run, modis_run, soil, is_demo=is_demo)
    }

    # Check / Clean / Handle gaps / Align: stored with the weather processing run when it was created.
    stored = {j["stage"]: j for j in (weather_run.summary.get("journey", []) if weather_run else [])}
    for name in (JourneyStageName.CHECK, JourneyStageName.CLEAN, JourneyStageName.HANDLE_GAPS, JourneyStageName.ALIGN):
        if name.value in stored:
            stages[name] = JourneyStage.model_validate(stored[name.value])
        else:
            stages[name] = _missing(name, "No processed weather stored for this site yet (run scripts/load_site.py).")
    if JourneyStageName.ALIGN in stages and stages[JourneyStageName.ALIGN].status != StageStatus.UNAVAILABLE:
        al = stages[JourneyStageName.ALIGN]
        al.chart = {"type": "footprint_map", "layers": footprint_layers(session, site, al.details, sources)}
    if modis_run and JourneyStageName.CHECK in stages:
        qa = next((s for s in modis_run.steps if s.get("name") == "modis_qa"), None)
        if qa:
            chk = stages[JourneyStageName.CHECK]
            chk.details = {**chk.details, "satellite_vegetation_qa": qa["params"]}
            chk.source_ids = sorted(set(chk.source_ids) | set(modis_run.input_source_ids))

    validations = phenology_validations(site_id, session)
    try:
        ss = get_site_seasons(site_id, session)
        stages[JourneyStageName.EXTRACT] = extract_stage(ss.result, is_demo=is_demo)
        stages[JourneyStageName.EXTRACT].details["params_source"] = ss.params_source
    except VegetationNotAvailableError:
        stages[JourneyStageName.EXTRACT] = _missing(
            JourneyStageName.EXTRACT, "No satellite vegetation data for this site: a local crop calendar is needed."
        )
    stages[JourneyStageName.VALIDATE] = validate_stage(
        validations, source_ids=modis_run.input_source_ids if modis_run else [], is_demo=is_demo
    )
    stages[JourneyStageName.SIMULATE], stages[JourneyStageName.COMPARE] = run_stages(session, site_id, is_demo=is_demo)
    return [stages[n] for n in ORDER]


COMPARE_METRICS = ("irrigation_mm", "water_stress_days", "possible_low_cover_days")


def run_stages(session: Session, site_id: str, *, is_demo: bool) -> tuple[JourneyStage, JourneyStage]:
    """Simulate and Compare from the newest stored comparison run (the engine's own Simulate stage)."""
    run = session.scalars(
        select(SimulationRunRow)
        .where(SimulationRunRow.site_id == site_id, SimulationRunRow.detail.is_not(None))
        .order_by(SimulationRunRow.created_at.desc())
    ).first()
    if run is None or not run.detail or "journey" not in run.detail:
        none = "No comparison run yet: run the comparison to simulate the strategies."
        return (
            JourneyStage(
                stage=JourneyStageName.SIMULATE, status=StageStatus.NOT_STARTED, summary=none, is_demo=is_demo
            ),
            JourneyStage(stage=JourneyStageName.COMPARE, status=StageStatus.NOT_STARTED, summary=none, is_demo=is_demo),
        )
    simulate = JourneyStage.model_validate(run.detail["journey"])
    names = {s["id"]: s["name"] for s in run.detail.get("strategies", [])}
    deltas = session.scalars(
        select(PairedDeltaRow).where(PairedDeltaRow.run_id == run.id, PairedDeltaRow.metric.in_(COMPARE_METRICS))
    ).all()
    if not deltas:
        compare = JourneyStage(
            stage=JourneyStageName.COMPARE,
            status=StageStatus.UNAVAILABLE,
            summary="No paired comparison: the current-practice baseline was not simulated in the latest run.",
            source_ids=simulate.source_ids,
            processing_run_id=simulate.processing_run_id,
            details={"run_id": run.id},
            is_demo=run.is_demo,
        )
        return simulate, compare
    rows = [
        {
            "strategy_id": d.strategy_id,
            "strategy": names.get(d.strategy_id, d.strategy_id),
            "metric": d.metric,
            "unit": d.unit,
            "p10": d.p10,
            "p50": d.p50,
            "p90": d.p90,
            "share_better": d.share_better,
        }
        for d in deltas
    ]
    baseline = names.get(deltas[0].baseline_strategy_id, deltas[0].baseline_strategy_id)
    compare = JourneyStage(
        stage=JourneyStageName.COMPARE,
        status=StageStatus.OK,
        summary=(
            f"Each alternative is compared with {baseline} on the same {deltas[0].sample_count} weather paths; "
            "differences are taken path by path, then summarised."
        ),
        source_ids=simulate.source_ids,
        processing_run_id=simulate.processing_run_id,
        chart={
            "type": "paired_deltas",
            "title": f"Difference from {baseline} (median, central 80% simulation range)",
            "rows": rows,
        },
        details={"run_id": run.id, "baseline_strategy_id": deltas[0].baseline_strategy_id},
        is_demo=run.is_demo,
    )
    return simulate, compare


def footprint_layers(
    session: Session, site: SiteRow, align_details: dict[str, Any], sources: dict[str, SourceRow]
) -> dict[str, Any]:
    """Map layers for the Align card: field boundary, satellite pixel(s), weather grid point.

    Native footprints only; nothing is resampled, so the map shows how coarse each source really is.
    """
    feats: list[dict[str, Any]] = []
    boundary = session.scalar(select(func.ST_AsGeoJSON(SiteRow.boundary)).where(SiteRow.id == site.id))
    if boundary:
        feats.append(
            {
                "type": "Feature",
                "geometry": json.loads(boundary),
                "properties": {
                    "layer": "field_boundary",
                    "label": "Field boundary (approximate)",
                    "area_ha": site.area_ha,
                },
            }
        )
    for sid, src in sources.items():
        if src.footprint is None:
            continue
        g = session.scalar(select(func.ST_AsGeoJSON(SourceRow.footprint)).where(SourceRow.id == sid))
        feats.append(
            {
                "type": "Feature",
                "geometry": json.loads(g),
                "properties": {
                    "layer": "source_footprint",
                    "source_id": sid,
                    "label": f"{src.product} pixel",
                    "resolution": src.spatial_resolution,
                },
            }
        )
    gp = align_details.get("grid_point_lon_lat")
    if gp:
        feats.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": gp},
                "properties": {
                    "layer": "weather_grid_point",
                    "label": "Weather grid point (NASA POWER)",
                    "resolution": align_details.get("native_resolution"),
                },
            }
        )
    return {"type": "FeatureCollection", "features": feats}


def collect_stage(
    sources: dict[str, SourceRow],
    weather_run: ProcessingRunRow | None,
    modis_run: ProcessingRunRow | None,
    soil: SoilProfileRow | None,
    *,
    is_demo: bool = False,
) -> JourneyStage:
    rows = []
    for sid, src in sources.items():
        rows.append(
            {
                "source_id": sid,
                "provider": src.provider,
                "product": src.product,
                "version": src.version,
                "kind": src.kind,
                "coverage_start": src.coverage_start.isoformat() if src.coverage_start else None,
                "coverage_end": src.coverage_end.isoformat() if src.coverage_end else None,
                "spatial_resolution": src.spatial_resolution,
                "temporal_resolution": src.temporal_resolution,
                "retrieved_at": src.retrieved_at.isoformat() if src.retrieved_at else None,
                "license": src.license,
                "doi": src.doi,
                "raw_sha256": (src.raw_sha256 or "")[:12] or None,
                "limitations": src.limitations,
            }
        )
    missing = [
        label for label, ok in (("weather", weather_run), ("soil", soil), ("satellite vegetation", modis_run)) if not ok
    ]
    status = StageStatus.FAILED if weather_run is None else (StageStatus.WARNING if missing else StageStatus.OK)
    summary = f"{len(rows)} data sources collected and stored unchanged with checksums."
    if missing:
        summary += f" Missing: {', '.join(missing)}."
    return JourneyStage(
        stage=JourneyStageName.COLLECT,
        status=status,
        summary=summary,
        source_ids=sorted(sources),
        chart={
            "type": "coverage_strip",
            "sources": [{k: r[k] for k in ("source_id", "product", "coverage_start", "coverage_end")} for r in rows],
        },
        details={"sources": rows, "missing": missing},
        is_demo=is_demo,
    )


def _latest_run(session: Session, site_id: str, prefix: str) -> ProcessingRunRow | None:
    for run in session.execute(
        select(ProcessingRunRow).where(ProcessingRunRow.site_id == site_id).order_by(ProcessingRunRow.created_at.desc())
    ).scalars():
        if any(s.startswith(prefix) for s in run.input_source_ids or []):
            return run
    return None


def _missing(name: JourneyStageName, why: str) -> JourneyStage:
    return JourneyStage(stage=name, status=StageStatus.UNAVAILABLE, summary=why)


def journey_json(stages: list[JourneyStage]) -> list[dict[str, Any]]:
    return [s.model_dump(mode="json") for s in stages]
