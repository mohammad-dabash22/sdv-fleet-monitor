"""Trip efficiency and safety (spec REQ-031, FR-12). Pure: no Beam, no I/O.

The Beam pipeline groups valid messages per van and calls trips(); the tests call it directly.
Route numbers are not computed here: the route_stats view sums these trip rows (REQ-032).
"""

from __future__ import annotations

from collections import defaultdict
from itertools import groupby

STOPPED_BELOW_KMH = 2.0


def trips(telemetry: list[dict], hazards: list[dict]) -> list[dict]:
    """One result per completed trip, for every van in the input.

    Only trips seen from start to end count: for each van the first trip seen (we may have joined
    it halfway) and the trip still in progress (the highest trip id) are left out.
    """
    by_van: dict[str, list[dict]] = defaultdict(list)
    for record in telemetry:
        by_van[record["vehicle_id"]].append(record)
    hazard_count: dict[tuple, int] = defaultdict(int)
    for hazard in hazards:
        hazard_count[(hazard["vehicle_id"], hazard.get("trip_id"))] += 1

    results = []
    for vehicle_id, records in sorted(by_van.items()):
        records.sort(key=lambda r: r["ts_ms"])
        trip_ids = sorted({r["trip_id"] for r in records})
        complete = set(trip_ids[1:-1])
        by_trip = {k: list(g) for k, g in groupby(sorted(records, key=lambda r: (r["trip_id"], r["ts_ms"])),
                                                   key=lambda r: r["trip_id"])}
        for trip_id in sorted(complete):
            results.append(_trip(vehicle_id, trip_id, by_trip[trip_id], hazard_count[(vehicle_id, trip_id)]))
    return results


def _trip(vehicle_id: str, trip_id: int, records: list[dict], hazards: int) -> dict:
    first, last = records[0], records[-1]
    distance = last["odometer_km"] - first["odometer_km"]
    energy = sum(max(0.0, a["soc_pct"] - b["soc_pct"]) for a, b in zip(records, records[1:]))  # rises = charging
    stopped_ms = sum(b["ts_ms"] - a["ts_ms"] for a, b in zip(records, records[1:])
                     if a["speed_kmh"] < STOPPED_BELOW_KMH)
    return {
        "vehicle_id": vehicle_id,
        "route_id": last.get("route_id"),
        "trip_id": trip_id,
        "started_ms": first["ts_ms"],
        "ended_ms": last["ts_ms"],
        "samples": len(records),
        "distance_km": distance,
        "energy_used_pct": energy,
        "energy_pct_per_km": energy / distance if distance > 0 else None,
        "avg_speed_kmh": sum(r["speed_kmh"] for r in records) / len(records),
        "stop_time_s": stopped_ms / 1000,
        "hazards": hazards,
        "hazards_per_100km": hazards * 100 / distance if distance > 0 else None,
    }
