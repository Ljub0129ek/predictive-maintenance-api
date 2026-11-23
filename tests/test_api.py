"""Test af REST API'et med in-memory lagring (ingen MySQL nødvendig)."""

import pytest
from fastapi.testclient import TestClient

from predictive_maintenance.api.main import create_app
from predictive_maintenance.domain.model import Asset
from predictive_maintenance.infrastructure.memory_repository import InMemoryAssetRepository


TEST_KEY = "test-key"


@pytest.fixture
def client():
    repo = InMemoryAssetRepository(assets=[Asset("WTG-001")])
    app = create_app(repository=repo, api_key=TEST_KEY)
    return TestClient(app, headers={"X-API-Key": TEST_KEY})


def send(client, value, asset_id="WTG-001"):
    return client.post(
        "/api/v1/telemetry",
        json={"asset_id": asset_id, "sensor_type": "vibration", "value": value, "unit": "mm/s"},
    )


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "database": "up"}


def test_normal_value_creates_no_alarm(client):
    body = send(client, 4.0).json()
    assert body["anomaly_detected"] is False
    assert [e["event_type"] for e in body["events"]] == ["SensorTelemetryReceived"]
    assert client.get("/api/v1/alarms").json() == []


def test_high_value_creates_and_stores_alarm(client):
    body = send(client, 8.9).json()
    assert body["anomaly_detected"] is True
    assert body["alarms"][0]["severity"] == "WARNING"
    stored = client.get("/api/v1/alarms", params={"asset_id": "WTG-001"}).json()
    assert len(stored) == 1
    events = [e["event_type"] for e in client.get("/api/v1/events").json()]
    assert events == ["SensorTelemetryReceived", "AnomalyDetected"]


def test_unknown_asset_gives_404(client):
    assert send(client, 4.0, asset_id="UNKNOWN").status_code == 404


def test_invalid_payload_gives_422(client):
    r = client.post("/api/v1/telemetry", json={"asset_id": "WTG-001", "value": "abc"})
    assert r.status_code == 422


def test_negative_vibration_gives_422(client):
    assert send(client, -2.0).status_code == 422


def test_missing_api_key_gives_401(client):
    r = client.post(
        "/api/v1/telemetry",
        json={"asset_id": "WTG-001", "sensor_type": "vibration", "value": 8.9, "unit": "mm/s"},
        headers={"X-API-Key": ""},
    )
    assert r.status_code == 401
    assert client.get("/api/v1/alarms").json() == []  # Ingen alarm blev oprettet


def test_wrong_api_key_gives_401(client):
    r = client.post(
        "/api/v1/telemetry",
        json={"asset_id": "WTG-001", "sensor_type": "vibration", "value": 8.9, "unit": "mm/s"},
        headers={"X-API-Key": "forkert"},
    )
    assert r.status_code == 401


def test_no_key_configured_refuses_all(client):
    app = create_app(repository=InMemoryAssetRepository(assets=[Asset("WTG-001")]), api_key="")
    r = TestClient(app).post(
        "/api/v1/telemetry",
        json={"asset_id": "WTG-001", "sensor_type": "vibration", "value": 4.0, "unit": "mm/s"},
    )
    assert r.status_code == 503


def test_health_needs_no_key():
    app = create_app(repository=InMemoryAssetRepository(assets=[Asset("WTG-001")]), api_key="k")
    assert TestClient(app).get("/health").status_code == 200


@pytest.mark.parametrize("value", [-0.1, 100.1])
def test_vibration_outside_0_to_100_gives_422(client, value):
    assert send(client, value).status_code == 422


def test_rate_limit_gives_429_after_20_calls():
    repo = InMemoryAssetRepository(assets=[Asset("WTG-001")])
    c = TestClient(create_app(repository=repo, api_key=TEST_KEY), headers={"X-API-Key": TEST_KEY})
    codes = [send(c, 4.0).status_code for _ in range(21)]
    assert codes[:20] == [200] * 20
    assert codes[20] == 429


def test_rate_limit_also_counts_wrong_keys():
    repo = InMemoryAssetRepository(assets=[Asset("WTG-001")])
    c = TestClient(create_app(repository=repo, api_key=TEST_KEY, rate_limit_per_minute=3))
    codes = [send(c, 4.0).status_code for _ in range(4)]  # Ingen nøgle sendt
    assert codes == [401, 401, 401, 429]


def test_wrong_key_is_logged_as_warning(client, caplog):
    client.post(
        "/api/v1/telemetry",
        json={"asset_id": "WTG-001", "sensor_type": "vibration", "value": 4.0, "unit": "mm/s"},
        headers={"X-API-Key": "gaet-1234"},
    )
    warnings = [r for r in caplog.records if r.name == "audit" and r.levelname == "WARNING"]
    assert any("Afvist API-nøgle" in r.getMessage() for r in warnings)
    assert all("gaet-1234" not in r.getMessage() for r in caplog.records)  # Nøglen logges aldrig


def test_every_call_is_audit_logged(client, caplog):
    with caplog.at_level("INFO", logger="audit"):
        client.get("/health")
    assert any("path=/health status=200" in r.getMessage() for r in caplog.records)


class BrokenRepository(InMemoryAssetRepository):
    def list_alarms(self, asset_id=None):
        raise RuntimeError("hemmelig intern detalje")


def test_unexpected_error_gives_generic_500():
    c = TestClient(
        create_app(repository=BrokenRepository(assets=[Asset("WTG-001")]), api_key=TEST_KEY),
        raise_server_exceptions=False,
    )
    r = c.get("/api/v1/alarms")
    assert r.status_code == 500
    assert "hemmelig" not in r.text
    assert r.json() == {"detail": "Der skete en intern fejl. Prøv igen senere."}
