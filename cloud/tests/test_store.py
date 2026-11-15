import os

import pytest

from cloud.app.store import Store

# SQLite always; PostgreSQL too when TEST_DATABASE_URL is set (CI starts one).
URLS = ["sqlite:///:memory:"] + ([os.environ["TEST_DATABASE_URL"]] if os.environ.get("TEST_DATABASE_URL") else [])


@pytest.fixture(params=URLS, ids=lambda url: url.split(":")[0])
def store(request):
    s = Store(request.param)
    if s.postgres:
        s._write("TRUNCATE telemetry, alerts, trip_stats, quality_flags RESTART IDENTITY", (), rowcount=True)
    return s


def trip_row(**kw):
    base = {"vehicle_id": "veh-02", "route_id": "B", "trip_id": 2, "started_ms": 1000, "ended_ms": 9000, "samples": 12,
            "distance_km": 2.0, "energy_used_pct": 1.0, "energy_pct_per_km": 0.5, "avg_speed_kmh": 30.0,
            "stop_time_s": 4.0, "hazards": 3, "hazards_per_100km": 150.0}
    base.update(kw)
    return base


def test_req_032_trip_upsert_keeps_one_row_per_trip(store):
    store.upsert_trip_stats(trip_row(), processed_at_ms=10)
    store.upsert_trip_stats(trip_row(hazards=4, hazards_per_100km=200.0), processed_at_ms=20)   # re-fired pane
    store.upsert_trip_stats(trip_row(started_ms=50_000), processed_at_ms=30)   # same trip id after a restart
    rows = sorted(store.trip_stats(), key=lambda r: r["started_ms"])
    assert [(r["started_ms"], r["hazards"], r["processed_at_ms"]) for r in rows] == [(1000, 4, 20), (50_000, 3, 30)]


def test_req_032_route_stats_view_sums_trips(store):
    store.upsert_trip_stats(trip_row(trip_id=2, distance_km=2.0, energy_used_pct=1.0, hazards=3,
                                     avg_speed_kmh=30.0, stop_time_s=4.0), processed_at_ms=10)
    store.upsert_trip_stats(trip_row(trip_id=3, started_ms=2000, distance_km=6.0, energy_used_pct=2.0, hazards=1,
                                     avg_speed_kmh=40.0, stop_time_s=8.0), processed_at_ms=15)
    store.upsert_trip_stats(trip_row(vehicle_id="veh-01", route_id="A", distance_km=10.0, hazards=0),
                            processed_at_ms=12)
    b = next(r for r in store.route_stats() if r["route_id"] == "B")
    assert b["trips"] == 2 and b["distance_km"] == pytest.approx(8.0)
    assert b["energy_pct_per_km"] == pytest.approx(3.0 / 8.0)          # total energy / total km
    assert b["hazards"] == 4 and b["hazards_per_100km"] == pytest.approx(50.0)
    assert b["avg_speed_kmh"] == pytest.approx(35.0) and b["stop_time_s_per_trip"] == pytest.approx(6.0)
    assert b["updated_ms"] == 15


def test_req_032_quality_flag_is_stored_once(store):
    flag = {"id": "abc123", "vehicle_id": "veh-02", "route_id": "B", "kind": "telemetry",
            "problems": "OUT_OF_RANGE", "detail": "speed_kmh=-40 is outside 0.0..250.0", "raw": "{}", "record_ms": 5}
    store.upsert_quality_flag(flag, processed_at_ms=10)
    store.upsert_quality_flag(flag, processed_at_ms=20)                # Pub/Sub redelivery or batch re-run
    assert store.quality_flag_count() == 1
    assert store.quality_flags()[0]["problems"] == "OUT_OF_RANGE"


def test_req_032_store_for_returns_the_registered_store():
    from cloud.app.store import register_store, store_for
    s = Store("sqlite:///:memory:")
    register_store(s, "sqlite:///:memory:")
    assert store_for("sqlite:///:memory:") is s


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




def test_telemetry_history(store):
    s = store
    s.add_telemetry({"vehicle_id": "veh-01", "ts_ms": 5000, "speed_kmh": 30, "engine_on": True})
    assert len(s.history("veh-01", 0)) == 1
    assert s.history("veh-01", 6000) == []
