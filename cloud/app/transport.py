"""Open the cloud's Zenoh session (fake today, real Zenoh next phase).

This is the ONLY cloud file that knows whether the transport is fake.
The cloud never imports vehicle code: the keys below and the JSON shape are
the whole contract between the two halves.

NEXT PHASE:
    pip install eclipse-zenoh
    set TRANSPORT=zenoh and ZENOH_ENDPOINT=tcp/<router-ip>:7447
"""

from __future__ import annotations

import json
from typing import Any

TELEMETRY_KEYS = "fleet/*/telemetry"
HAZARD_KEYS = "fleet/*/hazards"


def open_session(transport: str, endpoint: str) -> Any:
    if transport == "fake":
        from fakes import zenoh as fake_zenoh
        return fake_zenoh.open()
    if transport == "zenoh":
        import zenoh  # type: ignore[import-not-found]
        conf = zenoh.Config()
        conf.insert_json5("connect/endpoints", json.dumps([endpoint]))
        return zenoh.open(conf)
    raise ValueError(f"Unknown TRANSPORT: {transport!r} (use 'fake' or 'zenoh')")
