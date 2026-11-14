"""Assemble the nine Data Journey stages for a site from what is stored. Owner: M3 (+ M5 stages).

``build_journey(site_id, session)`` is what the ``/journey/{site_id}`` route (M1) can return directly.
Stages owned by other members (Simulate, Compare: M4/M1) come back as ``not_started`` with the owner named,
so the UI can show its empty state honestly instead of inventing content.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ftm.contracts.models import JourneyStage, JourneyStageName, StageStatus, Validation
from ftm.data.vegetation import VegetationNotAvailableError, get_vi_composites
from ftm.db.models import ProcessingRunRow, SiteRow, SoilProfileRow, SourceRow, ValidationRow
from ftm.validation.phenology import PhenologyParams, detect_seasons, extract_stage
from ftm.validation.report import validate_stage

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
    if modis_run and JourneyStageName.CHECK in stages:
        qa = next((s for s in modis_run.steps if s.get("name") == "modis_qa"), None)
        if qa:
            chk = stages[JourneyStageName.CHECK]
            chk.details = {**chk.details, "satellite_vegetation_qa": qa["params"]}
            chk.source_ids = sorted(set(chk.source_ids) | set(modis_run.input_source_ids))

    validations = _validations(session, site_id)
    params = _tuned_params(validations)
    try:
        comps = get_vi_composites(site_id, session=session)
        stages[JourneyStageName.EXTRACT] = extract_stage(detect_seasons(comps, params), is_demo=is_demo)
        stages[JourneyStageName.EXTRACT].details["params_source"] = (
            f"tuned ({validations[0].id})" if validations else "default (not tuned yet)"
        )
    except VegetationNotAvailableError:
        stages[JourneyStageName.EXTRACT] = _missing(
            JourneyStageName.EXTRACT, "No satellite vegetation data for this site: a local crop calendar is needed."
        )
    stages[JourneyStageName.VALIDATE] = validate_stage(
        validations, source_ids=modis_run.input_source_ids if modis_run else [], is_demo=is_demo
    )
    for name, owner in (
        (JourneyStageName.SIMULATE, "simulation engine (M4)"),
        (JourneyStageName.COMPARE, "comparison (M4/M1)"),
    ):
        stages[name] = JourneyStage(
            stage=name,
            status=StageStatus.NOT_STARTED,
            summary=f"Not available yet: owned by the {owner}.",
            is_demo=is_demo,
        )
    return [stages[n] for n in ORDER]


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


def _validations(session: Session, site_id: str) -> list[Validation]:
    rows = session.execute(
        select(ValidationRow)
        .where(ValidationRow.id.like(f"val_phenology_{site_id}_%"))
        .order_by(ValidationRow.created_at.desc())
    ).scalars()
    return [Validation.model_validate(r.payload) for r in rows]


def _tuned_params(validations: list[Validation]) -> PhenologyParams:
    if not validations:
        return PhenologyParams()
    m = validations[0].metrics
    return PhenologyParams(int(m["param_window"]), int(m["param_polyorder"]), float(m["param_fraction"]))


def _missing(name: JourneyStageName, why: str) -> JourneyStage:
    return JourneyStage(stage=name, status=StageStatus.UNAVAILABLE, summary=why)


def journey_json(stages: list[JourneyStage]) -> list[dict[str, Any]]:
    return [s.model_dump(mode="json") for s in stages]
