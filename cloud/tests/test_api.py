import json
import time

from fastapi.testclient import TestClient

from cloud.app.config import CloudConfig
from cloud.app.main import create_app
from fakes import zenoh as fake_zenoh


def wait_for(cond, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end and not cond():
        time.sleep(0.02)
    return cond()


def test_health_and_fleet():
    with TestClient(create_app(CloudConfig(transport="fake"))) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        assert len(client.get("/api/fleet").json()) == 3
        assert client.get("/").status_code == 200


def test_hazard_flows_to_alerts_and_can_be_acked():
    with TestClient(create_app(CloudConfig(transport="fake"))) as client:
        bus = fake_zenoh.open()
        event = {"vehicle_id": "veh-02", "route_id": "B", "type": "TRACTION_LOSS", "severity": 3,
                 "detail": "TCS", "lat": 43.9, "lon": -78.8, "t0_ms": int(time.time() * 1000)}
        bus.put("fleet/veh-02/hazards", json.dumps(event))
        assert wait_for(lambda: client.get("/api/alerts").json()["active"] == 1)
        alert = client.get("/api/alerts").json()["items"][0]
        assert alert["type"] == "TRACTION_LOSS" and alert["latency_ms"] is not None
        assert client.post(f"/api/alerts/{alert['id']}/ack").json()["ok"]
        assert client.get("/api/alerts").json()["active"] == 0
        assert client.post("/api/alerts/9999/ack").status_code == 404
        assert client.get("/api/latency").json()["count"] == 1


def test_websocket_sends_snapshot_then_live_twin():
    with TestClient(create_app(CloudConfig(transport="fake"))) as client:
        with client.websocket_connect("/ws") as ws:
            first = ws.receive_json()
            assert first["kind"] == "snapshot" and len(first["fleet"]) == 3
            msg = {"vehicle_id": "veh-01", "route_id": "A", "trip_id": 1, "ts_ms": 1, "speed_kmh": 33,
                   "lat": 43.9, "lon": -78.9, "soc_pct": 80, "engine_on": True, "odometer_km": 10}
            fake_zenoh.open().put("fleet/veh-01/telemetry", json.dumps(msg))
            ev = ws.receive_json()
            assert ev["kind"] == "twin" and ev["data"]["telemetry"]["speed_kmh"] == 33
