"""Cloud service configuration (environment variables with safe defaults)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class CloudConfig:
    transport: str = "fake"                     # fake | zenoh
    zenoh_endpoint: str = "tcp/127.0.0.1:7447"
    # Today: SQLite in memory (stand-in for PostgreSQL, nothing to install).
    # NEXT PHASE: postgresql://user:password@host:5432/fleet
    database_url: str = "sqlite:///:memory:"
    fleet_config: str = str(ROOT / "config" / "fleet.json")
    offline_after_s: float = 10.0
    host: str = "127.0.0.1"
    port: int = 8000

    @classmethod
    def from_env(cls) -> "CloudConfig":
        env = os.environ.get
        return cls(
            transport=env("TRANSPORT", cls.transport),
            zenoh_endpoint=env("ZENOH_ENDPOINT", cls.zenoh_endpoint),
            database_url=env("DATABASE_URL", cls.database_url),
            fleet_config=env("FLEET_CONFIG", cls.fleet_config),
            offline_after_s=float(env("OFFLINE_AFTER_S", cls.offline_after_s)),
            host=env("HOST", cls.host),
            port=int(env("PORT", cls.port)),
        )
