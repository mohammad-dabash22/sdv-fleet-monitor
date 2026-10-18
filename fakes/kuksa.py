"""Fake Kuksa Databroker + client.

Copies the parts of ``kuksa_client.grpc.VSSClient`` that we use:

    with VSSClient(host, port) as client:
        client.set_current_values({path: Datapoint(value)})
        client.get_current_values([path, ...])
        for updates in client.subscribe_current_values([path, ...]):
            updates[path].value

Every (host, port) pair is its own in-memory Databroker, just like every
vehicle will have its own Kuksa Databroker container. Different processes do
NOT share a fake broker, so the demo runs everything in one process.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator

__all__ = ["Datapoint", "VSSClient", "reset"]


@dataclass
class Datapoint:
    value: Any = None
    timestamp: float = field(default_factory=time.time)


class _Broker:
    """One in-memory Databroker: current values + subscribers."""

    def __init__(self) -> None:
        self._values: dict[str, Datapoint] = {}
        self._subs: list[tuple[frozenset[str], queue.Queue]] = []
        self._lock = threading.Lock()

    def set(self, updates: dict[str, Datapoint]) -> None:
        with self._lock:
            self._values.update(updates)
            subs = list(self._subs)
        for paths, q in subs:
            hit = {p: dp for p, dp in updates.items() if p in paths}
            if hit:
                q.put(hit)

    def get(self, paths: Iterable[str]) -> dict[str, Datapoint]:
        with self._lock:
            return {p: self._values[p] for p in paths if p in self._values}

    def subscribe(self, paths: Iterable[str]) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        wanted = frozenset(paths)
        with self._lock:
            self._subs.append((wanted, q))
            current = {p: self._values[p] for p in wanted if p in self._values}
        if current:  # like Kuksa: the first update holds the current values
            q.put(current)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            self._subs = [(p, sq) for p, sq in self._subs if sq is not q]


_brokers: dict[tuple[str, int], _Broker] = {}
_registry_lock = threading.Lock()


def _broker_for(host: str, port: int) -> _Broker:
    with _registry_lock:
        key = (host, int(port))
        if key not in _brokers:
            _brokers[key] = _Broker()
        return _brokers[key]


def reset() -> None:
    """Forget all brokers (used by tests)."""
    with _registry_lock:
        _brokers.clear()


class VSSClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 55555, **_: Any) -> None:
        self._broker = _broker_for(host, port)
        self._queues: list[queue.Queue] = []
        self._closed = threading.Event()

    # context manager, like the real client
    def __enter__(self) -> "VSSClient":
        self.connect()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.disconnect()

    def connect(self) -> None:
        self._closed.clear()

    def disconnect(self) -> None:
        self._closed.set()
        for q in self._queues:
            q.put(None)  # wake up blocked subscribers so they can exit

    def set_current_values(self, updates: dict[str, Datapoint]) -> None:
        self._broker.set(updates)

    def get_current_values(self, paths: Iterable[str]) -> dict[str, Datapoint]:
        return self._broker.get(paths)

    def subscribe_current_values(self, paths: Iterable[str]) -> Iterator[dict[str, Datapoint]]:
        q = self._broker.subscribe(paths)
        self._queues.append(q)
        try:
            while not self._closed.is_set():
                item = q.get()
                if item is None:
                    break
                yield item
        finally:
            self._broker.unsubscribe(q)
