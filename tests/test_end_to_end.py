"""Integration test (FR-19): one van + the cloud, wired together with the fakes.

A hard-braking value is written into the van's Databroker. The test checks
that the full chain (detector -> publisher -> transport -> cloud -> store)
produces an alert, tagged with route and location, in under 2 seconds.

NEXT PHASE: keep this test (it stays fast). Add a second CI job that runs
the same check against real Kuksa + Zenoh containers.
"""

import threading
import time

from fastapi.testclient import TestClient

from cloud.app.config import CloudConfig
from cloud.app.main import create_app
from fakes.kuksa import Datapoint, VSSClient
from vehicle.cloud_publisher import main as publisher
from vehicle.common import databroker, vss
from vehicle.common.config import VehicleConfig
from vehicle.hazard_detector import main as detector


def test_hazard_reaches_cloud_within_two_seconds():
    cfg = VehicleConfig(vehicle_id="veh-02", route_id="B", speed_limit_kmh=50, databroker_port=60001)
    stop = threading.Event()
    with TestClient(create_app(CloudConfig(transport="fake"))) as api:
        for module in (detector, publisher):
            client = databroker.connect(cfg)
            threading.Thread(target=module.run, args=(cfg, client, stop), daemon=True).start()
        time.sleep(0.2)  # let both apps subscribe

        sensors = VSSClient(cfg.databroker_host, cfg.databroker_port)
        sensors.set_current_values({vss.LATITUDE: Datapoint(43.89), vss.LONGITUDE: Datapoint(-78.85),
                                    vss.SPEED: Datapoint(48.0), vss.ACCEL_LONG: Datapoint(-6.5)})
        start = time.time()
        alerts = []
        while time.time() - start < 2.0 and not alerts:
            alerts = api.get("/api/alerts").json()["items"]
            time.sleep(0.05)
        stop.set()

    assert alerts, "no alert reached the cloud within 2 seconds"
    a = alerts[0]
    assert a["type"] == "HARSH_BRAKING" and a["route_id"] == "B"
    assert a["lat"] == 43.89 and a["lon"] == -78.85
    assert 0 <= a["latency_ms"] < 2000


def test_req_036_replay_reaches_both_paths():
    """The sample file through the whole laptop system: the live path rejects bad telemetry,
    the pipeline flags every bad record, and hazards with problems still become alerts."""
    from cloud.pipeline import run
    from cloud.pipeline.samples import SAMPLE_FILE, load_samples
    from fakes import pubsub as fake_pubsub
    from fakes import zenoh as fake_zenoh
    from tools.replay_samples import replay

    fake_pubsub.reset()
    cfg = CloudConfig(transport="fake")
    with TestClient(create_app(cfg)) as api:
        pipeline = run.start_laptop_pipeline(api.app.state.service.store, cfg.database_url,
                                             ["veh-01", "veh-02", "veh-03"], fake_zenoh.open(), interval_s=3600)
        samples = load_samples(SAMPLE_FILE, int(time.time() * 1000))
        sent = replay(fake_zenoh.open(), samples, gap_s=0)
        assert sent == len(samples) == 36

        start = time.time()
        while time.time() - start < 3 and len(run.buffered_elements(pipeline.project)) < sent:
            time.sleep(0.05)
        good_veh02 = [s for s in samples if s.kind == "telemetry" and not s.expect and s.message["vehicle_id"] == "veh-02"]
        history = api.get("/api/history/veh-02").json()
        assert len(history) == len(good_veh02) == 18          # live path: every bad record rejected
        assert all(0 <= r["speed_kmh"] <= 250 for r in history)

        alerts = [a for a in api.get("/api/alerts?limit=100").json()["items"] if a["vehicle_id"] == "veh-02"]
        assert len(alerts) == 5                                # 4 good hazards + 1 with no location
        assert any(a["lat"] is None for a in alerts)           # a hazard with a problem is never rejected

        pipeline.run_once()                                    # analytics path: every bad record flagged
        assert api.get("/api/routes").json()["flagged_records"] == 12
        pipeline.stop()
