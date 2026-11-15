"""Run the Beam pipeline (spec REQ-033): in batch on the laptop, in streaming on Dataflow (T16).

Laptop and mock dashboard (run_demo.py):
    the bridge copies Zenoh messages into the fake Pub/Sub buffer (last hour); every 30 s
    LaptopPipeline runs FleetPipeline in batch over the whole buffer on FnApiRunner, the
    DirectRunner's in-process engine. The sinks write into the dashboard's own Store, which is
    registered under its DATABASE_URL (cloud/app/store.py, register_store / store_for).

Beam is imported only inside functions: in the Kuksa venv (no Beam, spec REQ-025 AC3) the demo
must still start, without the pipeline.
"""

from __future__ import annotations

import threading
import time
import traceback
from typing import Any, Iterable

from cloud.pipeline.bridge import PubSubBridge
from cloud.pipeline.pubsub import TOPICS

LAPTOP_PROJECT = "local"


def beam_installed() -> bool:
    try:
        import apache_beam  # noqa: F401
    except ImportError:
        return False
    return True


def buffered_elements(project: str = LAPTOP_PROJECT) -> list[tuple[str, bytes, int]]:
    """(kind, raw message, arrival_ms) for everything in the fake Pub/Sub buffer."""
    from fakes import pubsub as fake_pubsub
    out = []
    for kind, topic in TOPICS.items():
        path = fake_pubsub.PublisherClient.topic_path(project, topic)
        out += [(kind, m.data, m.publish_time_ms) for m in fake_pubsub.messages(path)]
    return out


def run_batch(elements: list[tuple[str, Any, int]], database_url: str, known_vehicles: Iterable[str]) -> None:
    import apache_beam as beam
    from apache_beam.runners.portability.fn_api_runner import FnApiRunner

    from cloud.pipeline.transforms import FleetPipeline
    if not elements:
        return
    with beam.Pipeline(runner=FnApiRunner()) as p:
        _ = p | "Buffer" >> beam.Create(elements) | "Fleet" >> FleetPipeline(database_url, known_vehicles)


class LaptopPipeline:
    """The bridge plus a batch run of the pipeline every interval_s seconds, in this process."""

    def __init__(self, database_url: str, known_vehicles: Iterable[str], bridge: PubSubBridge,
                 project: str = LAPTOP_PROJECT, interval_s: float = 30.0) -> None:
        self.database_url = database_url
        self.known_vehicles = sorted(known_vehicles)
        self.bridge = bridge
        self.project = project
        self.interval_s = interval_s
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._status = {"installed": True, "mode": "batch", "interval_s": interval_s, "runs": 0,
                        "last_run_ms": None, "last_run_s": None, "last_error": None}

    def start(self) -> None:
        self.bridge.start()
        threading.Thread(target=self._loop, name="beam-batch", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self.bridge.stop()

    def run_once(self) -> None:
        started = time.time()
        try:
            run_batch(buffered_elements(self.project), self.database_url, self.known_vehicles)
            error = None
        except Exception as exc:  # a failed batch must not stop the demo; it is shown in the status
            traceback.print_exc()
            error = repr(exc)
        with self._lock:
            self._status.update(runs=self._status["runs"] + 1, last_run_ms=int(started * 1000),
                                last_run_s=round(time.time() - started, 2), last_error=error)

    def status(self) -> dict:
        with self._lock:
            return dict(self._status)

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_s):
            self.run_once()


def start_laptop_pipeline(store: Any, database_url: str, known_vehicles: Iterable[str], session: Any,
                          interval_s: float = 30.0) -> LaptopPipeline | None:
    """Start the bridge and the batch loop; None (and nothing started) when Beam is not installed."""
    if not beam_installed():
        return None
    from cloud.app.store import register_store
    from fakes import pubsub as fake_pubsub
    register_store(store, database_url)
    bridge = PubSubBridge(session, fake_pubsub.PublisherClient(), LAPTOP_PROJECT)
    pipeline = LaptopPipeline(database_url, known_vehicles, bridge, interval_s=interval_s)
    pipeline.start()
    return pipeline
