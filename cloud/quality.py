"""Data quality rules for vehicle messages (spec REQ-028, FR-10, NFR-2). Pure: no I/O, no Beam.

One function, two users, so the rules exist once:
    CloudService (cloud/app)      REJECTS invalid telemetry: it never reaches the twin or the database.
    the Beam pipeline (pipeline)  FLAGS every invalid message in quality_flags, so nothing is lost silently.

Hazard events are never rejected on the live path (a safety alert must reach the operator);
the pipeline flags them instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

# Oshawa area: every route point lies in lat 43.885-43.946, lon -78.915 to -78.818; this adds margin.
LAT_RANGE = (43.85, 43.98)
LON_RANGE = (-78.95, -78.78)
SPEED_RANGE_KMH = (0.0, 250.0)
SOC_RANGE_PCT = (0.0, 100.0)
ODOMETER_MIN_KM = 0.0
LATE_AFTER_MS = 30_000       # older than this when it arrives
FUTURE_LIMIT_MS = 5_000      # clocks may differ by this much

REQUIRED = {
    "telemetry": ("vehicle_id", "ts_ms", "trip_id", "speed_kmh", "lat", "lon", "soc_pct", "odometer_km"),
    "hazard": ("vehicle_id", "type", "severity", "t0_ms", "lat", "lon", "trip_id"),
}
TIME_FIELD = {"telemetry": "ts_ms", "hazard": "t0_ms"}
RANGES = {
    "speed_kmh": SPEED_RANGE_KMH,
    "soc_pct": SOC_RANGE_PCT,
    "lat": LAT_RANGE,
    "lon": LON_RANGE,
    "odometer_km": (ODOMETER_MIN_KM, float("inf")),
}


@dataclass(frozen=True)
class Problem:
    code: str        # UNKNOWN_VEHICLE | MISSING_FIELD | OUT_OF_RANGE | LATE
    field: str
    detail: str


def validate(message: dict[str, Any], kind: str, known_vehicles: Iterable[str], arrival_ms: int) -> list[Problem]:
    """Return every problem with the message; an empty list means it is valid."""
    if kind not in REQUIRED:
        raise ValueError(f"Unknown message kind: {kind!r} (use 'telemetry' or 'hazard')")
    problems: list[Problem] = []

    for name in REQUIRED[kind]:
        if message.get(name) is None:
            problems.append(Problem("MISSING_FIELD", name, f"{name} is missing"))

    vehicle_id = message.get("vehicle_id")
    if vehicle_id is not None and vehicle_id not in set(known_vehicles):
        problems.append(Problem("UNKNOWN_VEHICLE", "vehicle_id", f"{vehicle_id} is not in config/fleet.json"))

    for name, (low, high) in RANGES.items():
        value = message.get(name)
        if value is None:
            continue
        if not _is_number(value):
            problems.append(Problem("OUT_OF_RANGE", name, f"{name}={value!r} is not a number"))
        elif not low <= value <= high:
            problems.append(Problem("OUT_OF_RANGE", name, f"{name}={value} is outside {low}..{high}"))

    time_field = TIME_FIELD[kind]
    sent_ms = message.get(time_field)
    if _is_number(sent_ms):
        age_ms = arrival_ms - sent_ms
        if age_ms > LATE_AFTER_MS:
            problems.append(Problem("LATE", time_field, f"arrived {age_ms / 1000:.1f} s after it was sent"))
        elif -age_ms > FUTURE_LIMIT_MS:
            problems.append(Problem("LATE", time_field, f"sent {-age_ms / 1000:.1f} s in the future"))
    return problems


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
