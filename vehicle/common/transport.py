"""Open the vehicle-to-cloud session: the fake one, or real Zenoh (TRANSPORT=fake | zenoh).

The two Zenoh keys below, plus the JSON shape of the messages, are the ONLY
link between the vehicle half and the cloud half (see the UML package diagram).

Real Zenoh: TRANSPORT=zenoh and ZENOH_ENDPOINT=tcp/<router-ip>:7447 (the router on GKE).
"""

from __future__ import annotations

import json
from typing import Any

from .config import VehicleConfig


def telemetry_key(vehicle_id: str) -> str:
    return f"fleet/{vehicle_id}/telemetry"


def hazards_key(vehicle_id: str) -> str:
    return f"fleet/{vehicle_id}/hazards"


def open_session(cfg: VehicleConfig) -> Any:
    if cfg.transport == "fake":
        from fakes import zenoh as fake_zenoh
        return fake_zenoh.open()
    if cfg.transport == "zenoh":
        import zenoh  # type: ignore[import-not-found]
        conf = zenoh.Config()
        conf.insert_json5("connect/endpoints", json.dumps([cfg.zenoh_endpoint]))
        return zenoh.open(conf)
    raise ValueError(f"Unknown TRANSPORT: {cfg.transport!r} (use 'fake' or 'zenoh')")
