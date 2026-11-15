"""REQ-031: trip efficiency and safety, as a pure function (no Beam), with hand-computed answers."""

import pytest

from cloud.pipeline.metrics import trips
from cloud.pipeline.samples import SAMPLE_FILE, load_samples

NOW_MS = 1_700_000_000_000


def valid_sample(vehicle_id):
    samples = [s for s in load_samples(SAMPLE_FILE, NOW_MS) if not s.expect and s.message["vehicle_id"] == vehicle_id]
    return ([s.message for s in samples if s.kind == "telemetry"],
            [s.message for s in samples if s.kind == "hazard"])


def rec(t_s, trip, speed, odo, soc, vid="veh-02"):
    return {"vehicle_id": vid, "route_id": "B", "trip_id": trip, "ts_ms": int(t_s * 1000),
            "speed_kmh": speed, "odometer_km": odo, "soc_pct": soc}


def test_req_031_sample_trip_matches_hand_computed_values():
    telemetry, hazards = valid_sample("veh-02")
    (trip,) = trips(telemetry, hazards)      # trip 1 is the first seen, trip 3 is in progress
    assert trip["vehicle_id"] == "veh-02" and trip["route_id"] == "B" and trip["trip_id"] == 2
    assert trip["started_ms"] == NOW_MS - 23_000 and trip["ended_ms"] == NOW_MS - 12_000
    assert trip["distance_km"] == pytest.approx(1.00)
    assert trip["energy_used_pct"] == pytest.approx(0.9)
    assert trip["energy_pct_per_km"] == pytest.approx(0.9)
    assert trip["avg_speed_kmh"] == pytest.approx(316 / 12)
    assert trip["stop_time_s"] == pytest.approx(3.0)
    assert trip["hazards"] == 2 and trip["hazards_per_100km"] == pytest.approx(200.0)
    assert trip["samples"] == 12


def test_req_031_first_trip_seen_and_trip_in_progress_are_left_out():
    records = [rec(t, trip, 40, 100 + t / 10, 80) for trip, ts in ((7, (0, 1)), (8, (2, 3, 4)), (9, (5, 6))) for t in ts]
    assert [t["trip_id"] for t in trips(records, [])] == [8]
    assert trips([r for r in records if r["trip_id"] in (8, 9)], []) == []     # trip 8 is now the first seen


def test_req_031_charging_is_not_energy_used():
    records = [rec(0, 1, 40, 0.0, 50), rec(1, 2, 40, 1.0, 50), rec(2, 2, 40, 2.0, 49),
               rec(3, 2, 40, 3.0, 95), rec(4, 2, 40, 4.0, 94), rec(5, 3, 40, 5.0, 94)]
    (trip,) = trips(records, [])
    assert trip["energy_used_pct"] == pytest.approx(2.0)                       # 50->49 and 95->94; 49->95 is charging
    assert trip["energy_pct_per_km"] == pytest.approx(2.0 / 3.0)


def test_req_031_records_out_of_order_are_sorted_by_time():
    records = [rec(0, 1, 40, 0.0, 50), rec(3, 2, 0, 3.0, 49), rec(1, 2, 40, 1.0, 50), rec(2, 2, 1, 2.0, 49.5),
               rec(4, 3, 40, 4.0, 49)]
    (trip,) = trips(records, [])
    assert trip["distance_km"] == pytest.approx(2.0)
    assert trip["stop_time_s"] == pytest.approx(1.0)   # only t=2 s; the last record of a trip has no interval


def test_req_031_zero_distance_trip_has_no_rates():
    records = [rec(0, 1, 0, 5.0, 50), rec(1, 2, 0, 5.0, 50), rec(2, 2, 0, 5.0, 50), rec(3, 3, 0, 5.0, 50)]
    (trip,) = trips(records, [])
    assert trip["distance_km"] == 0 and trip["energy_pct_per_km"] is None and trip["hazards_per_100km"] is None


def test_req_031_no_records_no_trips():
    assert trips([], []) == []
