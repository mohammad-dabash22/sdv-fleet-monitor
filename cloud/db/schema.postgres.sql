-- PostgreSQL schema (same tables and columns as schema.sqlite.sql).
-- cloud/app/store.py runs it on every connect, so it must stay idempotent (IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS telemetry (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vehicle_id  TEXT    NOT NULL,
    route_id    TEXT,
    trip_id     INTEGER,
    ts_ms       BIGINT  NOT NULL,
    speed_kmh   DOUBLE PRECISION,
    lat         DOUBLE PRECISION,
    lon         DOUBLE PRECISION,
    soc_pct     DOUBLE PRECISION,
    engine_on   BOOLEAN,
    odometer_km DOUBLE PRECISION,
    hazard      TEXT
);
CREATE INDEX IF NOT EXISTS idx_telemetry_vehicle_ts ON telemetry (vehicle_id, ts_ms);

CREATE TABLE IF NOT EXISTS alerts (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vehicle_id   TEXT    NOT NULL,
    vehicle_name TEXT,
    route_id     TEXT,
    source       TEXT    NOT NULL,
    type         TEXT    NOT NULL,
    severity     INTEGER NOT NULL,
    detail       TEXT,
    lat          DOUBLE PRECISION,
    lon          DOUBLE PRECISION,
    t0_ms        BIGINT,
    ts_ms        BIGINT  NOT NULL,
    latency_ms   DOUBLE PRECISION,
    status       TEXT    NOT NULL DEFAULT 'active',
    acked_at_ms  BIGINT
);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts (status);

CREATE TABLE IF NOT EXISTS trips (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vehicle_id      TEXT    NOT NULL,
    route_id        TEXT    NOT NULL,
    trip_id         INTEGER,
    started_ms      BIGINT,
    ended_ms        BIGINT,
    distance_km     DOUBLE PRECISION,
    energy_used_pct DOUBLE PRECISION,
    hazards         INTEGER
);
