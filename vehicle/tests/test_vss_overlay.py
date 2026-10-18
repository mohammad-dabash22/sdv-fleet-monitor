import json
import re
from pathlib import Path

from vehicle.common import vss
from vehicle.hazard_rules import rules

OVERLAY = Path(__file__).resolve().parents[1] / "vss" / "fleet_overlay.json"


def _leaves(node: dict, prefix: str = "") -> dict:
    out = {}
    for name, entry in node.items():
        path = f"{prefix}.{name}" if prefix else name
        if entry.get("type") == "branch":
            out.update(_leaves(entry.get("children", {}), path))
        else:
            out[path] = entry
    return out


def test_overlay_defines_every_custom_path():
    """The Kuksa Databroker rejects unknown paths, so every Vehicle.Fleet/Hazard path we use must be here."""
    leaves = _leaves(json.loads(OVERLAY.read_text(encoding="utf-8")))
    custom = [v for k, v in vars(vss).items()
              if k.isupper() and isinstance(v, str) and v.startswith(("Vehicle.Fleet.", "Vehicle.Hazard."))]
    assert custom, "no overlay paths found in vehicle/common/vss.py"
    for path in custom:
        assert path in leaves, f"{path} is missing from {OVERLAY.name}"
        assert leaves[path].get("datatype"), f"{path} has no datatype"


def test_overlay_allows_every_hazard_type():
    """Hazard.Type has an allowed list, so a new rule type must be added to the overlay too."""
    leaves = _leaves(json.loads(OVERLAY.read_text(encoding="utf-8")))
    allowed = set(leaves[vss.HAZARD_TYPE]["allowed"])
    raised = set(re.findall(r'Finding\("([A-Z_]+)"', Path(rules.__file__).read_text(encoding="utf-8")))
    assert raised, "no Finding types found in hazard_rules/rules.py"
    assert vss.NO_HAZARD in allowed
    assert raised <= allowed, f"not allowed in {OVERLAY.name}: {sorted(raised - allowed)}"
