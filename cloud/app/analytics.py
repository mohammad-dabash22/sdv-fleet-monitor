"""Cloud domain logic: digital twins and cloud-side alerts. No I/O at all.

FleetAnalytics takes messages in and returns a list of EVENTS out. It never
writes to the database or the network; CloudService (main.py) does that.
This is why every rule here can be unit tested with plain dicts.

Event kinds returned:
    {"kind": "telemetry", "data": msg}       store the raw telemetry
    {"kind": "twin",      "data": twin}      push the twin to the dashboard
    {"kind": "alert",     "data": alert}     store + push a new alert
    {"kind": "clear",     "vehicle_id", "source", "type"}   auto-resolve old alerts

Telemetry that fails the quality checks (cloud/quality.py) is rejected here (REQ-029).
Trip and route numbers are not computed here: the Beam pipeline owns them (cloud/pipeline,
spec D-5). More anomaly detection (FR-11) is V2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cloud.quality import validate

ENERGY_DROP_PCT = 3.0       # one sample dropping more than this is suspicious


@dataclass
class Twin:
    vehicle_id: str
    name: str
    powertrain: str
    route_id: str
    route_name: str = ""
    telemetry: dict = field(default_factory=dict)
    last_seen: float = 0.0
    online: bool = False
    hazard: dict | None = None
    last_soc: float | None = None     # for the ENERGY_DROP rule

    def as_dict(self) -> dict:
        return {
            "vehicle_id": self.vehicle_id,
            "name": self.name,
            "powertrain": self.powertrain,
            "route_id": self.route_id,
            "route_name": self.route_name,
            "telemetry": self.telemetry,
            "last_seen_ms": int(self.last_seen * 1000) if self.last_seen else None,
            "online": self.online,
            "hazard": self.hazard,
        }


class FleetAnalytics:
    def __init__(self, fleet: dict, offline_after_s: float = 10.0) -> None:
        self.routes: dict[str, dict] = fleet.get("routes", {})
        self.vehicles: dict[str, dict] = {v["vehicle_id"]: v for v in fleet.get("vehicles", [])}
        self.offline_after_s = offline_after_s
        self.twins: dict[str, Twin] = {
            vid: Twin(vid, v["name"], v.get("powertrain", ""), v["route_id"],
                      self.routes.get(v["route_id"], {}).get("name", v["route_id"]))
            for vid, v in self.vehicles.items()
        }

    # ------------------------------------------------------------------ inputs
    def ingest_telemetry(self, msg: dict, now: float) -> list[dict]:
        twin = self.twins.get(msg.get("vehicle_id", ""))
        if twin is None:
            return []  # unknown vehicle: discard (activity diagram, first decision)
        if validate(msg, "telemetry", self.vehicles, int(now * 1000)):
            return []  # invalid: not stored, twin unchanged; the pipeline flags it (REQ-029)

        events: list[dict] = [{"kind": "telemetry", "data": msg}]
        if not twin.online:
            events.append({"kind": "clear", "vehicle_id": twin.vehicle_id, "source": "cloud", "type": "OFFLINE"})
        twin.telemetry = {k: msg.get(k) for k in
                          ("speed_kmh", "lat", "lon", "soc_pct", "engine_on", "odometer_km", "trip_id", "hazard_lights")}
        twin.route_id = msg.get("route_id") or twin.route_id
        twin.last_seen = now
        twin.online = True
        if not msg.get("hazard"):
            twin.hazard = None

        events += self._track_energy(twin, msg, now)
        events.append({"kind": "twin", "data": twin.as_dict()})
        return events

    def ingest_hazard(self, msg: dict, now: float) -> list[dict]:
        twin = self.twins.get(msg.get("vehicle_id", ""))
        if twin is None:
            return []
        t1_ms = int(now * 1000)  # t1: the moment the hazard arrives in the cloud
        t0_ms = msg.get("t0_ms")
        twin.hazard = {"type": msg.get("type"), "severity": msg.get("severity", 0),
                       "detail": msg.get("detail", ""), "t0_ms": t0_ms}
        alert = {
            "vehicle_id": twin.vehicle_id,
            "vehicle_name": twin.name,
            "route_id": msg.get("route_id") or twin.route_id,
            "source": "edge",
            "type": msg.get("type"),
            "severity": int(msg.get("severity") or 0),
            "detail": msg.get("detail", ""),
            "lat": msg.get("lat"),
            "lon": msg.get("lon"),
            "t0_ms": t0_ms,
            "ts_ms": t1_ms,
            "latency_ms": (t1_ms - t0_ms) if t0_ms else None,
        }
        return [{"kind": "alert", "data": alert}, {"kind": "twin", "data": twin.as_dict()}]

    def check_offline(self, now: float) -> list[dict]:
        events: list[dict] = []
        for twin in self.twins.values():
            if twin.online and now - twin.last_seen > self.offline_after_s:
                twin.online = False
                events.append({"kind": "alert", "data": self._cloud_alert(
                    twin, "OFFLINE", 2, f"No data for {self.offline_after_s:.0f} s", now)})
                events.append({"kind": "twin", "data": twin.as_dict()})
        return events

    # ---------------------------------------------------------------- helpers
    def snapshot(self) -> list[dict]:
        return [t.as_dict() for t in self.twins.values()]

    def _cloud_alert(self, twin: Twin, kind: str, severity: int, detail: str, now: float) -> dict:
        return {
            "vehicle_id": twin.vehicle_id, "vehicle_name": twin.name, "route_id": twin.route_id,
            "source": "cloud", "type": kind, "severity": severity, "detail": detail,
            "lat": twin.telemetry.get("lat"), "lon": twin.telemetry.get("lon"),
            "t0_ms": None, "ts_ms": int(now * 1000), "latency_ms": None,
        }

    def _track_energy(self, twin: Twin, msg: dict, now: float) -> list[dict]:
        """ENERGY_DROP: the battery fell more than ENERGY_DROP_PCT in one sample. Uses the twin's last
        value, not the trip tracker's, so the rule survives when trip tracking moves to Beam (REQ-013)."""
        soc, last = msg.get("soc_pct"), twin.last_soc
        events: list[dict] = []
        if soc is not None and last is not None:
            drop = last - soc        # a jump up means the van was charged: that is not a drop
            if drop > ENERGY_DROP_PCT:
                events.append({"kind": "alert", "data": self._cloud_alert(
                    twin, "ENERGY_DROP", 2, f"Battery fell {drop:.1f}% in one sample", now)})
        if soc is not None:
            twin.last_soc = soc
        return events



def latency_stats(values: list[float], target_ms: float = 2000.0) -> dict:
    """Median, 95th percentile (nearest rank) and max of hazard latencies."""
    vals = sorted(v for v in values if v is not None)
    n = len(vals)
    if n == 0:
        return {"count": 0, "median_ms": None, "p95_ms": None, "max_ms": None,
                "target_ms": target_ms, "within_target_pct": None, "pass": None}
    mid = n // 2
    median = vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2
    p95 = vals[max(0, -(-95 * n // 100) - 1)]
    within = sum(1 for v in vals if v < target_ms) * 100 / n
    return {"count": n, "median_ms": round(median, 1), "p95_ms": round(p95, 1), "max_ms": round(vals[-1], 1),
            "target_ms": target_ms, "within_target_pct": round(within, 1), "pass": p95 < target_ms}
