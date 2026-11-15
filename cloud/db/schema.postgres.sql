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

-- ---------------------------------------------------------------- V1 data pipeline (spec REQ-032)
-- Same tables and columns as schema.sqlite.sql. Written only by the Beam pipeline.

CREATE TABLE IF NOT EXISTS trip_stats (
    vehicle_id        TEXT    NOT NULL,
    route_id          TEXT,
    trip_id           INTEGER NOT NULL,
    started_ms        BIGINT  NOT NULL,
    ended_ms          BIGINT,
    samples           INTEGER,
    distance_km       DOUBLE PRECISION,
    energy_used_pct   DOUBLE PRECISION,
    energy_pct_per_km DOUBLE PRECISION,
    avg_speed_kmh     DOUBLE PRECISION,
    stop_time_s       DOUBLE PRECISION,
    hazards           INTEGER,
    hazards_per_100km DOUBLE PRECISION,
    processed_at_ms   BIGINT  NOT NULL,
    PRIMARY KEY (vehicle_id, trip_id, started_ms)
);

CREATE TABLE IF NOT EXISTS quality_flags (
    id              TEXT    PRIMARY KEY,
    vehicle_id      TEXT,
    route_id        TEXT,
    kind            TEXT    NOT NULL,
    problems        TEXT    NOT NULL,
    detail          TEXT,
    raw             TEXT    NOT NULL,
    record_ms       BIGINT,
    processed_at_ms BIGINT  NOT NULL
);

-- PostgreSQL has no CREATE VIEW IF NOT EXISTS; CREATE OR REPLACE is just as idempotent.
CREATE OR REPLACE VIEW route_stats AS
SELECT route_id,
       COUNT(*)                                          AS trips,
       SUM(distance_km)                                  AS distance_km,
       SUM(energy_used_pct)                              AS energy_used_pct,
       SUM(energy_used_pct) / NULLIF(SUM(distance_km), 0) AS energy_pct_per_km,
       AVG(avg_speed_kmh)                                AS avg_speed_kmh,
       AVG(stop_time_s)                                  AS stop_time_s_per_trip,
       SUM(hazards)                                      AS hazards,
       SUM(hazards) * 100.0 / NULLIF(SUM(distance_km), 0) AS hazards_per_100km,
       MAX(processed_at_ms)                              AS updated_ms
FROM trip_stats
GROUP BY route_id;
