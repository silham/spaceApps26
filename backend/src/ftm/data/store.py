"""Write sites, sources, processing runs and observations to Postgres. Owner: M3.

Rules (AGENTS.md section 4):
- ``raw_value`` is written once per processing run and never updated.
- A re-run creates a new ProcessingRun with new observation rows; older runs stay as they were.
- The Data Journey payloads of a run are kept in ``processing_run.summary["journey"]``.
"""

from __future__ import annotations

import json
import math
from typing import Any

from geoalchemy2.functions import ST_GeomFromGeoJSON
from sqlalchemy import insert
from sqlalchemy.orm import Session

from ftm.contracts.models import QualityFlag, Site, Source
from ftm.data.pipeline.run import PipelineResult
from ftm.db.models import ObservationRow, ProcessingRunRow, SiteRow, SourceRow

INSERT_BATCH = 5000


def upsert_site(session: Session, site: Site) -> None:
    data = site.model_dump(exclude={"boundary_geojson", "owner_user_id", "archived"})
    existing = session.get(SiteRow, site.id)
    if existing is not None and existing.owner_user_id is not None:
        return  # farm metadata belongs to the user; ingestion only adds versioned observations
    session.merge(SiteRow(**data, boundary=_geom(site.boundary_geojson)))


def upsert_source(session: Session, source: Source) -> None:
    """Source rows describe one immutable raw download, so re-registering the same ID is idempotent."""
    data = source.model_dump(exclude={"footprint_geojson"})
    session.merge(SourceRow(**data, footprint=_geom(source.footprint_geojson)))


def save_pipeline_result(session: Session, result: PipelineResult) -> int:
    """Insert the run and all of its observation rows. Returns the number of observation rows."""
    run = result.run
    obs = result.observations
    # The observation table allows one row per site/source/variable/timestamp/run, so flagged duplicate
    # records cannot be rows there. They are kept, values included, in the run summary instead.
    is_dup = obs["quality_flag"] == QualityFlag.DUPLICATE.value
    duplicates = [
        {"variable": r["variable"], "date": str(r["date"]), "raw_value": _num(r["raw_value"])}
        for r in obs[is_dup].to_dict("records")
    ]
    summary = {
        **run.summary,
        "duplicates_not_stored_as_rows": duplicates,
        "journey": [json.loads(j.model_dump_json()) for j in result.journey],
    }
    session.add(
        ProcessingRunRow(
            id=run.id,
            version=run.version,
            site_id=run.site_id,
            input_source_ids=run.input_source_ids,
            steps=[json.loads(s.model_dump_json()) for s in run.steps],
            summary=summary,
            created_at=run.created_at,
        )
    )
    session.flush()  # the run must exist before observations reference it

    rows = [_observation(r) for r in obs[~is_dup].to_dict("records")]
    for i in range(0, len(rows), INSERT_BATCH):
        session.execute(insert(ObservationRow), rows[i : i + INSERT_BATCH])
    return len(rows)


def _observation(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "site_id": r["site_id"],
        "source_id": r["source_id"],
        "observed_at": r["observed_at"],
        "variable": r["variable"],
        "unit": r["unit"],
        "raw_value": _num(r["raw_value"]),
        "processed_value": _num(r["processed_value"]),
        "quality_flag": r["quality_flag"],
        "value_kind": r["value_kind"],
        "imputation_method": r["imputation_method"],
        "processing_run_id": r["processing_run_id"],
    }


def _num(v: Any) -> float | None:
    """NaN/None -> NULL. Missing stays missing in the DB; it is never written as 0."""
    if v is None:
        return None
    f = float(v)
    return None if math.isnan(f) else f


def _geom(geojson: dict[str, Any] | None) -> Any:
    return None if geojson is None else ST_GeomFromGeoJSON(json.dumps(geojson))
