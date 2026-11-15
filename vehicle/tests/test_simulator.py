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


LIMITS = {"A": 60, "B": 50, "C": 70}   # config/fleet.json


def drive(route, seed, ticks):
    sim = Simulator(VehicleConfig(route_id=route, speed_limit_kmh=LIMITS[route]), Datapoint, random.Random(seed))
    return [{p: dp.value for p, dp in sim.tick().items()} for _ in range(ticks)]


def stopped_ticks(frames):
    return sum(1 for f in frames if f[vss.SPEED] < 2.0)   # the pipeline counts stop time below 2 km/h


def test_req_035_route_b_stops_longest():
    for seed in (1, 2, 3):
        stopped = {route: stopped_ticks(drive(route, seed, 4000)) for route in LIMITS}
        assert stopped["B"] > stopped["A"] and stopped["B"] > stopped["C"], (seed, stopped)


def test_req_035_stop_does_not_cause_harsh_braking(monkeypatch):
    import vehicle.simulator.main as sim_main
    calm = {**sim_main.PROFILES["B"], "harsh": 0.0, "traction": 0.0, "overspeed": 0.0, "stop": 0.05}
    monkeypatch.setitem(sim_main.PROFILES, "B", calm)
    frames = drive("B", 4, 2000)
    assert any(f[vss.SPEED] == 0.0 for f in frames[50:]), "the van never stopped"
    assert min(f[vss.ACCEL_LONG] for f in frames) > -4.0   # 4 m/s² is the harsh-braking threshold


def test_req_035_van_drives_on_after_a_stop(monkeypatch):
    import vehicle.simulator.main as sim_main
    monkeypatch.setitem(sim_main.PROFILES, "B", {**sim_main.PROFILES["B"], "stop": 0.05})
    speeds = [f[vss.SPEED] for f in drive("B", 5, 2000)]
    first_stop = next(i for i, s in enumerate(speeds) if i > 50 and s == 0.0)
    assert max(speeds[first_stop:]) > 30


def test_req_035_same_seed_same_stops():
    assert drive("B", 7, 1500) == drive("B", 7, 1500)


def test_route_geometry():
    for points in ROUTES.values():
        assert 3 < loop_length_km(points) < 30
        assert position_at(points, 0) == points[0]
