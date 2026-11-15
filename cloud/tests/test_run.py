"""REQ-033: the laptop runner. Samples go over (fake) Zenoh, through the bridge into the (fake)
Pub/Sub buffer, a Beam batch runs over the buffer, and the results land in the dashboard's store."""

import json
import sys
import time

from fastapi.testclient import TestClient

from cloud.app.config import CloudConfig
from cloud.app.main import create_app
from cloud.pipeline import run
from cloud.pipeline.samples import SAMPLE_FILE, load_samples
from fakes import pubsub as fake_pubsub
from fakes import zenoh as fake_zenoh

KNOWN = ["veh-01", "veh-02", "veh-03"]


def wait_for(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end and not cond():
        time.sleep(0.02)
    return cond()


def put_samples(now_ms):
    bus = fake_zenoh.open()
    samples = load_samples(SAMPLE_FILE, now_ms)
    for s in samples:
        key = f"fleet/{s.message.get('vehicle_id', 'x')}/{'telemetry' if s.kind == 'telemetry' else 'hazards'}"
        bus.put(key, json.dumps(s.message))
    return samples


def test_req_033_batch_run_writes_tables():
    fake_pubsub.reset()
    cfg = CloudConfig(transport="fake")
    with TestClient(create_app(cfg)) as client:
        store = client.app.state.service.store
        pipeline = run.start_laptop_pipeline(store, cfg.database_url, KNOWN, fake_zenoh.open(), interval_s=3600)
        samples = put_samples(int(time.time() * 1000))
        assert wait_for(lambda: len(run.buffered_elements(pipeline.project)) == len(samples))
        pipeline.run_once()
        assert store.quality_flag_count() == 12
        assert [t["trip_id"] for t in store.trip_stats()] == [2]
        assert pipeline.status()["runs"] == 1 and pipeline.status()["last_error"] is None
        pipeline.stop()


def test_req_033_live_path_works_without_pipeline(monkeypatch):
    monkeypatch.setitem(sys.modules, "apache_beam", None)       # like the Kuksa venv: Beam is not installed
    assert not run.beam_installed()
    cfg = CloudConfig(transport="fake")
    with TestClient(create_app(cfg)) as client:
        pipeline = run.start_laptop_pipeline(client.app.state.service.store, cfg.database_url, KNOWN,
                                             fake_zenoh.open(), interval_s=3600)
        assert pipeline is None
        assert client.get("/api/health").json()["status"] == "ok"
        assert len(client.get("/api/fleet").json()) == 3
