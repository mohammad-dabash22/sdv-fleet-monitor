import random

from fakes.kuksa import Datapoint
from vehicle.common import vss
from vehicle.common.config import VehicleConfig
from vehicle.simulator.main import Simulator
from vehicle.simulator.routes import ROUTES, loop_length_km, position_at


def test_tick_writes_all_signals():
    sim = Simulator(VehicleConfig(route_id="B", speed_limit_kmh=50), Datapoint, random.Random(1))
    values = {p: dp.value for p, dp in sim.tick().items()}
    for path in (vss.SPEED, vss.ACCEL_LONG, vss.TCS_ENGAGED, vss.LATITUDE, vss.LONGITUDE, vss.SOC,
                 vss.ODOMETER, vss.FLEET_ROUTE_ID, vss.FLEET_TRIP_ID):
        assert path in values
    assert values[vss.FLEET_ROUTE_ID] == "B"


def test_battery_drains_while_driving():
    sim = Simulator(VehicleConfig(route_id="A", speed_limit_kmh=60), Datapoint, random.Random(2))
    start_soc, start_odo = sim.soc_pct, sim.odometer_km
    for _ in range(60):
        sim.tick()
    assert sim.odometer_km > start_odo
    assert sim.soc_pct < start_soc


def test_trips_complete():
    sim = Simulator(VehicleConfig(route_id="A", speed_limit_kmh=60, time_scale=50), Datapoint, random.Random(2))
    for _ in range(400):
        sim.tick()
    assert sim.trip_id > 1


def test_route_geometry():
    for points in ROUTES.values():
        assert 3 < loop_length_km(points) < 30
        assert position_at(points, 0) == points[0]
