import json
import time

from fakes import zenoh as fake_zenoh
from fakes.kuksa import Datapoint
from vehicle.cloud_publisher.main import Bridge
from vehicle.common import vss


def collect(pattern):
    got = []
    fake_zenoh.open().declare_subscriber(pattern, lambda s: got.append((str(s.key_expr), json.loads(s.payload.to_string()))))
    return got


def wait_for(cond, timeout=1.0):
    end = time.time() + timeout
    while time.time() < end and not cond():
        time.sleep(0.01)
    return cond()


def test_hazard_event_is_sent_once():
    got = collect("fleet/*/hazards")
    bridge = Bridge(fake_zenoh.open(), {"vehicle_id": "veh-02", "route_id": "B"})
    bridge.on_updates({vss.LATITUDE: Datapoint(43.9), vss.LONGITUDE: Datapoint(-78.8)})
    hazard = {vss.HAZARD_TYPE: Datapoint("TRACTION_LOSS"), vss.HAZARD_SEVERITY: Datapoint(3),
              vss.HAZARD_DETAIL: Datapoint("TCS"), vss.HAZARD_DETECTED_AT: Datapoint(1000)}
    bridge.on_updates(hazard)
    bridge.on_updates(hazard)  # same hazard again: must not be sent twice
    assert wait_for(lambda: len(got) >= 1)
    time.sleep(0.15)
    assert len(got) == 1
    key, event = got[0]
    assert key == "fleet/veh-02/hazards"
    assert event["type"] == "TRACTION_LOSS" and event["route_id"] == "B" and event["t0_ms"] == 1000
    assert event["lat"] == 43.9


def test_hazard_active_before_start_is_not_resent():
    got = collect("fleet/*/hazards")
    bridge = Bridge(fake_zenoh.open(), {"vehicle_id": "veh-01", "route_id": "A"})
    old = {vss.HAZARD_TYPE: Datapoint("OVERSPEED"), vss.HAZARD_SEVERITY: Datapoint(1),
           vss.HAZARD_DETAIL: Datapoint("old"), vss.HAZARD_DETECTED_AT: Datapoint(500)}
    bridge.skip_active_hazard(old)
    bridge.on_updates(old)  # the Databroker replays its current values on subscribe
    time.sleep(0.15)
    assert got == []
    bridge.on_updates({vss.HAZARD_TYPE: Datapoint("HARSH_BRAKING"), vss.HAZARD_DETECTED_AT: Datapoint(900)})
    assert wait_for(lambda: len(got) == 1)
    assert got[0][1]["type"] == "HARSH_BRAKING" and got[0][1]["t0_ms"] == 900


def test_snapshot_shape():
    bridge = Bridge(fake_zenoh.open(), {"vehicle_id": "veh-01", "route_id": "A"})
    bridge.on_updates({vss.SPEED: Datapoint(42.0), vss.SOC: Datapoint(77.0), vss.POWER_STATE: Datapoint("ON"),
                       vss.HAZARD_TYPE: Datapoint(vss.NO_HAZARD)})
    snap = bridge.snapshot()
    assert snap["vehicle_id"] == "veh-01" and snap["speed_kmh"] == 42.0
    assert snap["engine_on"] is True and snap["hazard"] is None
