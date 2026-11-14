"""User-selected farms (D13): what is refused, and that unreviewed farms are observe-only. No network used."""

from collections.abc import Iterator

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from ftm.api.services import runs as run_svc
from ftm.api.services import sites as svc
from ftm.contracts.models import NewSiteRequest, RunRequest
from ftm.db.session import get_engine


def square(lon: float, lat: float, d: float) -> dict[str, object]:
    return {
        "type": "Polygon",
        "coordinates": [[[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d], [lon, lat]]],
    }


@pytest.fixture
def session() -> Iterator[Session]:
    try:
        conn = get_engine().connect()
        conn.execute(text("select postgis_version()"))
        conn.rollback()
    except Exception as exc:
        pytest.skip(f"no PostGIS available: {exc.__class__.__name__}")
    trans = conn.begin()
    s = Session(bind=conn, join_transaction_mode="create_savepoint")
    try:
        yield s
    finally:
        s.close()
        trans.rollback()
        conn.close()


def test_request_limits() -> None:
    with pytest.raises(ValidationError):
        NewSiteRequest(name="x", latitude=80, longitude=0)  # polar
    with pytest.raises(ValidationError):
        NewSiteRequest(name="", latitude=10, longitude=0)


def test_site_ids_are_stable_per_point() -> None:
    a = svc.site_id_for(NewSiteRequest(name="North Paddock!", latitude=8.31, longitude=80.4))
    b = svc.site_id_for(NewSiteRequest(name="North Paddock!", latitude=8.31, longitude=80.4))
    c = svc.site_id_for(NewSiteRequest(name="North Paddock!", latitude=8.32, longitude=80.4))
    assert a == b != c and a.startswith("north-paddock-")


def test_open_sea_is_refused() -> None:
    with pytest.raises(svc.SiteRequestError, match="not on land"):
        svc._timezone(0.0, -30.0)
    assert svc._timezone(8.31, 80.40) == "Asia/Colombo"


def test_soil_source_follows_d8() -> None:
    assert svc._steps(38.0, -100.9)[1].source == "USDA SSURGO"
    assert svc._steps(8.31, 80.40)[1].source == "ISRIC SoilGrids 2.0"


def test_outline_checks(session: Session) -> None:
    ok = NewSiteRequest(name="f", latitude=8.3105, longitude=80.4005, boundary_geojson=square(80.4, 8.31, 0.002))
    g, area = svc._check_boundary(session, ok)
    assert g is not None and g["type"] == "MultiPolygon" and area is not None and 4 < area < 6
    bowtie = {
        "type": "Polygon",
        "coordinates": [[[80.39, 8.30], [80.41, 8.32], [80.41, 8.30], [80.39, 8.32], [80.39, 8.30]]],
    }
    with pytest.raises(svc.SiteRequestError, match="crosses itself"):
        svc._check_boundary(session, NewSiteRequest(name="f", latitude=8.31, longitude=80.4, boundary_geojson=bowtie))
    with pytest.raises(svc.SiteRequestError, match="draw one field"):
        big = NewSiteRequest(name="f", latitude=8.5, longitude=80.5, boundary_geojson=square(80.0, 8.0, 1.0))
        svc._check_boundary(session, big)
    with pytest.raises(svc.SiteRequestError, match="inside the drawn field"):
        out = NewSiteRequest(name="f", latitude=9.0, longitude=81.0, boundary_geojson=square(80.4, 8.31, 0.002))
        svc._check_boundary(session, out)


def test_unreviewed_farm_is_observe_only(session: Session) -> None:
    assert not svc.has_strategies(session, "some-new-farm")
    assert svc.has_strategies(session, "ks-field-2")
    with pytest.raises(run_svc.SiteNotReadyError, match="observe-only"):
        run_svc.create_run(session, RunRequest(site_id="some-new-farm"))


def test_credentials_are_never_echoed() -> None:
    assert "SECRET" not in svc._readable("GET https://x/api?key=SECRET&q=1 failed")
