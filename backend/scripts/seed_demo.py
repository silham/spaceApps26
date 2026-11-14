"""Load DEMO fixtures into the database (idempotent upsert). Usage: uv run python scripts/seed_demo.py"""

import json

from geoalchemy2.functions import ST_GeomFromGeoJSON
from sqlalchemy.orm import Session

from ftm.db.models import ResultRow, SimulationRunRow, SiteRow, SourceRow, StrategyRow
from ftm.db.session import get_engine
from ftm.fixtures import load_demo
from ftm.provenance import inputs_hash


def _geom(geojson: dict | None):  # type: ignore[no-untyped-def]
    return None if geojson is None else ST_GeomFromGeoJSON(json.dumps(geojson))


def main() -> None:
    demo = load_demo()
    with Session(get_engine()) as s, s.begin():
        for site in demo.sites:
            data = site.model_dump(exclude={"boundary_geojson"})
            s.merge(SiteRow(**data, boundary=_geom(site.boundary_geojson)))
        for src in demo.sources:
            data = src.model_dump(exclude={"footprint_geojson"})
            s.merge(SourceRow(**data, footprint=_geom(src.footprint_geojson)))
        s.flush()
        for st in demo.strategies:
            s.merge(StrategyRow(**st.model_dump(mode="json")))
        s.flush()
        for run in demo.simulation_runs:
            data = run.model_dump(exclude={"sample_period"})
            data["inputs_hash"] = inputs_hash(run.model_dump(mode="json", exclude={"id", "created_at"}))
            s.merge(SimulationRunRow(**data, sample_start=run.sample_period[0], sample_end=run.sample_period[1]))
        s.flush()
        for res in demo.results:
            s.merge(ResultRow(**res.model_dump(exclude={"range_label"})))
    print(f"Seeded DEMO data: {len(demo.sites)} site(s), {len(demo.strategies)} strategies, {len(demo.results)} results")


if __name__ == "__main__":
    main()
