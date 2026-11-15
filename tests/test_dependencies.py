"""REQ-023 (D-17): the dependencies are split into a vehicle set and a cloud set.

apache-beam needs protobuf < 7 and kuksa-client 0.6.0 needs protobuf >= 7.35.1, so the two can
never be installed together. These tests guard the split: the files say which set a package is
in, and only vehicle code may import kuksa_client.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The only files allowed to import kuksa_client (both import it lazily, for the real Databroker).
KUKSA_IMPORTERS = {"vehicle/common/databroker.py", "tools/inject_hazards.py"}
SKIP_DIRS = {".venv", "sdd", ".git", "node_modules"}


def requirements(name: str) -> dict[str, str]:
    """Package name -> full requirement line, following "-r other.txt" includes."""
    out: dict[str, str] = {}
    for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("-r "):
            out.update(requirements(line[3:].strip()))
            continue
        package = re.split(r"[\[<>=!~; ]", line, maxsplit=1)[0].lower()
        out[package] = line
    return out


def test_req_023_requirements_are_split():
    vehicle = requirements("requirements-vehicle.txt")
    cloud = requirements("requirements.txt")
    dev = requirements("requirements-dev.txt")

    assert {"kuksa-client", "eclipse-zenoh"} <= vehicle.keys()
    assert not {"fastapi", "apache-beam", "google-cloud-pubsub", "psycopg2-binary"} & vehicle.keys()

    assert {"fastapi", "uvicorn", "eclipse-zenoh", "psycopg2-binary",
            "apache-beam", "google-cloud-pubsub"} <= cloud.keys()
    assert "kuksa-client" not in cloud
    assert cloud["apache-beam"] == "apache-beam[gcp]==2.77.0"  # pinned: unpinned, pip backtracks for minutes

    assert cloud.items() <= dev.items()          # the tests run on the cloud set
    assert vehicle["eclipse-zenoh"] == cloud["eclipse-zenoh"]  # both halves must match the router version


def test_req_023_only_vehicle_code_imports_kuksa_client():
    importers = set()
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if rel.parts[0] in SKIP_DIRS or path == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"^\s*(from|import)\s+kuksa_client\b", text, re.MULTILINE):
            importers.add(rel.as_posix())
    assert importers == KUKSA_IMPORTERS
