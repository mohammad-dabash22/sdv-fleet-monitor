from fakes.kuksa import Datapoint, VSSClient
from vehicle.common import vss
from vehicle.hazard_detector.main import Detector
from vehicle.hazard_rules import Thresholds


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def make_detector():
    client = VSSClient("test", 1)
    clock = FakeClock()
    det = Detector(client, Thresholds(speed_limit_kmh=50), Datapoint, clock=clock, wall_ms=lambda: 123456)
    return det, client, clock


def hazard(client):
    v = client.get_current_values(vss.HAZARD_PATHS)
    return {p: dp.value for p, dp in v.items()}


def test_hazard_is_written_back_with_t0():
    det, client, clock = make_detector()
    det.on_updates({vss.SPEED: Datapoint(45.0), vss.ACCEL_LONG: Datapoint(-6.0)})
    clock.t += 0.1
    det.step()
    h = hazard(client)
    assert h[vss.HAZARD_TYPE] == "HARSH_BRAKING"
    assert h[vss.HAZARD_SEVERITY] == 2
    assert h[vss.HAZARD_DETECTED_AT] == 123456


def test_waits_for_frame_to_settle():
    det, client, clock = make_detector()
    det.on_updates({vss.ACCEL_LONG: Datapoint(-6.0)})
    det.step()  # no time passed yet
    assert hazard(client) == {}


def test_hold_window_then_clear():
    det, client, clock = make_detector()
    det.on_updates({vss.ACCEL_LONG: Datapoint(-6.0)})
    clock.t += 0.1
    det.step()
    det.on_updates({vss.ACCEL_LONG: Datapoint(-0.5)})
    clock.t += 0.1
    det.step()
    assert hazard(client)[vss.HAZARD_TYPE] == "HARSH_BRAKING"  # still held
    clock.t += Detector.HOLD_S
    det.step()
    assert hazard(client)[vss.HAZARD_TYPE] == vss.NO_HAZARD
