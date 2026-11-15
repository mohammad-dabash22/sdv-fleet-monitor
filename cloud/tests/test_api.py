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


def test_req_038_health_returns_503_when_database_is_down():
    with TestClient(create_app(CloudConfig(transport="fake"))) as client:
        # A PostgreSQL restart leaves the store's only connection dead; closing it does the same.
        client.app.state.service.store.db.close()
        res = client.get("/api/health")
        assert res.status_code == 503
        body = res.json()
        assert body["status"] == "error"
        assert "closed" in body["reason"].lower()   # sqlite3: "Cannot operate on a closed database."


def test_req_038_health_ok_when_database_answers():
    with TestClient(create_app(CloudConfig(transport="fake"))) as client:
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok" and res.json()["database"] == "sqlite"


def now_ms():
    return int(time.time() * 1000)


def test_req_029_invalid_telemetry_is_not_stored():
    with TestClient(create_app(CloudConfig(transport="fake"))) as client:
        bus = fake_zenoh.open()
        good = {"vehicle_id": "veh-01", "route_id": "A", "trip_id": 1, "ts_ms": now_ms(), "speed_kmh": 33,
                "lat": 43.9, "lon": -78.9, "soc_pct": 80, "engine_on": True, "odometer_km": 10}
        bus.put("fleet/veh-01/telemetry", json.dumps({**good, "speed_kmh": -40}))
        bus.put("fleet/veh-01/telemetry", json.dumps({**good, "ts_ms": now_ms() + 1}))
        assert wait_for(lambda: len(client.get("/api/history/veh-01").json()) >= 1)
        time.sleep(0.1)
        rows = client.get("/api/history/veh-01").json()
        assert [r["speed_kmh"] for r in rows] == [33]


def test_req_009_malformed_json_is_ignored(capfd):
    with TestClient(create_app(CloudConfig(transport="fake"))) as client:
        bus = fake_zenoh.open()
        bus.put("fleet/veh-02/hazards", "not json")
        bus.put("fleet/veh-02/hazards", "[1, 2]")             # valid JSON, but not an object
        event = {"vehicle_id": "veh-02", "route_id": "B", "type": "TRACTION_LOSS", "severity": 3,
                 "detail": "TCS", "lat": 43.9, "lon": -78.8, "t0_ms": now_ms()}
        bus.put("fleet/veh-02/hazards", json.dumps(event))
        assert wait_for(lambda: client.get("/api/alerts").json()["active"] == 1)
    # The fake bus catches handler crashes and prints them; real Zenoh may not, so none is allowed.
    assert "handler error" not in capfd.readouterr().out


TRIP = {"vehicle_id": "veh-02", "route_id": "B", "trip_id": 2, "started_ms": 1000, "ended_ms": 9000, "samples": 12,
        "distance_km": 2.0, "energy_used_pct": 1.0, "energy_pct_per_km": 0.5, "avg_speed_kmh": 30.0,
        "stop_time_s": 4.0, "hazards": 3, "hazards_per_100km": 150.0}


def test_req_034_routes_read_route_stats():
    with TestClient(create_app(CloudConfig(transport="fake"))) as client:
        client.app.state.service.store.upsert_trip_stats(TRIP, processed_at_ms=12345)
        body = client.get("/api/routes").json()
        routes = {r["route_id"]: r for r in body["routes"]}
        assert sorted(routes) == ["A", "B", "C"]                 # every route in config/fleet.json
        b = routes["B"]
        assert b["name"].startswith("Route B") and b["trips"] == 1
        assert b["distance_km"] == 2.0 and b["energy_pct_per_km"] == 0.5 and b["avg_speed_kmh"] == 30.0
        assert b["stop_time_s_per_trip"] == 4.0 and b["hazards_per_100km"] == 150.0
        assert routes["A"]["trips"] == 0 and routes["A"]["hazards_per_100km"] is None
        assert body["updated_ms"] == 12345


def test_req_034_trips_read_trip_stats():
    with TestClient(create_app(CloudConfig(transport="fake"))) as client:
        client.app.state.service.store.upsert_trip_stats(TRIP, processed_at_ms=1)
        (trip,) = client.get("/api/trips").json()
        assert trip["trip_id"] == 2 and trip["hazards"] == 3


def test_req_034_flagged_count_and_pipeline_status():
    with TestClient(create_app(CloudConfig(transport="fake"))) as client:
        client.app.state.service.store.upsert_quality_flag(
            {"id": "x1", "kind": "telemetry", "problems": "LATE", "raw": "{}"}, processed_at_ms=1)
        body = client.get("/api/routes").json()
        assert body["flagged_records"] == 1
        assert body["pipeline"]["mode"] == "external"            # cloud.app.main on GKE: Dataflow writes the tables
        client.app.state.pipeline = None                         # run_demo.py in the Kuksa venv: no Beam
        assert client.get("/api/routes").json()["pipeline"] == {"installed": False, "mode": None}


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
            # ts_ms must be recent: since REQ-029 a 1970 timestamp is LATE and rejected.
            msg = {"vehicle_id": "veh-01", "route_id": "A", "trip_id": 1, "ts_ms": now_ms(), "speed_kmh": 33,
                   "lat": 43.9, "lon": -78.9, "soc_pct": 80, "engine_on": True, "odometer_km": 10}
            fake_zenoh.open().put("fleet/veh-01/telemetry", json.dumps(msg))
            ev = ws.receive_json()
            assert ev["kind"] == "twin" and ev["data"]["telemetry"]["speed_kmh"] == 33
