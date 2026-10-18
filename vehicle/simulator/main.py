"""Vehicle simulator: drives one van around its route and writes VSS signals.

It writes into the vehicle's Databroker (fake today, Kuksa next phase), like
a real vehicle's sensors would. It does NOT detect hazards; it only creates
the physical situations (hard braking, wheel slip, speeding) that the
HazardDetector must find.

Run one van on its own (next phase, inside a container):
    python -m vehicle.simulator.main

NEXT PHASE: nothing has to change here except, optionally, the VSS paths in
vehicle/common/vss.py and the driving model below.
"""

from __future__ import annotations

import random
import threading

from vehicle.common import databroker, vss
from vehicle.common.config import VehicleConfig

from .routes import PROFILES, ROUTES, loop_length_km, position_at

TICK_S = 0.5
BATTERY_KWH = 75.0
KWH_PER_KM = 0.25
RECHARGE_BELOW_PCT = 35.0


class Simulator:
    def __init__(self, cfg: VehicleConfig, datapoint: type, rng: random.Random | None = None) -> None:
        self.cfg = cfg
        self.Datapoint = datapoint
        self.rng = rng or random.Random(cfg.seed)
        self.points = ROUTES[cfg.route_id]
        self.profile = PROFILES[cfg.route_id]
        self.lap_km = loop_length_km(self.points)
        self.limit = cfg.speed_limit_kmh

        self.speed_kmh = 0.0
        self.target_kmh = self.limit * 0.8
        self.lap_pos_km = self.rng.uniform(0, self.lap_km * 0.5)
        self.odometer_km = round(self.rng.uniform(8000, 20000), 1)
        self.soc_pct = self.rng.uniform(70, 95)
        self.coolant_c = self.rng.uniform(60, 70)
        self.trip_id = 1
        self.overspeed_ticks = 0

    def tick(self) -> dict:
        """Advance the van by one tick and return the signal updates."""
        rng, p = self.rng, self.profile

        # 1. choose the target speed
        if self.overspeed_ticks > 0:
            self.overspeed_ticks -= 1
            self.target_kmh = self.limit + 18
        elif rng.random() < p["overspeed"]:
            self.overspeed_ticks = 8
        elif rng.random() < 0.05:
            self.target_kmh = self.limit * rng.uniform(0.7, 0.95)

        # 2. acceleration (normal driving, or a hard-braking event)
        if self.speed_kmh > 25 and rng.random() < p["harsh"]:
            accel = -rng.uniform(7.2, 9.0) if rng.random() < 0.2 else -rng.uniform(4.5, 6.8)
        else:
            accel = max(-2.5, min(2.0, (self.target_kmh - self.speed_kmh) / 3.6 / TICK_S))
        self.speed_kmh = max(0.0, self.speed_kmh + accel * TICK_S * 3.6)

        # 3. wheel slip: the traction control system steps in
        tcs = self.speed_kmh > 25 and rng.random() < p["traction"]

        # 4. move along the loop (time_scale makes the demo faster)
        dist_km = self.speed_kmh / 3600 * TICK_S * self.cfg.time_scale
        self.odometer_km += dist_km
        self.lap_pos_km += dist_km
        if self.lap_pos_km >= self.lap_km:  # back at the depot: the trip is over
            self.lap_pos_km -= self.lap_km
            self.trip_id += 1
            if self.soc_pct < RECHARGE_BELOW_PCT:
                self.soc_pct = 100.0
        self.soc_pct -= dist_km * KWH_PER_KM * p["energy_factor"] / BATTERY_KWH * 100
        self.coolant_c += rng.uniform(-0.5, 0.5) + (self.speed_kmh - 40) * 0.002
        self.coolant_c = max(55.0, min(85.0, self.coolant_c))
        lat, lon = position_at(self.points, self.lap_pos_km)

        values = {
            vss.SPEED: round(self.speed_kmh, 1),
            vss.ACCEL_LONG: round(accel, 2),
            vss.TCS_ENGAGED: tcs,
            vss.LATITUDE: round(lat, 6),
            vss.LONGITUDE: round(lon, 6),
            vss.SOC: round(self.soc_pct, 2),
            vss.ODOMETER: round(self.odometer_km, 3),
            vss.POWER_STATE: "ON",
            vss.COOLANT_TEMP: round(self.coolant_c, 1),
            vss.FLEET_VEHICLE_ID: self.cfg.vehicle_id,
            vss.FLEET_ROUTE_ID: self.cfg.route_id,
            vss.FLEET_TRIP_ID: self.trip_id,
        }
        return {path: self.Datapoint(value) for path, value in values.items()}


def run(cfg: VehicleConfig, client, stop: threading.Event) -> None:
    sim = Simulator(cfg, databroker.datapoint_class(cfg))
    while not stop.wait(TICK_S):
        client.set_current_values(sim.tick())


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
