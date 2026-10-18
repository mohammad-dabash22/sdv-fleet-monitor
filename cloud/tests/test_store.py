from cloud.app.store import Store


def alert(**kw):
    base = {"vehicle_id": "veh-02", "vehicle_name": "Van 02", "route_id": "B", "source": "edge",
            "type": "HARSH_BRAKING", "severity": 2, "detail": "x", "lat": 1, "lon": 2,
            "t0_ms": 1000, "ts_ms": 1100, "latency_ms": 100}
    base.update(kw)
    return base


def test_alert_lifecycle():
    s = Store()
    first = s.add_alert(alert())
    assert s.active_alert_count() == 1
    assert s.clear_alerts("veh-02", 2000, "edge", "HARSH_BRAKING") == 1
    second = s.add_alert(alert(ts_ms=2100))
    assert s.ack_alert(second) is True
    assert s.ack_alert(second) is False  # already acked
    statuses = {a["id"]: a["status"] for a in s.recent_alerts()}
    assert statuses == {first: "cleared", second: "acked"}
    assert s.latencies() == [100, 100]


def test_route_summary_joins_trips_and_alerts():
    s = Store()
    s.add_trip({"vehicle_id": "veh-02", "route_id": "B", "trip_id": 2, "distance_km": 8.0,
                "energy_used_pct": 2.5, "hazards": 2})
    s.add_alert(alert())
    s.add_alert(alert(route_id="A"))
    rows = {r["route_id"]: r for r in s.route_summary()}
    assert rows["B"]["trips"] == 1 and rows["B"]["trip_hazards"] == 2 and rows["B"]["hazard_alerts"] == 1
    assert rows["A"]["trips"] == 0 and rows["A"]["hazard_alerts"] == 1


def test_telemetry_history():
    s = Store()
    s.add_telemetry({"vehicle_id": "veh-01", "ts_ms": 5000, "speed_kmh": 30, "engine_on": True})
    assert len(s.history("veh-01", 0)) == 1
    assert s.history("veh-01", 6000) == []
