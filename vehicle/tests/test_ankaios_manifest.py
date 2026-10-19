import json

from tools import ankaios_manifest


def test_state_yaml_is_up_to_date():
    """deploy/ankaios/state.yaml is generated; regenerate it after changing config/fleet.json."""
    fleet = json.loads(ankaios_manifest.FLEET.read_text(encoding="utf-8"))
    expected = ankaios_manifest.render(fleet)
    assert ankaios_manifest.OUT.read_text(encoding="utf-8") == expected, \
        "run: python -m tools.ankaios_manifest"


def test_every_van_gets_its_own_agent_and_port():
    fleet = {
        "routes": {"A": {"speed_limit_kmh": 60}},
        "vehicles": [
            {"vehicle_id": "veh-01", "route_id": "A", "databroker_port": 55555},
            {"vehicle_id": "veh-09", "route_id": "A", "databroker_port": 55563},
        ],
    }
    text = ankaios_manifest.render(fleet)
    for vid, port in (("veh-01", 55555), ("veh-09", 55563)):
        for app in ("databroker", "simulator", "detector"):
            assert f"  {vid}-{app}:\n" in text
        assert f"agent: {vid}\n" in text
        assert f'"DATABROKER_PORT={port}"' in text
        assert f'["--port", "{port}"]' in text


def test_zenoh_adds_a_publisher_per_van():
    fleet = {"routes": {"A": {"speed_limit_kmh": 60}},
             "vehicles": [{"vehicle_id": "veh-01", "route_id": "A", "databroker_port": 55555}]}
    assert "publisher" not in ankaios_manifest.render(fleet)
    text = ankaios_manifest.render(fleet, zenoh="tcp/10.0.0.5:7447")
    assert "  veh-01-publisher:\n" in text
    assert '"TRANSPORT=zenoh", "-e", "ZENOH_ENDPOINT=tcp/10.0.0.5:7447"' in text
    assert '["vehicle.cloud_publisher.main"]' in text
