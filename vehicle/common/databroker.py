"""Connect to the vehicle's Databroker (fake today, Kuksa next phase).

This is the ONLY vehicle file that knows whether the Databroker is fake.

NEXT PHASE:
    pip install kuksa-client      (pin the version that works with Velocitas)
    set DATABROKER=kuksa, DATABROKER_HOST, DATABROKER_PORT
"""

from __future__ import annotations

from typing import Any

from .config import VehicleConfig


def _client_class(kind: str) -> tuple[type, type]:
    if kind == "fake":
        from fakes.kuksa import Datapoint, VSSClient
        return VSSClient, Datapoint
    if kind == "kuksa":
        from kuksa_client.grpc import Datapoint, VSSClient  # type: ignore[import-not-found]
        return VSSClient, Datapoint
    raise ValueError(f"Unknown DATABROKER: {kind!r} (use 'fake' or 'kuksa')")


def connect(cfg: VehicleConfig) -> Any:
    """Return a VSSClient. Use it as a context manager: ``with connect(cfg) as client:``."""
    client_cls, _ = _client_class(cfg.databroker)
    return client_cls(cfg.databroker_host, cfg.databroker_port)


def datapoint_class(cfg: VehicleConfig) -> type:
    return _client_class(cfg.databroker)[1]
