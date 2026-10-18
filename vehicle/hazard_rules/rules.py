"""Hazard rules: pure functions, no Kuksa, no Zenoh, no clock.

The input is a "frame": a plain dict of the latest signal values, with short
names (the Detector maps VSS paths to these names):

    speed_kmh, accel_mps2, tcs_active, soc_pct, coolant_c

This module depends on nothing, so it is easy to unit test and does not
change when the real Databroker arrives.

NEXT PHASE: tune the default thresholds with the team, and add rules here
(each rule is one small function that returns a Finding or None).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

# Severity levels (0 means "no hazard")
WARNING = 1
HIGH = 2
CRITICAL = 3


@dataclass(frozen=True)
class Thresholds:
    harsh_brake_mps2: float = 4.0
    severe_brake_mps2: float = 7.0
    traction_min_speed_kmh: float = 20.0
    overspeed_margin_kmh: float = 10.0
    speed_limit_kmh: float = 50.0
    low_energy_pct: float = 20.0
    critical_energy_pct: float = 10.0
    coolant_max_c: float = 90.0


@dataclass(frozen=True)
class Finding:
    type: str
    severity: int
    detail: str


Frame = dict[str, Any]


def _harsh_braking(f: Frame, t: Thresholds) -> Finding | None:
    accel = f.get("accel_mps2")
    if accel is None:
        return None
    decel = -float(accel)
    if decel >= t.severe_brake_mps2:
        return Finding("HARSH_BRAKING", CRITICAL, f"Severe braking at {decel:.1f} m/s²")
    if decel >= t.harsh_brake_mps2:
        return Finding("HARSH_BRAKING", HIGH, f"Harsh braking at {decel:.1f} m/s²")
    return None


def _traction_loss(f: Frame, t: Thresholds) -> Finding | None:
    speed = f.get("speed_kmh") or 0.0
    if f.get("tcs_active") and speed >= t.traction_min_speed_kmh:
        return Finding("TRACTION_LOSS", CRITICAL, f"Traction control active at {speed:.0f} km/h")
    return None


def _overspeed(f: Frame, t: Thresholds) -> Finding | None:
    speed = f.get("speed_kmh")
    if speed is not None and speed > t.speed_limit_kmh + t.overspeed_margin_kmh:
        return Finding("OVERSPEED", WARNING, f"{speed:.0f} km/h in a {t.speed_limit_kmh:.0f} km/h zone")
    return None


def _low_energy(f: Frame, t: Thresholds) -> Finding | None:
    soc = f.get("soc_pct")
    if soc is None:
        return None
    if soc <= t.critical_energy_pct:
        return Finding("LOW_ENERGY", HIGH, f"Battery critical at {soc:.0f}%")
    if soc <= t.low_energy_pct:
        return Finding("LOW_ENERGY", WARNING, f"Battery low at {soc:.0f}%")
    return None


def _overheat(f: Frame, t: Thresholds) -> Finding | None:
    temp = f.get("coolant_c")
    if temp is not None and temp > t.coolant_max_c:
        return Finding("OVERHEAT", HIGH, f"Coolant at {temp:.0f} °C")
    return None


# Order matters only for ties in severity (first one wins).
RULES: list[Callable[[Frame, Thresholds], Finding | None]] = [
    _harsh_braking,
    _traction_loss,
    _overheat,
    _low_energy,
    _overspeed,
]


def evaluate(frame: Frame, thresholds: Thresholds) -> list[Finding]:
    """Run every rule and return all findings (may be empty)."""
    return [f for rule in RULES if (f := rule(frame, thresholds)) is not None]


def most_severe(findings: list[Finding]) -> Finding | None:
    best: Finding | None = None
    for f in findings:
        if best is None or f.severity > best.severity:
            best = f
    return best
