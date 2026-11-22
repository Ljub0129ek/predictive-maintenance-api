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
