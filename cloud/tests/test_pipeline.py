"""REQ-030, REQ-031: the Beam graph, run for real on the DirectRunner's in-process engine (FnApiRunner).

The input is the sample file (REQ-036); the output is read back through the Store, the same way
the dashboard reads it.
"""

import json

import apache_beam as beam
from apache_beam.runners.portability.fn_api_runner import FnApiRunner

from cloud.app.store import Store, register_store
from cloud.pipeline import metrics
from cloud.pipeline.samples import SAMPLE_FILE, load_samples
from cloud.pipeline.transforms import FleetPipeline

KNOWN = ["veh-01", "veh-02", "veh-03"]
NOW_MS = 1_700_000_000_000
URL = "sqlite:///:memory:"


def fresh_store():
    store = Store(URL)
    register_store(store, URL)   # the sink finds this store by its URL, in this process
    return store


def elements(samples):
    return [(s.kind, json.dumps(s.message), NOW_MS) for s in samples]


def run(items):
    with beam.Pipeline(runner=FnApiRunner()) as p:
        _ = p | beam.Create(items) | FleetPipeline(URL, KNOWN)


def test_req_030_one_flag_per_bad_record():
    store = fresh_store()
    samples = load_samples(SAMPLE_FILE, NOW_MS)
    run(elements(samples))
    flags = store.quality_flags(limit=100)
    expected = sorted(",".join(sorted(s.expect)) for s in samples if s.expect)
    assert sorted(",".join(sorted(f["problems"].split(","))) for f in flags) == expected
    raw_bad = {json.dumps(s.message) for s in samples if s.expect}
    assert {f["raw"] for f in flags} == raw_bad                     # no good record is flagged


def test_req_030_malformed_message_is_flagged():
    store = fresh_store()
    run([("telemetry", "not json", NOW_MS), ("hazard", "[1, 2]", NOW_MS)])
    assert sorted(f["problems"] for f in store.quality_flags()) == ["MALFORMED", "MALFORMED"]


def test_req_031_trip_rows_match_metrics():
    store = fresh_store()
    samples = load_samples(SAMPLE_FILE, NOW_MS)
    run(elements(samples))
    good = [s for s in samples if not s.expect]
    expected = metrics.trips([s.message for s in good if s.kind == "telemetry"],
                             [s.message for s in good if s.kind == "hazard"])
    rows = store.trip_stats()
    assert len(rows) == len(expected) == 1
    row, want = rows[0], expected[0]
    for column in Store.TRIP_COLUMNS:
        assert row[column] == want[column], column
    route_b = next(r for r in store.route_stats() if r["route_id"] == "B")
    assert route_b["trips"] == 1 and route_b["hazards"] == 2


def test_req_031_streaming_mode_writes_the_same_rows():
    """The Dataflow shape: global window, trigger every 30 s, accumulating panes, upserts."""
    from apache_beam.options.pipeline_options import PipelineOptions, StandardOptions
    from apache_beam.runners.direct.direct_runner import BundleBasedDirectRunner
    from apache_beam.testing.test_stream import TestStream

    store = fresh_store()
    items = elements(load_samples(SAMPLE_FILE, NOW_MS))
    half = len(items) // 2
    stream = (TestStream()
              .add_elements(items[:half])
              .advance_processing_time(31)          # first firing: only half of the messages so far
              .add_elements(items[half:])
              .advance_processing_time(31)          # second firing: everything (accumulating)
              .advance_watermark_to_infinity())
    options = PipelineOptions()
    options.view_as(StandardOptions).streaming = True
    with beam.Pipeline(runner=BundleBasedDirectRunner(), options=options) as p:
        _ = p | stream | FleetPipeline(URL, KNOWN, streaming=True)

    batch_store = fresh_store()
    run(items)
    strip = lambda rows: [{k: v for k, v in r.items() if k != "processed_at_ms"} for r in rows]
    assert strip(store.trip_stats()) == strip(batch_store.trip_stats())
    assert store.quality_flag_count() == batch_store.quality_flag_count() == 12


def test_req_031_second_run_changes_nothing():
    store = fresh_store()
    items = elements(load_samples(SAMPLE_FILE, NOW_MS))
    run(items)
    first_trips = [{k: v for k, v in r.items() if k != "processed_at_ms"} for r in store.trip_stats()]
    first_flags = sorted(f["id"] for f in store.quality_flags(limit=100))
    run(items)
    assert [{k: v for k, v in r.items() if k != "processed_at_ms"} for r in store.trip_stats()] == first_trips
    assert sorted(f["id"] for f in store.quality_flags(limit=100)) == first_flags
