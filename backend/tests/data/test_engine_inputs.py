"""Engine inputs from the database: missing inputs stop the run with a reason, never a default."""

import importlib.util
import json
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pandas as pd
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from ftm.contracts.models import Site, SoilProfile, Source
from ftm.data.engine_inputs import (
    EngineInputsNotAvailableError,
    SiteEngineInputs,
    build_site_scenario,
    load_site_engine_inputs,
)
from ftm.db.session import get_engine

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def session() -> Iterator[Session]:
    try:
        conn = get_engine().connect()
        conn.execute(text("select 1 from site limit 1"))
        conn.rollback()
    except Exception as exc:
        pytest.skip(f"no migrated Postgres available: {exc.__class__.__name__}")
    trans = conn.begin()
    s = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        yield s
    finally:
        s.close()
        trans.rollback()
        conn.close()


def test_boundary_accepts_a_one_feature_collection(tmp_path: Path) -> None:
    poly = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
    path = tmp_path / "b.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": poly}]}))
    out = _script("load_power")._multipolygon(path)
    assert out == {"type": "MultiPolygon", "coordinates": [poly["coordinates"]]}
    two = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": poly}] * 2}
    path.write_text(json.dumps(two))
    with pytest.raises(SystemExit, match="exactly one feature"):
        _script("load_power")._multipolygon(path)


def test_site_without_scenarios_is_refused() -> None:
    site = Site(id="nowhere", name="x", latitude=0, longitude=0, timezone="UTC")
    src = Source(id="w", provider="p", product="p", variables=[], units={}, kind="reanalysis")
    inputs = SiteEngineInputs(
        site,
        src,
        SoilProfile.model_construct(),
        None,  # type: ignore[arg-type]  # soil is not read before the site check
        pd.DataFrame(),
        0.0,
        "",
    )
    with pytest.raises(EngineInputsNotAvailableError, match="no strategies are defined"):
        build_site_scenario(inputs)


def test_missing_site_names_what_to_load(session: Session) -> None:
    with pytest.raises(EngineInputsNotAvailableError, match=r"load_site\.py"):
        load_site_engine_inputs(session, "no-such-site")
