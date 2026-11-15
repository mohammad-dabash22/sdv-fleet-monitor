"""Pub/Sub bridge: copies every raw vehicle message from Zenoh to Pub/Sub (spec REQ-027, D-1).

    fleet/{id}/telemetry  ─►  topic fleet-telemetry   attributes vehicle_id, kind=telemetry
    fleet/{id}/hazards    ─►  topic fleet-hazards     attributes vehicle_id, kind=hazard

It sits NEXT TO the live path (Zenoh -> CloudService -> dashboard), never on it: it does not parse,
check or change a message, and a failed publish is logged and skipped. The Beam pipeline does the
checking (it must also see the bad messages that CloudService rejects).

On GKE it runs as its own container in the sdv-cloud pod, next to the Zenoh router (deploy/k8s/cloud.yaml):
    PUBSUB=gcp TRANSPORT=zenoh ZENOH_ENDPOINT=tcp/127.0.0.1:7447 python -m cloud.pipeline.bridge
GCP_PROJECT is optional there: without it the project comes from the GKE metadata server.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable

from cloud.app.transport import HAZARD_KEYS, TELEMETRY_KEYS, open_session
from cloud.pipeline.pubsub import TOPICS, open_publisher


class PubSubBridge:
    def __init__(self, session: Any, publisher: Any, project: str) -> None:
        self.session = session
        self.publisher = publisher
        self.topics = {kind: publisher.topic_path(project, name) for kind, name in TOPICS.items()}
        self.published = 0
        self.failed = 0
        self._subs: list[Any] = []

    def start(self) -> None:
        self._subs.append(self.session.declare_subscriber(TELEMETRY_KEYS, lambda s: self.forward("telemetry", s)))
        self._subs.append(self.session.declare_subscriber(HAZARD_KEYS, lambda s: self.forward("hazard", s)))

    def stop(self) -> None:
        for sub in self._subs:
            sub.undeclare()
        self._subs.clear()

    def forward(self, kind: str, sample: Any) -> None:
        key = str(sample.key_expr)                     # fleet/{vehicle_id}/telemetry
        parts = key.split("/")
        vehicle_id = parts[1] if len(parts) == 3 else ""
        try:
            future = self.publisher.publish(self.topics[kind], sample.payload.to_bytes(),
                                            vehicle_id=vehicle_id, kind=kind)
            future.add_done_callback(lambda f: self._done(f, key))
        except Exception as exc:                        # the live path must never notice
            self._failed(key, exc)

    def _done(self, future: Any, key: str) -> None:
        exc = future.exception()
        if exc is None:
            self.published += 1
        else:
            self._failed(key, exc)

    def _failed(self, key: str, exc: BaseException) -> None:
        self.failed += 1
        print(f"[bridge] publish failed for {key}: {exc!r}", flush=True)


def connect_publisher(kind: str, project: str | None, wait: Callable[[float], Any] = time.sleep,
                      retry_s: float = 60.0) -> tuple[Any, str]:
    """Open the publisher, retrying until it works; never raises.

    On GKE the bridge is a container in the sdv-cloud pod. If it crashed while Pub/Sub permissions are
    missing (one-time setup, docs/pipeline.md), the pod would turn not-Ready and take the live dashboard
    down with it. So it waits and logs instead.
    """
    while True:
        try:
            publisher = open_publisher(kind)
            if not project:
                import google.auth  # type: ignore[import-untyped]
                project = google.auth.default()[1]   # the GKE node's project, from the metadata server
            return publisher, project or "local"
        except Exception as exc:
            print(f"[bridge] Pub/Sub not ready ({exc!r}); retrying in {retry_s:.0f} s", flush=True)
            wait(retry_s)


def main() -> None:
    session = open_session(os.environ.get("TRANSPORT", "fake"), os.environ.get("ZENOH_ENDPOINT", "tcp/127.0.0.1:7447"))
    kind = os.environ.get("PUBSUB", "fake")
    publisher, project = connect_publisher(kind, os.environ.get("GCP_PROJECT") or ("local" if kind == "fake" else None))
    bridge = PubSubBridge(session, publisher, project)
    bridge.start()
    print(f"[bridge] forwarding fleet/** to Pub/Sub topics {sorted(bridge.topics.values())}", flush=True)
    stop = threading.Event()
    try:
        while not stop.wait(60):
            print(f"[bridge] published {bridge.published}, failed {bridge.failed}", flush=True)
    except KeyboardInterrupt:
        bridge.stop()


if __name__ == "__main__":
    main()
