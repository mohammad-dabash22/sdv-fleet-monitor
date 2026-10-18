"""Fake Zenoh: in-memory publish/subscribe with a small network delay.

Copies the parts of the zenoh-python API that we use:

    session = zenoh.open(config)
    session.put("fleet/veh-01/telemetry", json_text)
    sub = session.declare_subscriber("fleet/*/hazards", handler)
    # handler(sample): str(sample.key_expr), sample.payload.to_string()
    sub.undeclare(); session.close()

All sessions in one process share one bus. Messages are delivered on a
background thread, like real Zenoh, after a short random delay so the
latency panel shows realistic numbers. Key expressions support '*' (one
chunk) and '**' (any number of chunks).
"""

from __future__ import annotations

import heapq
import itertools
import random
import threading
import time
from typing import Any, Callable

__all__ = ["open", "configure", "reset", "Session", "Sample", "ZBytes"]


class ZBytes:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def to_bytes(self) -> bytes:
        return self._data

    def to_string(self) -> str:
        return self._data.decode("utf-8")


class Sample:
    def __init__(self, key_expr: str, payload: bytes) -> None:
        self.key_expr = key_expr
        self.payload = ZBytes(payload)


def key_matches(pattern: str, key: str) -> bool:
    p, k = pattern.split("/"), key.split("/")

    def m(i: int, j: int) -> bool:
        if i == len(p):
            return j == len(k)
        if p[i] == "**":
            return any(m(i + 1, jj) for jj in range(j, len(k) + 1))
        if j == len(k):
            return False
        return (p[i] == "*" or p[i] == k[j]) and m(i + 1, j + 1)

    return m(0, 0)


class _Bus:
    def __init__(self) -> None:
        self.delay_ms = 40.0
        self.jitter_ms = 30.0
        self._rng = random.Random()
        self._subs: dict[int, tuple[str, Callable[[Sample], Any]]] = {}
        self._ids = itertools.count(1)
        self._seq = itertools.count()
        self._heap: list[tuple[float, int, str, bytes]] = []
        self._cond = threading.Condition()
        self._thread: threading.Thread | None = None

    def _ensure_thread(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._dispatch, name="fake-zenoh", daemon=True)
            self._thread.start()

    def subscribe(self, key_expr: str, handler: Callable[[Sample], Any]) -> int:
        with self._cond:
            sub_id = next(self._ids)
            self._subs[sub_id] = (key_expr, handler)
            self._ensure_thread()
            return sub_id

    def unsubscribe(self, sub_id: int) -> None:
        with self._cond:
            self._subs.pop(sub_id, None)

    def put(self, key: str, payload: bytes) -> None:
        delay = max(0.0, self.delay_ms + self._rng.uniform(-self.jitter_ms, self.jitter_ms)) / 1000
        with self._cond:
            heapq.heappush(self._heap, (time.monotonic() + delay, next(self._seq), key, payload))
            self._ensure_thread()
            self._cond.notify()

    def _dispatch(self) -> None:
        while True:
            with self._cond:
                while not self._heap or self._heap[0][0] > time.monotonic():
                    timeout = None if not self._heap else self._heap[0][0] - time.monotonic()
                    self._cond.wait(timeout)
                _, _, key, payload = heapq.heappop(self._heap)
                handlers = [h for pat, h in self._subs.values() if key_matches(pat, key)]
            for handler in handlers:
                try:
                    handler(Sample(key, payload))
                except Exception as exc:  # a bad handler must not kill the bus
                    print(f"[fake-zenoh] handler error on {key}: {exc!r}")


_bus = _Bus()


class Subscriber:
    def __init__(self, sub_id: int) -> None:
        self._id = sub_id

    def undeclare(self) -> None:
        _bus.unsubscribe(self._id)


class Session:
    def __init__(self) -> None:
        self._subs: list[Subscriber] = []

    def put(self, key_expr: str, payload: str | bytes) -> None:
        data = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
        _bus.put(str(key_expr), data)

    def declare_subscriber(self, key_expr: str, handler: Callable[[Sample], Any]) -> Subscriber:
        sub = Subscriber(_bus.subscribe(str(key_expr), handler))
        self._subs.append(sub)
        return sub

    def close(self) -> None:
        for sub in self._subs:
            sub.undeclare()
        self._subs.clear()


def open(config: Any = None) -> Session:  # noqa: A001 - same name as zenoh.open
    return Session()


def configure(delay_ms: float = 40.0, jitter_ms: float = 30.0, seed: int | None = None) -> None:
    """Set the fake network delay (milliseconds)."""
    _bus.delay_ms = float(delay_ms)
    _bus.jitter_ms = float(jitter_ms)
    if seed is not None:
        _bus._rng.seed(seed)


def reset() -> None:
    """Drop all subscribers and pending messages (used by tests)."""
    with _bus._cond:
        _bus._subs.clear()
        _bus._heap.clear()
