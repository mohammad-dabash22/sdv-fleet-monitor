-- Used TODAY by the mock (SQLite in memory, stand-in for PostgreSQL).
-- Keep it in step with schema.postgres.sql: same tables, same columns.

CREATE TABLE IF NOT EXISTS telemetry (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id  TEXT    NOT NULL,
    route_id    TEXT,
    trip_id     INTEGER,
    ts_ms       INTEGER NOT NULL,
    speed_kmh   REAL,
    lat         REAL,
    lon         REAL,
    soc_pct     REAL,
    engine_on   INTEGER,
    odometer_km REAL,
    hazard      TEXT
);
CREATE INDEX IF NOT EXISTS idx_telemetry_vehicle_ts ON telemetry (vehicle_id, ts_ms);

CREATE TABLE IF NOT EXISTS alerts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id   TEXT    NOT NULL,
    vehicle_name TEXT,
    route_id     TEXT,
    source       TEXT    NOT NULL,          -- 'edge' (from the vehicle) or 'cloud'
    type         TEXT    NOT NULL,
    severity     INTEGER NOT NULL,
    detail       TEXT,
    lat          REAL,
    lon          REAL,
    t0_ms        INTEGER,                   -- detected on the vehicle
    ts_ms        INTEGER NOT NULL,          -- t1: arrived in the cloud
    latency_ms   REAL,                      -- t1 - t0
    status       TEXT    NOT NULL DEFAULT 'active',   -- active | acked | cleared
    acked_at_ms  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts (status);

CREATE TABLE IF NOT EXISTS trips (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    vehicle_id      TEXT    NOT NULL,
    route_id        TEXT    NOT NULL,
    trip_id         INTEGER,
    started_ms      INTEGER,
    ended_ms        INTEGER,
    distance_km     REAL,
    energy_used_pct REAL,
    hazards         INTEGER
);
