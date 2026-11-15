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

    def ping(self) -> None:
        """Raise if the database does not answer (the store keeps one connection and never reconnects)."""
        self._read("SELECT 1 AS ok", ())

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

    # ------------------------------------------------- pipeline (REQ-032)
    # Written by the Beam pipeline's sinks only; CloudService reads them for the route report.
    TRIP_COLUMNS = ("vehicle_id", "route_id", "trip_id", "started_ms", "ended_ms", "samples", "distance_km",
                    "energy_used_pct", "energy_pct_per_km", "avg_speed_kmh", "stop_time_s", "hazards",
                    "hazards_per_100km")
    FLAG_COLUMNS = ("id", "vehicle_id", "route_id", "kind", "problems", "detail", "raw", "record_ms")

    def upsert_trip_stats(self, t: dict, processed_at_ms: int) -> None:
        """One row per (van, trip id, start time); a re-fired pane overwrites it."""
        cols = self.TRIP_COLUMNS + ("processed_at_ms",)
        updates = ", ".join(f"{c} = excluded.{c}" for c in cols[4:])
        self._write(
            f"INSERT INTO trip_stats ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
            f" ON CONFLICT (vehicle_id, trip_id, started_ms) DO UPDATE SET route_id = excluded.route_id, {updates}",
            tuple(t.get(c) for c in self.TRIP_COLUMNS) + (processed_at_ms,),
        )

    def upsert_quality_flag(self, f: dict, processed_at_ms: int) -> None:
        """One row per distinct raw message (id = hash of it); the same message again is ignored."""
        cols = self.FLAG_COLUMNS + ("processed_at_ms",)
        self._write(
            f"INSERT INTO quality_flags ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
            " ON CONFLICT (id) DO NOTHING",
            tuple(f.get(c) for c in self.FLAG_COLUMNS) + (processed_at_ms,),
        )

    def trip_stats(self, limit: int = 20) -> list[dict]:
        return self._read("SELECT * FROM trip_stats ORDER BY ended_ms DESC LIMIT ?", (limit,))

    def route_stats(self) -> list[dict]:
        return self._read("SELECT * FROM route_stats ORDER BY route_id", ())

    def quality_flags(self, limit: int = 50) -> list[dict]:
        return self._read("SELECT * FROM quality_flags ORDER BY processed_at_ms DESC, id LIMIT ?", (limit,))

    def quality_flag_count(self) -> int:
        return self._read("SELECT COUNT(*) AS n FROM quality_flags", ())[0]["n"]

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


# --------------------------------------------- one Store per URL per process (REQ-033)
# A Beam sink carries only DATABASE_URL (it is pickled) and gets its Store here in setup().
# On the laptop the DirectRunner runs in the dashboard's process, so register_store() lets the
# sink write into the dashboard's own in-memory SQLite. On Dataflow nothing is registered, so
# each worker opens its own connection to PostgreSQL.
_stores: dict[str, Store] = {}
_stores_lock = threading.Lock()


def register_store(store: Store, url: str) -> None:
    with _stores_lock:
        _stores[url] = store


def store_for(url: str) -> Store:
    with _stores_lock:
        if url not in _stores:
            _stores[url] = Store(url)
        return _stores[url]


def _bool(v: Any) -> bool | None:
    return None if v is None else bool(v)
