"""Route shapes and driving profiles for the simulated vans (Oshawa, Ontario).

Each route is a closed loop that starts and ends at the depot. One loop is
one trip. The points are approximate; they only need to look right on a map.

NEXT PHASE (optional): replace the points with real road geometry, or replay
recorded drives instead of generating them.
"""

from __future__ import annotations

import math

DEPOT = (43.9050, -78.8720)

ROUTES: dict[str, list[tuple[float, float]]] = {
    "A": [DEPOT, (43.9150, -78.8770), (43.9300, -78.8850), (43.9440, -78.8930),
          (43.9460, -78.9050), (43.9380, -78.9150), (43.9230, -78.9060), (43.9100, -78.8920)],
    "B": [DEPOT, (43.8990, -78.8660), (43.8975, -78.8540), (43.8945, -78.8400),
          (43.8870, -78.8380), (43.8850, -78.8530), (43.8890, -78.8680), (43.8970, -78.8800)],
    "C": [DEPOT, (43.9090, -78.8560), (43.9160, -78.8420), (43.9280, -78.8310),
          (43.9210, -78.8180), (43.9080, -78.8230), (43.9010, -78.8400), (43.9020, -78.8580)],
}

# Chance per simulator tick (0.5 s) of each event, plus energy use factor.
# Route B is stop-and-go downtown, so it has the most hazards (Maria's scenario).
PROFILES: dict[str, dict[str, float]] = {
    "A": {"harsh": 0.004, "traction": 0.002, "overspeed": 0.002, "energy_factor": 1.0},
    "B": {"harsh": 0.030, "traction": 0.012, "overspeed": 0.001, "energy_factor": 1.3},
    "C": {"harsh": 0.006, "traction": 0.003, "overspeed": 0.006, "energy_factor": 1.1},
}


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def loop_segments(points: list[tuple[float, float]]) -> list[tuple[tuple[float, float], tuple[float, float], float]]:
    closed = points + [points[0]]
    return [(closed[i], closed[i + 1], haversine_km(closed[i], closed[i + 1])) for i in range(len(points))]


def loop_length_km(points: list[tuple[float, float]]) -> float:
    return sum(seg[2] for seg in loop_segments(points))


def position_at(points: list[tuple[float, float]], dist_km: float) -> tuple[float, float]:
    """Point on the loop after driving dist_km from the start."""
    segments = loop_segments(points)
    dist_km %= sum(s[2] for s in segments)
    for a, b, length in segments:
        if dist_km <= length:
            r = dist_km / length if length else 0.0
            return a[0] + (b[0] - a[0]) * r, a[1] + (b[1] - a[1]) * r
        dist_km -= length
    return points[0]
