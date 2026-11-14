from fastapi.testclient import TestClient

from ftm.api.main import app

client = TestClient(app)


def test_health() -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert {"schema_version", "model_version", "demo_mode"} <= body.keys()


def test_health_reports_the_engine_model_version() -> None:
    from ftm.engine.ensemble import MODEL_VERSION

    assert client.get("/health").json()["model_version"] == MODEL_VERSION


def test_run_and_card_requests_are_validated() -> None:
    from ftm.api.auth import require_user
    from ftm.db.models import UserRow
    from ftm.db.session import get_session

    app.dependency_overrides[require_user] = lambda: UserRow(id="test")
    app.dependency_overrides[get_session] = lambda: None
    try:
        assert client.post("/runs", json={}, headers={"X-FTM-Request": "1"}).status_code == 422
        assert client.post("/decision-cards", json={"site_id": "s"}, headers={"X-FTM-Request": "1"}).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_journey_route_returns_nine_stages_in_order(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from ftm.api.auth import require_user
    from ftm.api.routes import journey as route
    from ftm.contracts.models import JourneyStage, StageStatus
    from ftm.data.journey import ORDER
    from ftm.db.models import UserRow
    from ftm.db.session import get_session

    stages = [JourneyStage(stage=n, status=StageStatus.NOT_STARTED, summary="x") for n in ORDER]
    monkeypatch.setattr(route.journey, "build_journey", lambda site_id, session, **kwargs: stages)
    monkeypatch.setattr(route, "site_access", lambda *a: None)
    app.dependency_overrides[require_user] = lambda: UserRow(id="test")
    app.dependency_overrides[get_session] = lambda: None
    try:
        body = client.get("/journey/ks-field-2").json()
    finally:
        app.dependency_overrides.clear()
    assert [s["stage"] for s in body] == [n.value for n in ORDER]


def test_journey_route_unknown_site_is_404(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from ftm.api.auth import require_user
    from ftm.api.routes import journey as route
    from ftm.data.journey import SiteNotFoundError
    from ftm.db.models import UserRow
    from ftm.db.session import get_session

    def missing(site_id: str, session: object, **kwargs: object) -> list[object]:
        raise SiteNotFoundError(site_id)

    monkeypatch.setattr(route, "site_access", lambda *a: None)
    monkeypatch.setattr(route.journey, "build_journey", missing)
    app.dependency_overrides[require_user] = lambda: UserRow(id="test")
    app.dependency_overrides[get_session] = lambda: None
    try:
        assert client.get("/journey/nope").status_code == 404
    finally:
        app.dependency_overrides.clear()
