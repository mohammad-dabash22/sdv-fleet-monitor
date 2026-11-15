-- Used by the demo and the tests (SQLite in memory); GKE uses schema.postgres.sql.
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

-- ---------------------------------------------------------------- V1 data pipeline (spec REQ-032)
-- Written only by the Beam pipeline (cloud/pipeline/transforms.py), never by CloudService.

-- One row per completed trip. Keyed by van, trip id AND start time: trip ids start again at 1 when
-- a simulator restarts. A re-fired Beam pane overwrites its row instead of adding one.
CREATE TABLE IF NOT EXISTS trip_stats (
    vehicle_id        TEXT    NOT NULL,
    route_id          TEXT,
    trip_id           INTEGER NOT NULL,
    started_ms        INTEGER NOT NULL,
    ended_ms          INTEGER,
    samples           INTEGER,
    distance_km       REAL,
    energy_used_pct   REAL,
    energy_pct_per_km REAL,
    avg_speed_kmh     REAL,
    stop_time_s       REAL,
    hazards           INTEGER,
    hazards_per_100km REAL,
    processed_at_ms   INTEGER NOT NULL,
    PRIMARY KEY (vehicle_id, trip_id, started_ms)
);

-- One row per invalid message. id is a hash of the raw message, so a Pub/Sub redelivery or a batch
-- re-run of the same message does not add a second row.
CREATE TABLE IF NOT EXISTS quality_flags (
    id              TEXT    PRIMARY KEY,
    vehicle_id      TEXT,
    route_id        TEXT,
    kind            TEXT    NOT NULL,             -- telemetry | hazard
    problems        TEXT    NOT NULL,             -- comma-separated codes, e.g. OUT_OF_RANGE,LATE
    detail          TEXT,
    raw             TEXT    NOT NULL,
    record_ms       INTEGER,                      -- ts_ms or t0_ms of the message, if it had one
    processed_at_ms INTEGER NOT NULL
);

-- Route numbers are sums and ratios of trip numbers, so they are a view: one source, no double counting.
CREATE VIEW IF NOT EXISTS route_stats AS
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
