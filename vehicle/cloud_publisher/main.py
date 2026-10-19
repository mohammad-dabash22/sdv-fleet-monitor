"""CloudPublisher app (class Bridge): sends vehicle data to the cloud.

    telemetry -> fleet/{vehicle_id}/telemetry   on a timer (TELEMETRY_HZ, default 1 per second)
    hazards   -> fleet/{vehicle_id}/hazards     right away, when a new hazard appears

The Detector writes four hazard signals at once, but they can arrive as
separate updates, so the Bridge waits SETTLE_S before sending one complete
hazard event. last_hazard stops the same hazard from being sent twice.

Run one publisher on its own (next phase, inside a container):
    python -m vehicle.cloud_publisher.main

NEXT PHASE: nothing changes here. Set TRANSPORT=zenoh and the session in
vehicle/common/transport.py becomes a real Zenoh session.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from vehicle.common import databroker, transport, vss
from vehicle.common.config import VehicleConfig

TELEMETRY_PATHS = [vss.SPEED, vss.LATITUDE, vss.LONGITUDE, vss.SOC, vss.POWER_STATE,
                   vss.ODOMETER, vss.FLEET_ROUTE_ID, vss.FLEET_TRIP_ID, vss.HAZARD_LIGHTS]
SUBSCRIBED_PATHS = TELEMETRY_PATHS + vss.HAZARD_PATHS


class Bridge:
    SETTLE_S = 0.05

    def __init__(self, session: Any, vehicle: dict, telemetry_hz: float = 1.0) -> None:
        self.session = session
        self.vehicle = vehicle  # {"vehicle_id": ..., "route_id": ...}
        self.telemetry_hz = telemetry_hz
        self.latest: dict[str, Any] = {}
        self.lock = threading.Lock()
        self.last_hazard: tuple | None = None
        self.flush_timer: threading.Timer | None = None

    def snapshot(self) -> dict:
        """The telemetry message (JSON shape shared with the cloud)."""
        with self.lock:
            v = dict(self.latest)
        hazard = v.get(vss.HAZARD_TYPE)
        return {
            "vehicle_id": self.vehicle["vehicle_id"],
            "route_id": v.get(vss.FLEET_ROUTE_ID, self.vehicle["route_id"]),
            "trip_id": v.get(vss.FLEET_TRIP_ID),
            "ts_ms": _now_ms(),
            "speed_kmh": v.get(vss.SPEED),
            "lat": v.get(vss.LATITUDE),
            "lon": v.get(vss.LONGITUDE),
            "soc_pct": v.get(vss.SOC),
            "engine_on": v.get(vss.POWER_STATE) == "ON",
            "odometer_km": v.get(vss.ODOMETER),
            "hazard_lights": bool(v.get(vss.HAZARD_LIGHTS)),
            "hazard": None if hazard in (None, vss.NO_HAZARD) else hazard,
        }

    def on_updates(self, updates: dict) -> None:
        with self.lock:
            for path, dp in updates.items():
                self.latest[path] = dp.value
            hazard_changed = any(p in vss.HAZARD_PATHS for p in updates)
            if hazard_changed:
                if self.flush_timer is not None:
                    self.flush_timer.cancel()
                self.flush_timer = threading.Timer(self.SETTLE_S, self.flush_hazard)
                self.flush_timer.daemon = True
                self.flush_timer.start()

    def skip_active_hazard(self, current: dict) -> None:
        """Do not send a hazard that was already active before this publisher started.

        On (re)start the Databroker hands over its current values, including an old
        hazard. Sending it again would count as a new alert with a stale t0, so the
        latency would show how long the publisher was down, not the network.
        """
        kind, t0 = current.get(vss.HAZARD_TYPE), current.get(vss.HAZARD_DETECTED_AT)
        kind, t0 = getattr(kind, "value", None), getattr(t0, "value", None)
        if kind not in (None, vss.NO_HAZARD) and t0 is not None:
            self.last_hazard = (kind, t0)

    def flush_hazard(self) -> None:
        with self.lock:
            v = dict(self.latest)
        kind, t0 = v.get(vss.HAZARD_TYPE), v.get(vss.HAZARD_DETECTED_AT)
        if kind in (None, vss.NO_HAZARD) or t0 is None:
            return
        if (kind, t0) == self.last_hazard:
            return
        self.last_hazard = (kind, t0)
        event = {
            "vehicle_id": self.vehicle["vehicle_id"],
            "route_id": v.get(vss.FLEET_ROUTE_ID, self.vehicle["route_id"]),
            "type": kind,
            "severity": v.get(vss.HAZARD_SEVERITY, 0),
            "detail": v.get(vss.HAZARD_DETAIL, ""),
            "lat": v.get(vss.LATITUDE),
            "lon": v.get(vss.LONGITUDE),
            "speed_kmh": v.get(vss.SPEED),
            "t0_ms": t0,
        }
        self.session.put(transport.hazards_key(self.vehicle["vehicle_id"]), json.dumps(event))

    def telemetry_loop(self, stop: threading.Event) -> None:
        key = transport.telemetry_key(self.vehicle["vehicle_id"])
        while not stop.wait(1.0 / self.telemetry_hz):
            if self.latest:
                self.session.put(key, json.dumps(self.snapshot()))


def _now_ms() -> int:
    return int(time.time() * 1000)


def run(cfg: VehicleConfig, client: Any, stop: threading.Event, session: Any = None) -> None:
    session = session or transport.open_session(cfg)
    bridge = Bridge(session, {"vehicle_id": cfg.vehicle_id, "route_id": cfg.route_id}, cfg.telemetry_hz)
    threading.Thread(target=bridge.telemetry_loop, args=(stop,), name=f"{cfg.vehicle_id}-telemetry",
                     daemon=True).start()
    bridge.skip_active_hazard(client.get_current_values(vss.HAZARD_PATHS))
    for updates in client.subscribe_current_values(SUBSCRIBED_PATHS):
        if stop.is_set():
            break
        bridge.on_updates(updates)


def main() -> None:
    cfg = VehicleConfig.from_env()
    stop = threading.Event()
    with databroker.connect(cfg) as client:
        try:
            run(cfg, client, stop)
        except KeyboardInterrupt:
            stop.set()


if __name__ == "__main__":
    main()
