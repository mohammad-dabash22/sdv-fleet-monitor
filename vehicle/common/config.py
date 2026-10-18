"""Vehicle app configuration.

In the demo, run_demo.py builds one VehicleConfig per van in code.
NEXT PHASE: each app runs in its own container, started by Ankaios, and
reads the same values from environment variables with VehicleConfig.from_env().
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class VehicleConfig:
    vehicle_id: str = "veh-01"
    route_id: str = "A"
    speed_limit_kmh: float = 50.0
    databroker: str = "fake"            # fake | kuksa
    databroker_host: str = "127.0.0.1"
    databroker_port: int = 55555
    transport: str = "fake"             # fake | zenoh
    zenoh_endpoint: str = "tcp/127.0.0.1:7447"
    telemetry_hz: float = 1.0
    time_scale: float = 15.0            # simulator only: vans move this many times faster on the map
    seed: int | None = None

    @classmethod
    def from_env(cls) -> "VehicleConfig":
        env = os.environ.get
        seed = env("SEED")
        return cls(
            vehicle_id=env("VEHICLE_ID", cls.vehicle_id),
            route_id=env("ROUTE_ID", cls.route_id),
            speed_limit_kmh=float(env("SPEED_LIMIT_KMH", cls.speed_limit_kmh)),
            databroker=env("DATABROKER", cls.databroker),
            databroker_host=env("DATABROKER_HOST", cls.databroker_host),
            databroker_port=int(env("DATABROKER_PORT", cls.databroker_port)),
            transport=env("TRANSPORT", cls.transport),
            zenoh_endpoint=env("ZENOH_ENDPOINT", cls.zenoh_endpoint),
            telemetry_hz=float(env("TELEMETRY_HZ", cls.telemetry_hz)),
            time_scale=float(env("SIM_TIME_SCALE", cls.time_scale)),
            seed=int(seed) if seed else None,
        )
