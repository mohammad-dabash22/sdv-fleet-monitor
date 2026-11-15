"""REQ-007: the vehicle-to-cloud contract is written down as JSON Schema, and the publisher keeps to it.

This test sits in tests/ because it uses both halves: the vehicle's publisher produces the
messages, the cloud's schema files describe them. The halves themselves never import each other.
"""

import json
from pathlib import Path

import jsonschema

from fakes.kuksa import Datapoint
from vehicle.cloud_publisher.main import Bridge
from vehicle.common import vss

SCHEMAS = Path(__file__).resolve().parents[1] / "cloud" / "pipeline" / "schemas"


class RecordingSession:
    """Stands in for the Zenoh session: keeps what the publisher puts."""

    def __init__(self):
        self.puts = []

    def put(self, key, payload):
        self.puts.append((key, json.loads(payload)))


def schema(name):
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def full_twin():
    return {vss.SPEED: Datapoint(42.0), vss.LATITUDE: Datapoint(43.9), vss.LONGITUDE: Datapoint(-78.85),
            vss.SOC: Datapoint(77.5), vss.POWER_STATE: Datapoint("ON"), vss.ODOMETER: Datapoint(12000.5),
            vss.FLEET_ROUTE_ID: Datapoint("B"), vss.FLEET_TRIP_ID: Datapoint(3), vss.HAZARD_LIGHTS: Datapoint(False)}


def test_req_007_messages_match_json_schemas():
    session = RecordingSession()
    bridge = Bridge(session, {"vehicle_id": "veh-02", "route_id": "B"})
    bridge.on_updates(full_twin())
    jsonschema.validate(bridge.snapshot(), schema("telemetry.schema.json"))

    bridge.latest.update({vss.HAZARD_TYPE: "TRACTION_LOSS", vss.HAZARD_SEVERITY: 3,
                          vss.HAZARD_DETAIL: "TCS", vss.HAZARD_DETECTED_AT: 1_700_000_000_000})
    bridge.flush_hazard()
    (key, event), = session.puts
    assert key == "fleet/veh-02/hazards"
    jsonschema.validate(event, schema("hazard.schema.json"))


def test_req_007_schemas_reject_unknown_fields_and_wrong_types():
    telemetry = schema("telemetry.schema.json")
    bridge = Bridge(RecordingSession(), {"vehicle_id": "veh-01", "route_id": "A"})
    bridge.on_updates(full_twin())
    good = bridge.snapshot()
    for bad in ({**good, "extra": 1}, {**good, "speed_kmh": "fast"}):
        try:
            jsonschema.validate(bad, telemetry)
        except jsonschema.ValidationError:
            continue
        raise AssertionError(f"schema accepted {bad}")


def test_req_007_hazard_trip_id_is_optional_for_readers():
    hazard = {"vehicle_id": "veh-02", "route_id": "B", "type": "HARSH_BRAKING", "severity": 2, "detail": "x",
              "lat": 43.9, "lon": -78.85, "speed_kmh": 40.0, "t0_ms": 1_700_000_000_000}
    jsonschema.validate(hazard, schema("hazard.schema.json"))   # an MVP publisher, without trip_id
