"""The Beam pipeline: quality flags and trip stats (spec REQ-030, REQ-031, REQ-033).

One composite transform, FleetPipeline, used unchanged by every runner. Its input is a PCollection of
(kind, raw message, arrival_ms) tuples; only the step that produces them differs:

    tests and laptop   beam.Create(...)                   batch, FnApiRunner (cloud/pipeline/run.py)
    Dataflow           ReadFromPubSub on 2 subscriptions  streaming (cloud/pipeline/run.py)

    raw ─► ParseAndCheck ─┬─ flagged ─► WriteFlags ─► quality_flags
                          └─ valid ───► key by van ─► GroupByKey ─► metrics.trips ─► WriteTrips ─► trip_stats

arrival_ms is when the bridge received the message (the Pub/Sub publish time on Dataflow). The
LATE rule uses it, so a message that sits in the laptop's buffer for an hour does not turn late.

In streaming, the trip step uses one global window per van with a trigger every 30 s in
accumulating mode: each firing sees every message of that van so far, and the trip rows are
upserts, so batch and streaming produce the same rows.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Iterable

import apache_beam as beam
from apache_beam import pvalue
from apache_beam.transforms import trigger, window

from cloud.pipeline import metrics
from cloud.quality import TIME_FIELD, validate

FLAGGED = "flagged"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _flag(kind: str, raw: str, message: dict | None, codes: list[str], detail: str) -> dict:
    record_ms = message.get(TIME_FIELD[kind]) if message else None
    return {
        "id": hashlib.sha256(f"{kind}\n{raw}".encode("utf-8")).hexdigest(),
        "vehicle_id": message.get("vehicle_id") if message else None,
        "route_id": message.get("route_id") if message else None,
        "kind": kind,
        "problems": ",".join(codes),
        "detail": detail,
        "raw": raw,
        "record_ms": record_ms if isinstance(record_ms, int) and not isinstance(record_ms, bool) else None,
    }


class ParseAndCheck(beam.DoFn):
    """Decode and validate; valid messages go on as (vehicle_id, (kind, message)), the rest are flagged."""

    def __init__(self, known_vehicles: Iterable[str]) -> None:
        self.known = sorted(known_vehicles)

    def process(self, element: tuple[str, Any, int]):
        kind, raw, arrival_ms = element
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        try:
            message = json.loads(text)
        except ValueError:
            message = None
        if not isinstance(message, dict):
            yield pvalue.TaggedOutput(FLAGGED, _flag(kind, text, None, ["MALFORMED"], "not a JSON object"))
            return
        problems = validate(message, kind, self.known, arrival_ms)
        if problems:
            yield pvalue.TaggedOutput(FLAGGED, _flag(kind, text, message, [p.code for p in problems],
                                                     "; ".join(p.detail for p in problems)))
        else:
            yield message["vehicle_id"], (kind, message)


class _StoreSink(beam.DoFn):
    """Base for the sinks: only the URL is pickled; the Store comes from the per-process registry."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def setup(self) -> None:
        from cloud.app.store import store_for  # imported on the worker
        self.store = store_for(self.database_url)


class WriteFlags(_StoreSink):
    def process(self, flag: dict):
        self.store.upsert_quality_flag(flag, processed_at_ms=_now_ms())
        yield flag


class WriteTrips(_StoreSink):
    def process(self, trip: dict):
        self.store.upsert_trip_stats(trip, processed_at_ms=_now_ms())
        yield trip


def _trips_of_van(keyed: tuple[str, Iterable[tuple[str, dict]]]) -> list[dict]:
    _, items = keyed
    items = list(items)
    return metrics.trips([m for k, m in items if k == "telemetry"], [m for k, m in items if k == "hazard"])


class FleetPipeline(beam.PTransform):
    """(kind, raw, arrival_ms) in; quality_flags and trip_stats rows written. Returns the trip rows."""

    def __init__(self, database_url: str, known_vehicles: Iterable[str], streaming: bool = False,
                 fire_every_s: int = 30) -> None:
        super().__init__()
        self.database_url = database_url
        self.known_vehicles = sorted(known_vehicles)
        self.streaming = streaming
        self.fire_every_s = fire_every_s

    def expand(self, messages):
        checked = messages | "ParseAndCheck" >> beam.ParDo(ParseAndCheck(self.known_vehicles)).with_outputs(
            FLAGGED, main="valid")
        _ = checked[FLAGGED] | "WriteFlags" >> beam.ParDo(WriteFlags(self.database_url))

        valid = checked.valid
        if self.streaming:
            valid = valid | "EveryVanSoFar" >> beam.WindowInto(
                window.GlobalWindows(),
                trigger=trigger.Repeatedly(trigger.AfterProcessingTime(self.fire_every_s)),
                accumulation_mode=trigger.AccumulationMode.ACCUMULATING)
        return (valid
                | "ByVan" >> beam.GroupByKey()
                | "Trips" >> beam.FlatMap(_trips_of_van)
                | "WriteTrips" >> beam.ParDo(WriteTrips(self.database_url)))
