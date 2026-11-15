"""REQ-028: one pure validate() decides whether a vehicle message is valid.

Every rule in the spec's REQ-028 table gets a passing and a failing case (AC3).
"""

import pytest

from cloud.quality import validate

KNOWN = {"veh-01", "veh-02", "veh-03"}
NOW_MS = 1_700_000_000_000


def telemetry(**changes):
    msg = {"vehicle_id": "veh-02", "route_id": "B", "trip_id": 3, "ts_ms": NOW_MS - 200, "speed_kmh": 40.0,
           "lat": 43.895, "lon": -78.86, "soc_pct": 80.0, "engine_on": True, "odometer_km": 12000.0,
           "hazard_lights": False, "hazard": None}
    msg.update(changes)
    return msg


def hazard(**changes):
    msg = {"vehicle_id": "veh-02", "route_id": "B", "trip_id": 3, "type": "HARSH_BRAKING", "severity": 2,
           "detail": "x", "lat": 43.895, "lon": -78.86, "speed_kmh": 45.0, "t0_ms": NOW_MS - 100}
    msg.update(changes)
    return msg


def codes(msg, kind="telemetry"):
    return [p.code for p in validate(msg, kind, KNOWN, NOW_MS)]


def test_req_028_valid_messages_have_no_problems():
    assert codes(telemetry()) == []
    assert codes(hazard(), "hazard") == []


def test_req_028_unknown_vehicle():
    assert codes(telemetry(vehicle_id="veh-99")) == ["UNKNOWN_VEHICLE"]
    assert codes(hazard(vehicle_id="veh-99"), "hazard") == ["UNKNOWN_VEHICLE"]


@pytest.mark.parametrize("field", ["vehicle_id", "ts_ms", "trip_id", "speed_kmh", "lat", "lon", "soc_pct", "odometer_km"])
def test_req_028_missing_telemetry_field(field):
    missing = telemetry()
    del missing[field]
    assert "MISSING_FIELD" in codes(missing)
    assert "MISSING_FIELD" in codes(telemetry(**{field: None}))   # null counts as missing


@pytest.mark.parametrize("field", ["vehicle_id", "type", "severity", "t0_ms", "lat", "lon", "trip_id"])
def test_req_028_missing_hazard_field(field):
    assert "MISSING_FIELD" in codes(hazard(**{field: None}), "hazard")


@pytest.mark.parametrize("field, low_ok, high_ok, low_bad, high_bad", [
    ("speed_kmh", 0.0, 250.0, -0.1, 250.1),
    ("soc_pct", 0.0, 100.0, -1.0, 100.5),
    ("lat", 43.85, 43.98, 43.84, 43.99),
    ("lon", -78.95, -78.78, -78.96, -78.77),
])
def test_req_028_out_of_range(field, low_ok, high_ok, low_bad, high_bad):
    assert codes(telemetry(**{field: low_ok})) == []
    assert codes(telemetry(**{field: high_ok})) == []
    assert codes(telemetry(**{field: low_bad})) == ["OUT_OF_RANGE"]
    assert codes(telemetry(**{field: high_bad})) == ["OUT_OF_RANGE"]


def test_req_028_odometer_cannot_be_negative():
    assert codes(telemetry(odometer_km=0.0)) == []
    assert codes(telemetry(odometer_km=-5.0)) == ["OUT_OF_RANGE"]


def test_req_028_a_value_that_is_not_a_number_is_out_of_range():
    assert codes(telemetry(speed_kmh="fast")) == ["OUT_OF_RANGE"]
    assert codes(telemetry(speed_kmh=True)) == ["OUT_OF_RANGE"]   # bool is not a speed


def test_req_028_hazard_location_out_of_range():
    assert codes(hazard(lat=10.0), "hazard") == ["OUT_OF_RANGE"]


def test_req_028_late():
    assert codes(telemetry(ts_ms=NOW_MS - 30_000)) == []          # exactly 30 s old is still on time
    assert codes(telemetry(ts_ms=NOW_MS - 30_001)) == ["LATE"]
    assert codes(telemetry(ts_ms=NOW_MS + 5_000)) == []           # clocks may be up to 5 s apart
    assert codes(telemetry(ts_ms=NOW_MS + 5_001)) == ["LATE"]     # from the future
    assert codes(hazard(t0_ms=NOW_MS - 60_000), "hazard") == ["LATE"]


def test_req_028_reports_every_problem_with_its_field():
    problems = validate(telemetry(speed_kmh=-3.0, lat=None, ts_ms=NOW_MS - 60_000), "telemetry", KNOWN, NOW_MS)
    assert sorted((p.code, p.field) for p in problems) == [
        ("LATE", "ts_ms"), ("MISSING_FIELD", "lat"), ("OUT_OF_RANGE", "speed_kmh")]


def test_req_028_unknown_kind_is_an_error():
    with pytest.raises(ValueError):
        validate(telemetry(), "weather", KNOWN, NOW_MS)
