import os

import pytest

from cloud.app.store import Store

# SQLite always; PostgreSQL too when TEST_DATABASE_URL is set (CI starts one).
URLS = ["sqlite:///:memory:"] + ([os.environ["TEST_DATABASE_URL"]] if os.environ.get("TEST_DATABASE_URL") else [])


@pytest.fixture(params=URLS, ids=lambda url: url.split(":")[0])
def store(request):
    s = Store(request.param)
    if s.postgres:
        s._write("TRUNCATE telemetry, alerts, trips RESTART IDENTITY", (), rowcount=True)
    return s


def alert(**kw):
    base = {"vehicle_id": "veh-02", "vehicle_name": "Van 02", "route_id": "B", "source": "edge",
            "type": "HARSH_BRAKING", "severity": 2, "detail": "x", "lat": 1, "lon": 2,
            "t0_ms": 1000, "ts_ms": 1100, "latency_ms": 100}
    base.update(kw)
    return base


def test_alert_lifecycle(store):
    s = store
    first = s.add_alert(alert())
    assert s.active_alert_count() == 1
    assert s.clear_alerts("veh-02", 2000, "edge", "HARSH_BRAKING") == 1
    second = s.add_alert(alert(ts_ms=2100))
    assert s.ack_alert(second) is True
    assert s.ack_alert(second) is False  # already acked
    statuses = {a["id"]: a["status"] for a in s.recent_alerts()}
    assert statuses == {first: "cleared", second: "acked"}
    assert s.latencies() == [100, 100]


def test_route_summary_joins_trips_and_alerts(store):
    s = store
    s.add_trip({"vehicle_id": "veh-02", "route_id": "B", "trip_id": 2, "distance_km": 8.0,
                "energy_used_pct": 2.5, "hazards": 2})
    s.add_alert(alert())
    s.add_alert(alert(route_id="A"))
    rows = {r["route_id"]: r for r in s.route_summary()}
    assert rows["B"]["trips"] == 1 and rows["B"]["trip_hazards"] == 2 and rows["B"]["hazard_alerts"] == 1
    assert rows["A"]["trips"] == 0 and rows["A"]["hazard_alerts"] == 1


def test_telemetry_history(store):
    s = store
    s.add_telemetry({"vehicle_id": "veh-01", "ts_ms": 5000, "speed_kmh": 30, "engine_on": True})
    assert len(s.history("veh-01", 0)) == 1
    assert s.history("veh-01", 6000) == []
