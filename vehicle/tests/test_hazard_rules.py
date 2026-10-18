from vehicle.hazard_rules import CRITICAL, HIGH, WARNING, Thresholds, evaluate, most_severe

T = Thresholds(speed_limit_kmh=50)


def types(frame):
    return {f.type: f.severity for f in evaluate(frame, T)}


def test_normal_driving_has_no_hazard():
    assert evaluate({"speed_kmh": 45, "accel_mps2": -1.0, "tcs_active": False, "soc_pct": 80, "coolant_c": 70}, T) == []


def test_harsh_and_severe_braking():
    assert types({"accel_mps2": -5.0}) == {"HARSH_BRAKING": HIGH}
    assert types({"accel_mps2": -8.0}) == {"HARSH_BRAKING": CRITICAL}
    assert types({"accel_mps2": -3.9}) == {}


def test_traction_loss_needs_minimum_speed():
    assert types({"tcs_active": True, "speed_kmh": 40}) == {"TRACTION_LOSS": CRITICAL}
    assert types({"tcs_active": True, "speed_kmh": 10}) == {}


def test_overspeed_uses_route_limit_plus_margin():
    assert types({"speed_kmh": 61}) == {"OVERSPEED": WARNING}
    assert types({"speed_kmh": 60}) == {}


def test_energy_and_coolant():
    assert types({"soc_pct": 15}) == {"LOW_ENERGY": WARNING}
    assert types({"soc_pct": 8}) == {"LOW_ENERGY": HIGH}
    assert types({"coolant_c": 95}) == {"OVERHEAT": HIGH}


def test_most_severe_wins():
    findings = evaluate({"speed_kmh": 70, "tcs_active": True, "accel_mps2": -5}, T)
    assert most_severe(findings).type == "TRACTION_LOSS"
    assert most_severe([]) is None
