"""Store: ALL database code lives here (tables: telemetry, alerts, trips).

DATABASE_URL picks the database:
    sqlite:///:memory:                          the default: the demo and tests need nothing installed
    postgresql://user:password@host:5432/fleet  PostgreSQL; the tables are created on connect

The SQL is plain and works in both. Queries are written with "?" and turned into
"%s" for PostgreSQL, so no SQL text may contain a "?" or "%" of its own.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA_SQLITE = Path(__file__).resolve().parents[1] / "db" / "schema.sqlite.sql"
SCHEMA_POSTGRES = Path(__file__).resolve().parents[1] / "db" / "schema.postgres.sql"


class Store:
    def __init__(self, url: str = "sqlite:///:memory:") -> None:
        self.lock = threading.Lock()
        self.param = "?"
        self.postgres = False
        self.db = self._connect(url)

    def _connect(self, url: str) -> Any:
        if url.startswith("sqlite:///"):
            db = sqlite3.connect(url.removeprefix("sqlite:///"), check_same_thread=False)
            db.row_factory = sqlite3.Row
            db.executescript(SCHEMA_SQLITE.read_text(encoding="utf-8"))
            return db
        if url.startswith(("postgresql://", "postgres://")):
            import psycopg2  # type: ignore[import-untyped]
            import psycopg2.extras  # type: ignore[import-untyped]
            db = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
            db.autocommit = True
            with db.cursor() as cur:
                cur.execute(SCHEMA_POSTGRES.read_text(encoding="utf-8"))  # CREATE ... IF NOT EXISTS
            self.param, self.postgres = "%s", True
            return db
        raise ValueError(f"Unsupported DATABASE_URL: {url!r} (use sqlite:/// or postgresql://)")

    # ------------------------------------------------------------ telemetry
    def add_telemetry(self, m: dict) -> None:
        self._write(
            "INSERT INTO telemetry (vehicle_id, route_id, trip_id, ts_ms, speed_kmh, lat, lon, soc_pct,"
            " engine_on, odometer_km, hazard) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (m.get("vehicle_id"), m.get("route_id"), m.get("trip_id"), m.get("ts_ms") or _now_ms(),
             m.get("speed_kmh"), m.get("lat"), m.get("lon"), m.get("soc_pct"),
             _bool(m.get("engine_on")), m.get("odometer_km"), m.get("hazard")),
        )

    def history(self, vehicle_id: str, since_ts: int) -> list[dict]:
        return self._read(
            "SELECT ts_ms, speed_kmh, lat, lon, soc_pct, odometer_km, hazard FROM telemetry"
            " WHERE vehicle_id = ? AND ts_ms >= ? ORDER BY ts_ms",
            (vehicle_id, since_ts),
        )

    # --------------------------------------------------------------- alerts
    def add_alert(self, a: dict) -> int:
        return self._write(
            "INSERT INTO alerts (vehicle_id, vehicle_name, route_id, source, type, severity, detail,"
            " lat, lon, t0_ms, ts_ms, latency_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (a["vehicle_id"], a.get("vehicle_name"), a.get("route_id"), a["source"], a["type"],
             a.get("severity", 0), a.get("detail"), a.get("lat"), a.get("lon"), a.get("t0_ms"),
             a["ts_ms"], a.get("latency_ms")),
            returning_id=True,
        )

    def clear_alerts(self, vehicle_id: str, ts: int, source: str, type_: str) -> int:
        """Mark older ACTIVE alerts of this vehicle/source/type as cleared. Returns how many."""
        return self._write(
            "UPDATE alerts SET status = 'cleared' WHERE vehicle_id = ? AND source = ? AND type = ?"
            " AND status = 'active' AND ts_ms <= ?",
            (vehicle_id, source, type_, ts), rowcount=True,
        )

    def ack_alert(self, alert_id: int) -> bool:
        return self._write(
            "UPDATE alerts SET status = 'acked', acked_at_ms = ? WHERE id = ? AND status <> 'acked'",
            (_now_ms(), alert_id), rowcount=True,
        ) > 0

    def get_alert(self, alert_id: int) -> dict | None:
        rows = self._read("SELECT * FROM alerts WHERE id = ?", (alert_id,))
        return rows[0] if rows else None

    def recent_alerts(self, limit: int = 50) -> list[dict]:
        return self._read("SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,))

    def active_alert_count(self) -> int:
        return self._read("SELECT COUNT(*) AS n FROM alerts WHERE status = 'active'", ())[0]["n"]

    def latencies(self) -> list[float]:
        rows = self._read("SELECT latency_ms FROM alerts WHERE source = 'edge' AND latency_ms IS NOT NULL", ())
        return [r["latency_ms"] for r in rows]

    # ---------------------------------------------------------------- trips
    def add_trip(self, t: dict) -> None:
        self._write(
            "INSERT INTO trips (vehicle_id, route_id, trip_id, started_ms, ended_ms, distance_km,"
            " energy_used_pct, hazards) VALUES (?,?,?,?,?,?,?,?)",
            (t["vehicle_id"], t["route_id"], t.get("trip_id"), t.get("started_ms"), t.get("ended_ms"),
             t.get("distance_km"), t.get("energy_used_pct"), t.get("hazards", 0)),
        )

    def recent_trips(self, limit: int = 20) -> list[dict]:
        return self._read("SELECT * FROM trips ORDER BY id DESC LIMIT ?", (limit,))

    def route_summary(self) -> list[dict]:
        """Per route: completed trips joined with hazard counts."""
        return self._read(
            """
            SELECT r.route_id,
                   (SELECT COUNT(*) FROM trips t WHERE t.route_id = r.route_id) AS trips,
                   (SELECT COALESCE(SUM(distance_km), 0) FROM trips t WHERE t.route_id = r.route_id) AS distance_km,
                   (SELECT COALESCE(SUM(hazards), 0) FROM trips t WHERE t.route_id = r.route_id) AS trip_hazards,
                   (SELECT AVG(energy_used_pct) FROM trips t WHERE t.route_id = r.route_id) AS avg_energy_pct,
                   (SELECT COUNT(*) FROM alerts a WHERE a.route_id = r.route_id AND a.source = 'edge') AS hazard_alerts
            FROM (SELECT route_id FROM trips UNION SELECT route_id FROM alerts WHERE route_id IS NOT NULL) r
            ORDER BY r.route_id
            """,
            (),
        )

    # -------------------------------------------------------------- helpers
    def _write(self, sql: str, params: tuple, rowcount: bool = False, returning_id: bool = False) -> int:
        """Run an INSERT/UPDATE. Returns the row count, or the new row's id for an INSERT."""
        sql = sql.replace("?", self.param)
        if returning_id and self.postgres:
            sql += " RETURNING id"  # psycopg2 has no lastrowid for identity columns
        with self.lock:
            cur = self.db.cursor()
            try:
                cur.execute(sql, params)
                if rowcount:
                    result = cur.rowcount
                elif returning_id and self.postgres:
                    result = cur.fetchone()["id"]
                else:
                    result = cur.lastrowid or 0
                self.db.commit()  # PostgreSQL runs in autocommit mode, so this is a no-op there
                return result
            finally:
                cur.close()

    def _read(self, sql: str, params: tuple) -> list[dict]:
        with self.lock:
            cur = self.db.cursor()
            try:
                cur.execute(sql.replace("?", self.param), params)
                return [dict(row) for row in cur.fetchall()]
            finally:
                cur.close()


def _now_ms() -> int:
    return int(time.time() * 1000)


def _bool(v: Any) -> bool | None:
    return None if v is None else bool(v)
