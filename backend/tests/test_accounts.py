"""Real PostgreSQL tests for account lifecycle and cross-user farm isolation; no external data downloads."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ftm.api.auth import COOKIE, password_matches, token_hash
from ftm.api.main import create_app
from ftm.api.services import sites as site_svc
from ftm.contracts.models import Site
from ftm.data.store import upsert_site
from ftm.db.models import (
    DecisionRecordRow,
    SimulationRunRow,
    SiteRow,
    SourceRow,
    StrategyRow,
    UserRow,
    UserSessionRow,
)
from ftm.db.session import get_engine, get_session

HEADERS = {"X-FTM-Request": "1"}
PASSWORD = "a long test passphrase 123"


@pytest.fixture
def session() -> Iterator[Session]:
    try:
        conn = get_engine().connect()
        conn.execute(text("select id from app_user limit 1"))
        conn.rollback()
    except Exception as exc:
        pytest.skip(f"no migrated Postgres available: {exc.__class__.__name__}")
    transaction = conn.begin()
    s = Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield s
    finally:
        s.close()
        transaction.rollback()
        conn.close()


@pytest.fixture
def clients(session: Session) -> Iterator[tuple[TestClient, TestClient, TestClient]]:
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app, headers=HEADERS) as alice, TestClient(app, headers=HEADERS) as bob, TestClient(app) as guest:
        yield alice, bob, guest


def register(client: TestClient, username: str) -> dict[str, str]:
    r = client.post(
        "/auth/register", json={"username": username, "display_name": username.title(), "password": PASSWORD}
    )
    assert r.status_code == 201, r.text
    assert "password" not in r.text
    assert "HttpOnly" in r.headers["set-cookie"] and "SameSite=lax" in r.headers["set-cookie"]
    return r.json()


def test_account_lifecycle_and_session_revocation(
    session: Session, clients: tuple[TestClient, TestClient, TestClient]
) -> None:
    alice, other_session, guest = clients
    assert guest.get("/auth/me").status_code == 401
    account = register(alice, "alice")
    assert alice.get("/auth/me").json()["id"] == account["id"]
    assert alice.put("/auth/me", json={"display_name": " Alice Farmer "}).json()["display_name"] == "Alice Farmer"
    assert alice.put("/auth/me", json={"display_name": "   "}).status_code == 422
    row = session.get(UserRow, account["id"])
    assert row and row.password_hash != PASSWORD and password_matches(PASSWORD, row.password_hash)
    token = alice.cookies.get(COOKIE)
    stored = session.get(UserSessionRow, token_hash(token))
    assert stored and stored.token_hash != token
    assert other_session.post("/auth/login", json={"username": "ALICE", "password": PASSWORD}).status_code == 200
    assert (
        alice.put(
            "/auth/password", json={"current_password": "wrong", "new_password": "another long passphrase"}
        ).status_code
        == 400
    )
    assert (
        alice.put(
            "/auth/password", json={"current_password": PASSWORD, "new_password": "another long passphrase"}
        ).status_code
        == 204
    )
    assert alice.get("/auth/me").status_code == 200
    assert other_session.get("/auth/me").status_code == 401
    assert alice.post("/auth/logout").status_code == 204
    assert alice.get("/auth/me").status_code == 401
    assert alice.post("/auth/login", json={"username": "alice", "password": PASSWORD}).status_code == 401
    assert (
        alice.post("/auth/login", json={"username": "alice", "password": "another long passphrase"}).status_code == 200
    )
    current = session.get(UserSessionRow, token_hash(alice.cookies.get(COOKIE)))
    assert current
    current.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()
    assert alice.get("/auth/me").status_code == 401


def test_request_protection_duplicates_validation_and_lockout(
    session: Session, clients: tuple[TestClient, TestClient, TestClient]
) -> None:
    alice, bob, guest = clients
    assert guest.post("/auth/register", json={}).status_code == 403
    assert alice.post("/auth/register", json={}, headers={"Origin": "https://evil.example"}).status_code == 403
    invalid = alice.post("/auth/register", json={"username": "alice", "display_name": "Alice", "password": "SECRET"})
    assert invalid.status_code == 422 and "SECRET" not in invalid.text
    register(alice, "alice")
    assert (
        bob.post("/auth/register", json={"username": "ALICE", "display_name": "X", "password": PASSWORD}).status_code
        == 409
    )
    for _ in range(5):
        assert bob.post("/auth/login", json={"username": "alice", "password": "wrong"}).status_code == 401
    assert bob.post("/auth/login", json={"username": "alice", "password": PASSWORD}).status_code == 429
    row = session.scalar(select(UserRow).where(UserRow.username == "alice"))
    assert row
    row.locked_until = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()
    assert bob.post("/auth/login", json={"username": "alice", "password": PASSWORD}).status_code == 200


def test_private_farms_create_list_edit_archive_and_ingestion(
    session: Session, clients: tuple[TestClient, TestClient, TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    alice, bob, guest = clients
    a = register(alice, "alice")
    register(bob, "bob")
    monkeypatch.setattr(site_svc, "_timezone", lambda lat, lon: "UTC")
    monkeypatch.setattr(site_svc, "_load", lambda *args: None)
    req = {"name": "My field", "latitude": 38, "longitude": -100}
    assert guest.post("/sites", headers=HEADERS, json=req).status_code == 401
    ar = alice.post("/sites", json=req)
    br = bob.post("/sites", json=req)
    assert ar.status_code == br.status_code == 202
    aid, bid = ar.json()["site_id"], br.json()["site_id"]
    assert aid != bid  # same coordinates/name cannot attach a second user to an existing private farm
    assert alice.post("/sites", json=req).json()["site_id"] == aid
    assert alice.get(f"/sites/{aid}").json()["owner_user_id"] == a["id"]
    assert aid in {s["id"] for s in alice.get("/sites").json()}
    assert bid not in {s["id"] for s in alice.get("/sites").json()}
    assert guest.get("/sites").status_code == 401
    for path in [
        f"/sites/{aid}",
        f"/sites/{aid}/load",
        f"/sites/{aid}/timeline",
        f"/sites/{aid}/farmer-context",
        f"/journey/{aid}",
        f"/strategies?site_id={aid}",
        f"/runs?site_id={aid}",
        f"/decision-cards?site_id={aid}",
        f"/validations?site_id={aid}",
    ]:
        assert bob.get(path).status_code == 404, path
        assert guest.get(path).status_code == 401, path
    assert bob.put(f"/sites/{aid}", json={"name": "stolen"}).status_code == 404
    assert bob.put(f"/sites/{aid}/farmer-context", json={}).status_code == 404
    assert alice.put(f"/sites/{aid}", json={"name": "Renamed"}).status_code == 409  # still loading
    site_svc._set(aid, status="done")
    assert alice.put(f"/sites/{aid}/farmer-context", json={"soil_confirmed": True}).status_code == 200
    renamed = alice.put(f"/sites/{aid}", json={"name": "Renamed", "archived": True})
    assert renamed.status_code == 200 and renamed.json()["archived"]
    assert aid not in {s["id"] for s in alice.get("/sites").json()}
    assert aid in {s["id"] for s in alice.get("/sites?include_archived=true").json()}
    assert alice.post("/runs", json={"site_id": aid}).status_code == 409
    # A loader cannot reset the owner, confirmed inputs, name or archive flag.
    upsert_site(session, Site(id=aid, name="Loader name", latitude=38, longitude=-100, timezone="UTC"))
    session.flush()
    stored = session.get(SiteRow, aid)
    assert stored and stored.owner_user_id == a["id"] and stored.archived and stored.name == "Renamed"
    assert stored.farmer_context["soil_confirmed"]
    assert alice.put(f"/sites/{aid}", json={"name": "Renamed", "archived": False}).status_code == 200
    assert aid in {s["id"] for s in alice.get("/sites").json()}
    assert alice.post("/runs", json={"site_id": aid}).status_code == 409  # still observe-only, never invent strategies
    # "Try again" after a failed load restarts it instead of returning the stale failure.
    site_svc._set(aid, status="failed")
    retried = alice.post("/sites", json=req)
    assert retried.status_code == 202 and retried.json()["status"] == "queued"
    # After an API restart there is no in-memory job: a farm without stored weather reads as failed, not done,
    # and posting it again restarts the load.
    site_svc._jobs.pop(aid, None)
    assert alice.get(f"/sites/{aid}/load").json()["status"] == "failed"
    assert alice.post("/sites", json=req).json()["status"] == "queued"
    site_svc._jobs.pop(aid, None)
    site_svc._jobs.pop(bid, None)


def test_unowned_farms_are_invisible_and_private_run_downloads_are_protected(
    session: Session, clients: tuple[TestClient, TestClient, TestClient]
) -> None:
    alice, bob, guest = clients
    a = register(alice, "alice")
    register(bob, "bob")
    session.add(SiteRow(id="test-public", name="TEST preset", latitude=38, longitude=-100, timezone="UTC"))
    session.add(SourceRow(id="test-auth-source", provider="TEST", product="TEST", kind="demo", variables=[], units={}))
    session.flush()
    session.add(StrategyRow(id="test-auth-strategy", site_id="test-public", name="TEST", is_baseline=True, seasons=[]))
    session.flush()
    session.add(
        SimulationRunRow(
            id="test-private-run",
            site_id="test-public",
            owner_user_id=a["id"],
            strategy_ids=[],
            mode="irrigation_needed",
            weather_source_id="test-auth-source",
            resampling_method="TEST",
            sample_start=date(2000, 1, 1),
            sample_end=date(2001, 1, 1),
            n_paths=20,
            horizon_years=2,
            seed=1,
            model_version="TEST",
            input_versions={},
            inputs_hash="test",
        )
    )
    session.flush()
    session.add(
        DecisionRecordRow(
            id="test-private-card",
            site_id="test-public",
            run_id="test-private-run",
            chosen_strategy_id="test-auth-strategy",
            reason="private reason",
        )
    )
    session.commit()
    # No shared farms (D14): an unowned farm is invisible to every account, and guests must sign in.
    assert guest.get("/sites/test-public").status_code == 401
    assert "test-public" not in {s["id"] for s in alice.get("/sites?include_archived=true").json()}
    for client in (alice, bob):
        assert client.get("/sites/test-public").status_code == 404
        assert client.get("/strategies?site_id=test-public").status_code == 404
        assert client.put("/sites/test-public", json={"name": "Changed"}).status_code == 404
        assert client.put("/sites/test-public/farmer-context", json={}).status_code == 404
    assert "test-auth-strategy" not in {s["id"] for s in alice.get("/strategies").json()}
    for path in [
        "/runs/test-private-run",
        "/runs/test-private-run/results",
        "/runs/test-private-run/deltas",
        "/runs/test-private-run/replay?years=2000-2001",
        "/decision-cards/test-private-card",
        "/decision-cards/test-private-card.json",
        "/decision-cards/test-private-card.pdf",
    ]:
        assert bob.get(path).status_code == 404, path
        assert guest.get(path).status_code == 401, path
    assert (
        bob.post(
            "/decision-cards",
            json={
                "site_id": "test-public",
                "run_id": "test-private-run",
                "chosen_strategy_id": "test-auth-strategy",
                "reason": "stolen",
            },
        ).status_code
        == 404
    )
    assert bob.get("/sources/test-auth-source").status_code == 404
