"""HazardDetector app: reads signals from the Databroker, finds hazards, writes them back.

Flow (see the UML sequence diagram):
    Databroker update -> on_updates() -> frame settles -> step() runs the rules
    -> the most severe Finding is written back as Vehicle.Hazard.* (t0 is set here)

A short hold window (HOLD_S) stops a hazard from flickering on and off.

Run one detector on its own (next phase, inside a container):
    python -m vehicle.hazard_detector.main

NEXT PHASE: wrap this class in a Velocitas VehicleApp (the charter says the
detector is a Velocitas app). The rules (vehicle/hazard_rules) and this class
stay the same; Velocitas only replaces how we subscribe and write signals.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from vehicle.common import databroker, vss
from vehicle.common.config import VehicleConfig
from vehicle.hazard_rules import Finding, Thresholds, evaluate, most_severe
from vehicle.hazard_rules.rules import CRITICAL

INPUT_PATHS = [vss.SPEED, vss.ACCEL_LONG, vss.TCS_ENGAGED, vss.SOC, vss.COOLANT_TEMP]

# VSS path -> short name used by hazard_rules
FRAME_KEYS = {
    vss.SPEED: "speed_kmh",
    vss.ACCEL_LONG: "accel_mps2",
    vss.TCS_ENGAGED: "tcs_active",
    vss.SOC: "soc_pct",
    vss.COOLANT_TEMP: "coolant_c",
}


class Detector:
    SETTLE_S = 0.05   # wait this long after the last update before evaluating
    HOLD_S = 1.5      # keep a hazard active at least this long

    def __init__(self, client: Any, thresholds: Thresholds, datapoint: type,
                 clock: Callable[[], float] = time.monotonic,
                 wall_ms: Callable[[], int] = lambda: int(time.time() * 1000)) -> None:
        self.client = client
        self.thresholds = thresholds
        self.Datapoint = datapoint
        self.clock = clock
        self.wall_ms = wall_ms
        self.state: dict[str, Any] = {}
        self.lock = threading.Lock()
        self.last_update = 0.0
        self.dirty = False
        self.held_until = 0.0
        self.current: Finding | None = None

    def on_updates(self, updates: dict) -> None:
        with self.lock:
            for path, dp in updates.items():
                self.state[path] = dp.value
            self.dirty = True
            self.last_update = self.clock()

    def step(self) -> None:
        """Evaluate the rules once the frame has settled. Call this often."""
        now = self.clock()
        with self.lock:
            settled = self.dirty and now - self.last_update >= self.SETTLE_S
            if settled:
                self.dirty = False
                frame = {FRAME_KEYS[p]: v for p, v in self.state.items() if p in FRAME_KEYS}
        if settled:
            top = most_severe(evaluate(frame, self.thresholds))
            if top is not None:
                if self.current is None or top.type != self.current.type or top.severity > self.current.severity:
                    self._publish(top)
                self.held_until = now + self.HOLD_S
                self.current = top
                return
        if self.current is not None and now >= self.held_until:
            self._clear()

    def _publish(self, finding: Finding) -> None:
        t0_ms = self.wall_ms()  # t0: the moment the hazard is detected
        D = self.Datapoint
        self.client.set_current_values({
            vss.HAZARD_TYPE: D(finding.type),
            vss.HAZARD_SEVERITY: D(finding.severity),
            vss.HAZARD_DETAIL: D(finding.detail),
            vss.HAZARD_DETECTED_AT: D(t0_ms),
            vss.HAZARD_LIGHTS: D(finding.severity >= CRITICAL),
        })

    def _clear(self) -> None:
        D = self.Datapoint
        self.client.set_current_values({
            vss.HAZARD_TYPE: D(vss.NO_HAZARD),
            vss.HAZARD_SEVERITY: D(0),
            vss.HAZARD_DETAIL: D(""),
            vss.HAZARD_LIGHTS: D(False),
        })
        self.current = None

    def stop(self, client: Any) -> None:
        client.disconnect()


def thresholds_for(cfg: VehicleConfig) -> Thresholds:
    return Thresholds(speed_limit_kmh=cfg.speed_limit_kmh)


def run(cfg: VehicleConfig, client: Any, stop: threading.Event) -> None:
    detector = Detector(client, thresholds_for(cfg), databroker.datapoint_class(cfg))

    def step_loop() -> None:
        while not stop.wait(0.02):
            detector.step()

    threading.Thread(target=step_loop, name=f"{cfg.vehicle_id}-detector-step", daemon=True).start()
    for updates in client.subscribe_current_values(INPUT_PATHS):
        if stop.is_set():
            break
        detector.on_updates(updates)


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
