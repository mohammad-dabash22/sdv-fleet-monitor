"""Open the Pub/Sub publisher: the fake one, or Google Cloud Pub/Sub (spec REQ-027 AC3).

This is the ONLY file that knows whether Pub/Sub is fake (PUBSUB=fake | gcp), like
cloud/app/transport.py for Zenoh and vehicle/common/databroker.py for Kuksa.
"""

from __future__ import annotations

from typing import Any

# One topic per message kind; Dataflow reads them through one subscription each.
TOPICS = {"telemetry": "fleet-telemetry", "hazard": "fleet-hazards"}
SUBSCRIPTIONS = {"telemetry": "fleet-telemetry-beam", "hazard": "fleet-hazards-beam"}


def open_publisher(kind: str) -> Any:
    if kind == "fake":
        from fakes import pubsub as fake_pubsub
        return fake_pubsub.PublisherClient()
    if kind == "gcp":
        from google.cloud import pubsub_v1  # type: ignore[import-untyped]
        return pubsub_v1.PublisherClient()
    raise ValueError(f"Unknown PUBSUB: {kind!r} (use 'fake' or 'gcp')")
