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
