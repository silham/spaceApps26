from fastapi.testclient import TestClient

from ftm.api.main import app

client = TestClient(app)


def test_health() -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert {"schema_version", "model_version", "demo_mode"} <= body.keys()


def test_unimplemented_endpoints_say_so() -> None:
    assert client.post("/runs").status_code == 501
    assert client.post("/decision-card").status_code == 501
