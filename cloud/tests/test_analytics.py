from cloud.app.analytics import FleetAnalytics, latency_stats

FLEET = {
    "routes": {"B": {"name": "Route B", "speed_limit_kmh": 50}},
    "vehicles": [{"vehicle_id": "veh-02", "name": "Van 02", "route_id": "B", "powertrain": "BEV"}],
}


def telemetry(trip=1, odo=100.0, soc=80.0, hazard=None):
    return {"vehicle_id": "veh-02", "route_id": "B", "trip_id": trip, "ts_ms": 0, "speed_kmh": 40,
            "lat": 43.9, "lon": -78.8, "soc_pct": soc, "engine_on": True, "odometer_km": odo, "hazard": hazard}


def kinds(events):
    return [e["kind"] for e in events]


def test_unknown_vehicle_is_discarded():
    fa = FleetAnalytics(FLEET)
    assert fa.ingest_telemetry({"vehicle_id": "nope"}, 1.0) == []
    assert fa.ingest_hazard({"vehicle_id": "nope"}, 1.0) == []


def test_telemetry_updates_twin():
    fa = FleetAnalytics(FLEET)
    events = fa.ingest_telemetry(telemetry(), 10.0)
    assert "telemetry" in kinds(events) and "twin" in kinds(events)
    twin = fa.twins["veh-02"]
    assert twin.online and twin.telemetry["speed_kmh"] == 40


def test_hazard_creates_alert_with_latency():
    fa = FleetAnalytics(FLEET)
    events = fa.ingest_hazard({"vehicle_id": "veh-02", "route_id": "B", "type": "TRACTION_LOSS",
                               "severity": 3, "detail": "x", "t0_ms": 10_000}, 10.25)
    alert = events[0]["data"]
    assert alert["latency_ms"] == 250 and alert["source"] == "edge" and alert["route_id"] == "B"
    assert fa.twins["veh-02"].hazard["type"] == "TRACTION_LOSS"


def test_trip_result_after_first_full_trip():
    fa = FleetAnalytics(FLEET)
    fa.ingest_telemetry(telemetry(trip=1, odo=100), 1.0)        # we join mid-trip: partial
    assert "trip" not in kinds(fa.ingest_telemetry(telemetry(trip=2, odo=105), 2.0))
    fa.ingest_hazard({"vehicle_id": "veh-02", "type": "HARSH_BRAKING", "severity": 2, "t0_ms": 2900}, 3.0)
    fa.ingest_telemetry(telemetry(trip=2, odo=108, soc=78), 4.0)
    events = fa.ingest_telemetry(telemetry(trip=3, odo=115, soc=77), 5.0)
    trip = next(e["data"] for e in events if e["kind"] == "trip")
    assert trip["distance_km"] == 10 and trip["hazards"] == 1 and trip["hazards_per_100km"] == 10.0
    assert trip["energy_used_pct"] == 3.0


def test_req_029_invalid_telemetry_does_not_update_twin():
    fa = FleetAnalytics(FLEET)
    fa.ingest_telemetry(telemetry(), 10.0)
    bad = {**telemetry(), "speed_kmh": -40}
    assert fa.ingest_telemetry(bad, 11.0) == []          # no telemetry event = nothing is stored
    assert fa.twins["veh-02"].telemetry["speed_kmh"] == 40


def test_req_029_hazard_with_problem_still_alerts():
    fa = FleetAnalytics(FLEET)
    events = fa.ingest_hazard({"vehicle_id": "veh-02", "route_id": "B", "type": "TRACTION_LOSS", "severity": 3,
                               "detail": "x", "lat": None, "lon": None, "t0_ms": 10_000}, 10.25)
    assert events[0]["kind"] == "alert" and events[0]["data"]["type"] == "TRACTION_LOSS"


def test_req_029_partial_message_then_full_message():
    fa = FleetAnalytics(FLEET)
    partial = {**telemetry(), "lat": None, "lon": None, "soc_pct": None}   # a publisher that just started
    assert fa.ingest_telemetry(partial, 1.0) == []
    assert not fa.twins["veh-02"].online
    assert "twin" in kinds(fa.ingest_telemetry(telemetry(), 2.0))
    assert fa.twins["veh-02"].online


def test_req_013_energy_drop_alert():
    fa = FleetAnalytics(FLEET)
    fa.ingest_telemetry(telemetry(soc=80.0), 1.0)
    assert "alert" not in kinds(fa.ingest_telemetry(telemetry(soc=78.0), 2.0))     # 2 % in one sample: normal
    events = fa.ingest_telemetry(telemetry(soc=74.0), 3.0)                          # 4 % in one sample
    alert = next(e["data"] for e in events if e["kind"] == "alert")
    assert alert["type"] == "ENERGY_DROP" and alert["source"] == "cloud"
    assert "alert" not in kinds(fa.ingest_telemetry(telemetry(soc=100.0), 4.0))    # charging is not a drop


def test_offline_then_back_online():
    fa = FleetAnalytics(FLEET, offline_after_s=5)
    fa.ingest_telemetry(telemetry(), 1.0)
    events = fa.check_offline(10.0)
    assert events[0]["data"]["type"] == "OFFLINE"
    assert not fa.twins["veh-02"].online
    assert "clear" in kinds(fa.ingest_telemetry(telemetry(), 11.0))


def test_latency_stats():
    s = latency_stats(list(range(1, 101)))
    assert s["count"] == 100 and s["median_ms"] == 50.5 and s["p95_ms"] == 95 and s["max_ms"] == 100
    assert s["pass"] is True
    assert latency_stats([])["count"] == 0
