"""Fake Google Pub/Sub publisher: an in-memory buffer per topic, for the laptop demo and the tests.

Copies the parts of ``google.cloud.pubsub_v1.PublisherClient`` that the bridge uses:

    client = PublisherClient()
    path = client.topic_path(project, "fleet-telemetry")
    client.publish(path, data_bytes, vehicle_id="veh-01", kind="telemetry").result()

There is no subscriber: the laptop's batch pipeline reads the buffer with messages(path).
Every topic keeps only the last hour of messages (RETENTION_S), so the mock dashboard on GKE,
which runs for days, does not slow down (spec REQ-033 AC2). Older trips are already stored.
"""

from __future__ import annotations

import collections
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

__all__ = ["PublisherClient", "Message", "messages", "reset", "RETENTION_S"]

RETENTION_S = 3600.0


@dataclass(frozen=True)
class Message:
    data: bytes
    attributes: dict = field(default_factory=dict)
    publish_time_ms: int = 0


class _Done:
    """Like the future that the real publish() returns."""

    def __init__(self, message_id: str) -> None:
        self._id = message_id

    def result(self, timeout: float | None = None) -> str:
        return self._id

    def add_done_callback(self, fn: Callable) -> None:
        fn(self)

    def exception(self, timeout: float | None = None) -> None:
        return None


_topics: dict[str, collections.deque[Message]] = collections.defaultdict(collections.deque)
_lock = threading.Lock()
_ids = iter(range(1, 1 << 62))


class PublisherClient:
    def __init__(self, clock: Callable[[], float] = time.time, **_: object) -> None:
        self._clock = clock

    @staticmethod
    def topic_path(project: str, topic: str) -> str:
        return f"projects/{project}/topics/{topic}"

    def publish(self, topic: str, data: bytes, **attributes: str) -> _Done:
        now = self._clock()
        with _lock:
            q = _topics[topic]
            q.append(Message(bytes(data), dict(attributes), int(now * 1000)))
            _drop_old(q, now)
            return _Done(str(next(_ids)))


def messages(topic: str) -> list[Message]:
    """A snapshot of the topic's buffer, oldest first."""
    with _lock:
        return list(_topics.get(topic, ()))


def reset() -> None:
    """Forget every topic (used by tests)."""
    with _lock:
        _topics.clear()


def _drop_old(q: collections.deque[Message], now: float) -> None:
    cutoff_ms = (now - RETENTION_S) * 1000
    while q and q[0].publish_time_ms < cutoff_ms:
        q.popleft()
