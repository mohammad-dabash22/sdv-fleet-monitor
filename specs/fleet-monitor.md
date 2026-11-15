# Spec: SDV Fleet Monitor, V1

| | |
|---|---|
| Status | **Approved** by the user on 2026-11-14; open questions answered the same day (D-15, D-16); dependency split added while planning (D-17) |
| Date | 2026-11-14 |
| Baseline | MVP at commit `4c21d13` (branch `v1/sdd`): 34 tests pass |
| Sources | `docs/requirements/srs.md` (SRS v1.0, `FR-x` / `NFR-x`), `docs/requirements/charter.md` (Charter v2), `README.md`, the code |
| Skills used | `grilling` (questions D-1 to D-9), `spec-driven-development` (proposals D-10 to D-14, this file) |

This spec does two things:

1. It describes **what the MVP already does**, one REQ per behavior, so every later change has a baseline to diff against.
2. It defines the **V1 scope**: a Google Pub/Sub + Apache Beam (Dataflow) data pipeline (required by the course rubric) and the fixes chosen in the decisions log (section 9).

Status of each REQ:

- **Done**: in the MVP, works as described.
- **Partial**: in the MVP, but part of the SRS/charter requirement is missing (the gap is stated).
- **New in V1**: does not exist yet.
- **Changed in V1** / **Replaced in V1**: in the MVP, and V1 changes it (the REQ that changes it is named).

---

## 1. Objective

Maria, a fleet operator at a small delivery company, watches three electric vans on fixed routes in Oshawa (charter section 3).
She needs to (a) see every safety hazard within 2 seconds, and (b) see at the end of the week which route is both the least
efficient and the least safe, from data she can trust.

The MVP delivers (a): live map, alert queue and measured hazard latency (p95 65 ms on GCP, README).
V1 delivers (b) through a data pipeline: raw vehicle data goes to Google Pub/Sub, an Apache Beam pipeline checks its quality
(FR-10) and computes route efficiency and safety per trip (FR-12), the results land in PostgreSQL, and the dashboard shows them as
a route report. The live path stays as fast as it is.

**V1 is done when** every REQ marked *New in V1* or *Changed in V1* meets its acceptance criteria, all tests pass in CI, and the
runtime evidence in section 7 exists.

## 2. Assumptions

1. The three vans, their routes and speed limits stay as in `config/fleet.json`.
2. GCP project, GKE cluster, `sdv-vehicles` VM and Jenkins from the MVP stay; V1 adds to them and removes nothing.
3. Python 3.11+ everywhere (CI 3.11, Jenkins 3.12, laptops 3.12). `apache-beam[gcp]` supports these versions.
   `apache-beam` 2.77.0 needs `protobuf < 7` and `kuksa-client` 0.6.0 needs `protobuf >= 7.35.1`, so they cannot share one
   environment; the dependencies are split into a vehicle set and a cloud set (D-17, REQ-023).
4. Dataflow runs in the same region as GKE (`us-central1`) and only during demos and measurements (D-3), so credits last.
5. The message JSON shapes in REQ-007 are the contract; the pipeline reads them unchanged.
6. The SRS and charter are not edited (CLAUDE.md); every difference is listed in section 8.

## 3. Capability map

The user asked for one spec file, so the capability map from `spec-driven-development` Phase 0 lives here instead of in separate
files. Module ids are stable; REQs are grouped by them.

| Module id | Responsibility | Depends on | REQs |
|---|---|---|---|
| `vehicle` | Simulator, Kuksa twin, hazard detection, cloud publisher, Ankaios | none | 001-008, 035 |
| `cloud-live` | Zenoh ingestion, live twins, alerts, latency, API, PostgreSQL store | `vehicle` (contract REQ-007) | 009-015, 028, 029, 038 |
| `dashboard` | Web UI for Maria | `cloud-live` (API) | 016-020, 034 |
| `pipeline` | Pub/Sub bridge, Beam quality checks and route stats, sample data | `vehicle` (contract), `cloud-live` (store, `validate()`) | 027, 030-033, 036, 041 |

`validate()` (REQ-028) lives on the cloud side (`cloud/quality.py`) and is used by both `cloud-live` and `pipeline`.
| `devops` | CI, CD, containers, tests, demo, docs hygiene | all | 021-026, 037, 039, 040 |

V1 build order: shared `validate()` (REQ-028) → bridge (REQ-027) → Beam transforms (REQ-030, 031) → tables (REQ-032) →
runners (REQ-033) → route report (REQ-034) → delivery stops (REQ-035) and sample data (REQ-036) → deployment (REQ-037) → docs
(REQ-041). The small fixes (REQ-038, 039, 040) are independent and can go first.

```
                ┌──────────── live path (unchanged, ~58 ms) ────────────┐
van ──Zenoh──► Zenoh router ──► CloudService ──► PostgreSQL ──► dashboard
                    │            (validate: reject bad telemetry)  ▲
                    │                                              │ /api/routes
                    └──► bridge ──► Pub/Sub ──► Beam ──► trip_stats, route_stats, quality_flags
                         (raw copy)   (2 topics)  (validate: flag;   (same PostgreSQL)
                                                   trip/route stats)
                └──────────── analytics path (new, seconds are fine) ───┘
```

---

## 4. Requirements: what the MVP does today

Test names are the existing ones in `vehicle/tests/`, `cloud/tests/` and `tests/`.

### Module `vehicle`

**REQ-001 Simulated fleet** · Done · FR-1, NFR-7
The system simulates three vans (Van 01 on Route A, Van 02 on B, Van 03 on C) driving closed loops in Oshawa; one loop is one trip.
- AC1: `config/fleet.json` defines the vans and routes; adding a van is one line there plus `python -m tools.ankaios_manifest`.
- AC2: Each van gets its own route profile; Route B (downtown) has the highest harsh-braking and traction chances.
- AC3: The same `--seed` gives the same drive.
- AC4: The trip counter goes up by one each time the van passes the depot.
- Code: `config/fleet.json`, `vehicle/simulator/main.py`, `vehicle/simulator/routes.py`
- Tests: `test_tick_writes_all_signals`, `test_trips_complete`, `test_route_geometry`, `test_every_van_gets_its_own_agent_and_port`

**REQ-002 Digital twin in Kuksa (VSS)** · Done · FR-2
Each van has its own Kuksa Databroker 0.6.0 holding VSS 5.1 plus our overlay (`Vehicle.Fleet.*`, `Vehicle.Hazard.*`).
- AC1: Every custom path used in `vehicle/common/vss.py` is defined in `vehicle/vss/fleet_overlay.json`.
- AC2: The overlay's `Vehicle.Hazard.Type` allows every hazard type the rules can produce.
- AC3: Every standard path in `vss.py` exists in VSS 5.1.
- Code: `vehicle/common/vss.py`, `vehicle/vss/fleet_overlay.vspec`, `vehicle/vss/fleet_overlay.json`, `vehicle/common/databroker.py`, `deploy/docker/databroker.Dockerfile`, `deploy/kuksa/docker-compose.yml`
- Tests: `test_overlay_defines_every_custom_path`, `test_overlay_allows_every_hazard_type`; AC3 no test yet (checked by hand against the Databroker in the README run)

**REQ-003 Twin signals updated** · Done · FR-3
Every 0.5 s the simulator writes speed, acceleration, TCS state, latitude, longitude, battery state of charge, odometer, power
state (engine status), coolant temperature, vehicle id, route id and trip id into the van's Databroker.
- AC1: One tick writes all twelve signals.
- AC2: The battery drains while driving; it is recharged to 100% at the depot when it ended a trip below 35%.
- Note: engine status (`Vehicle.LowVoltageSystemState`) is always `"ON"`; the vans never switch off.
- Code: `vehicle/simulator/main.py`
- Tests: `test_tick_writes_all_signals`, `test_battery_drains_while_driving`

**REQ-004 Hazard rules** · Done · FR-4
Pure rules (no I/O) turn a frame of signal values into findings; the most severe finding wins (first rule on ties).

| Hazard | Fires when | Severity |
|---|---|---|
| HARSH_BRAKING | deceleration ≥ 4.0 m/s² (≥ 7.0 m/s² is critical) | high (critical) |
| TRACTION_LOSS | TCS engaged at ≥ 20 km/h | critical |
| OVERSPEED | speed > route limit + 10 km/h | warning |
| LOW_ENERGY | battery ≤ 20% (≤ 10% is high) | warning (high) |
| OVERHEAT | coolant > 90 °C | high |

- AC1: Each row of the table holds, including the thresholds.
- AC2: Normal driving gives no finding.
- Note (D-13): OVERHEAT and LOW_ENERGY are tested at rule level but **the simulator never produces them** (coolant is capped at
  85 °C; a van is recharged at 35% and a trip uses about 3-4%). FR-4 only requires harsh braking and traction loss.
- Code: `vehicle/hazard_rules/rules.py`
- Tests: `test_normal_driving_has_no_hazard`, `test_harsh_and_severe_braking`, `test_traction_loss_needs_minimum_speed`, `test_overspeed_uses_route_limit_plus_margin`, `test_energy_and_coolant`, `test_most_severe_wins`

**REQ-005 Hazard detector** · Done · FR-4, FR-5, NFR-1
The HazardDetector subscribes to the five input signals, waits until the frame settles, runs the rules and writes the most severe
finding back into Kuksa as `Vehicle.Hazard.*`, with the detection time t0.
- AC1: A new hazard is written with type, severity, detail and `DetectedAt` = t0 (Unix ms); critical hazards also switch the hazard lights on.
- AC2: Rules run only after 50 ms without new updates (the frame has settled).
- AC3: A hazard stays active for at least 1.5 s, then is cleared to `NONE` / 0 if no rule fires.
- AC4: The same hazard is not re-written while it stays active, unless its severity rises.
- Code: `vehicle/hazard_detector/main.py`
- Tests: `test_hazard_is_written_back_with_t0`, `test_waits_for_frame_to_settle`, `test_hold_window_then_clear`; AC4 no test yet

**REQ-006 Cloud publisher** · Done · FR-5, FR-7
The CloudPublisher (`Bridge` class) reads the twin and sends telemetry on a timer and hazards right away.
- AC1: Telemetry is sent once per second (`TELEMETRY_HZ`).
- AC2: A hazard is sent once, 50 ms after its signals change, as one complete event.
- AC3: A hazard that was already active when the publisher started is not sent again (no stale t0).
- Code: `vehicle/cloud_publisher/main.py`, `vehicle/common/transport.py`
- Tests: `test_hazard_event_is_sent_once`, `test_hazard_active_before_start_is_not_resent`; AC1 no test yet

**REQ-007 Vehicle-to-cloud contract** · Done, **Changed in V1** · FR-7, NFR-7
The two halves share only two Zenoh keys and two JSON shapes; they never import each other.

| Key | Fields |
|---|---|
| `fleet/{vehicle_id}/telemetry` | `vehicle_id`, `route_id`, `trip_id`, `ts_ms`, `speed_kmh`, `lat`, `lon`, `soc_pct`, `engine_on`, `odometer_km`, `hazard_lights`, `hazard` |
| `fleet/{vehicle_id}/hazards` | `vehicle_id`, `route_id`, `type`, `severity`, `detail`, `lat`, `lon`, `speed_kmh`, `t0_ms` |

- AC1: The telemetry message has exactly the fields above.
- AC2 (**V1**): The hazard event also carries `trip_id`, so Beam can count hazards per trip (REQ-031). The field is optional
  for readers, so an old publisher still works.
- AC3 (**V1**): Both shapes are written down as JSON Schema files in `cloud/pipeline/schemas/` and the publisher's messages
  validate against them.
- Code: `vehicle/cloud_publisher/main.py`, `vehicle/common/transport.py`, `cloud/app/transport.py`
- Tests: `test_snapshot_shape`; AC2 and AC3 no test yet

**REQ-008 Vehicle software managed by Ankaios** · Partial · FR-6, NFR-5
Ankaios 1.0.4 runs each van's workloads (Databroker, simulator, detector, publisher) on the `sdv-vehicles` VM, one agent per van.
- AC1: `deploy/ankaios/state.yaml` is generated from `config/fleet.json` and is up to date.
- AC2: Each van has its own agent and Databroker port; with `--zenoh` each van also gets a publisher.
- AC3: Every workload has `restartPolicy: ALWAYS`; systemd brings the fleet back after a VM restart.
- Gap: FR-6 also says "update". Updating means editing the manifest and applying it by hand; there is no remote update flow
  (charter: "Remote software update", Could, Phase 2). Not in V1.
- Code: `tools/ankaios_manifest.py`, `deploy/ankaios/*`
- Tests: `test_state_yaml_is_up_to_date`, `test_every_van_gets_its_own_agent_and_port`, `test_zenoh_adds_a_publisher_per_van`; AC3 checked on the VM only

### Module `cloud-live`

**REQ-009 Ingestion** · Done, **Changed in V1** · FR-8
CloudService subscribes to `fleet/*/telemetry` and `fleet/*/hazards`, updates the twin of each known van and turns hazards into alerts.
- AC1: Messages from a vehicle not in `config/fleet.json` are discarded.
- AC2: Messages that are not valid JSON are ignored without crashing the service.
- AC3: Telemetry updates the van's twin (speed, position, battery, trip, odometer, online).
- AC4 (**V1**): Telemetry that fails `validate()` is rejected (REQ-029).
- Code: `cloud/app/main.py`, `cloud/app/analytics.py`, `cloud/app/transport.py`
- Tests: `test_unknown_vehicle_is_discarded`, `test_telemetry_updates_twin`; AC2 no test yet

**REQ-010 Storage in PostgreSQL** · Done, **Changed in V1** · FR-9
`Store` holds all database code; `DATABASE_URL` picks PostgreSQL (GCP) or SQLite in memory (demo and tests).
- AC1: Telemetry and alerts are stored; the schema is created on connect and is idempotent.
- AC2: The same SQL runs on SQLite and PostgreSQL; the store tests run on both in GitHub Actions.
- AC3 (**V1**): The `trips` table is replaced by the pipeline tables (REQ-032).
- Code: `cloud/app/store.py`, `cloud/db/schema.sqlite.sql`, `cloud/db/schema.postgres.sql`, `deploy/k8s/fleet-db.yaml`
- Tests: `test_alert_lifecycle`, `test_route_summary_joins_trips_and_alerts`, `test_telemetry_history` (each on SQLite, and on PostgreSQL when `TEST_DATABASE_URL` is set)

**REQ-011 Hazard latency** · Done · NFR-1, charter section 2
Each edge alert records t1 (arrival in the cloud) and latency = t1 − t0.
- AC1: `/api/latency` returns count, median, p95 (nearest rank), max, % under target, and pass = p95 < 2000 ms.
- AC2: A hazard written into a van's Databroker reaches `/api/alerts` in under 2 s, tagged with route and location.
- AC3: On GCP, over ≥ 50 injected hazards, p95 < 2000 ms (README, 2026-10-19: 64 hazards, median 58 ms, p95 65 ms, max 66 ms).
- Code: `cloud/app/analytics.py` (`ingest_hazard`, `latency_stats`), `cloud/app/main.py`
- Tests: `test_hazard_creates_alert_with_latency`, `test_latency_stats`, `test_hazard_reaches_cloud_within_two_seconds`; AC3 is runtime evidence

**REQ-012 Alert lifecycle** · Done · FR-15
- AC1: A new alert is `active`; acknowledging sets `acked` and the ack time; acknowledging an unknown id returns 404.
- AC2: A new edge alert of the same vehicle and type marks the older active one `cleared`.
- AC3: `/api/alerts` returns the active count and the newest alerts first.
- Code: `cloud/app/main.py`, `cloud/app/store.py`
- Tests: `test_alert_lifecycle`, `test_hazard_flows_to_alerts_and_can_be_acked`

**REQ-013 Cloud-side rules** · Partial · FR-11
- AC1: A van with no telemetry for 10 s gets an `OFFLINE` alert and shows offline; the alert clears when data comes back.
- AC2: A battery drop of more than 3% in one sample gives an `ENERGY_DROP` alert.
- Gap: FR-11 (anomaly detection on stored data) is Phase 2; these are two live rules only. More anomaly detection is V2 (D-4).
- Code: `cloud/app/analytics.py`
- Tests: `test_offline_then_back_online`; AC2 no test yet

**REQ-014 Trip tracking and route summary in CloudService** · Done, **Replaced in V1** by REQ-031, 032, 034 · FR-12 (partial), FR-16
- AC1: After a van's first full trip, a trip row is stored with distance, battery % used and hazards; the first, partly seen trip is skipped.
- AC2: `/api/routes` joins trips and edge alerts per route: trips, distance, hazards per 100 km, average battery % per trip, hazard alerts.
- V1 (D-5): trip tracking leaves CloudService; Beam becomes the only source of trip and route numbers. The two tests below are
  replaced by REQ-031 and REQ-034 tests (spec first, then tests, then code).
- Code: `cloud/app/analytics.py` (`TripTracker`, `_track_trip`), `cloud/app/store.py` (`add_trip`, `route_summary`)
- Tests: `test_trip_result_after_first_full_trip`, `test_route_summary_joins_trips_and_alerts`

**REQ-015 REST API and WebSocket** · Done · FR-14, FR-15, FR-16, SRS 5.3
- AC1: `GET /api/health`, `/api/fleet`, `/api/alerts`, `/api/latency`, `/api/routes`, `/api/trips`, `/api/history/{vehicle_id}`; `POST /api/alerts/{id}/ack`.
- AC2: `/ws` first sends a snapshot of all twins and the transport, then live events: `twin`, `alert`, `alerts_changed`, `trip`.
- Code: `cloud/app/main.py`
- Tests: `test_health_and_fleet`, `test_hazard_flows_to_alerts_and_can_be_acked`, `test_websocket_sends_snapshot_then_live_twin`; `/api/trips` and `/api/history` no test yet

### Module `dashboard`

The dashboard is plain JavaScript (`cloud/app/static/`). No UI tests exist; `test_health_and_fleet` only checks that `/` loads.
UI behavior is checked by hand (demo script in the README).

**REQ-016 Live map** · Done · FR-14, NFR-3
- AC1: The three vans move on an OpenStreetMap of Oshawa with a short trail in their route colour.
- AC2: Each edge hazard leaves a dot coloured by severity (yellow warning, orange high, red critical); a van with an active hazard pulses red.
- Code: `cloud/app/static/app.js`, `index.html`, `style.css` · Tests: no test yet (manual)

**REQ-017 Fleet panel** · Done · FR-3, FR-16, NFR-3
- AC1: Per van: name, route, speed, battery (bar turns red under 25%), trip number, odometer, and an Online / Offline / hazard chip.
- AC2: The header shows vans online and active alerts, a "Mock data" badge when the transport is fake, and Live / Reconnecting.
- Code: `cloud/app/static/*` · Tests: no test yet (manual)

**REQ-018 Alerts panel** · Done · FR-15, NFR-3
- AC1: Active alerts appear newest first with type, van, route, detail, time ago, latency and source; "Show resolved" also shows old ones.
- AC2: Clicking Acknowledge acknowledges the alert; high and critical alerts pop up for 5 s.
- Code: `cloud/app/static/*` · Tests: no test yet (manual)

**REQ-019 Latency panel** · Done · NFR-1, charter "Latency measurement"
- AC1: Shows count, median, p95, max and a Pass/Fail verdict against p95 < 2 s.
- Code: `cloud/app/static/*` · Tests: no test yet (manual)

**REQ-020 Route performance panel** · Done, **Changed in V1** by REQ-034 · FR-16
- AC1 (MVP): Per route: trips, distance, hazards per 100 km, average battery per trip, hazard alerts; the worst route is highlighted.
- Code: `cloud/app/static/*` · Tests: no test yet (manual)

### Module `devops`

**REQ-021 CI on GitHub Actions** · Done · FR-19, NFR-6
- AC1: Every pull request and push to `main` runs all tests on Python 3.11, with a real PostgreSQL 16 for the store tests.
- Code: `.github/workflows/ci.yml` · Evidence: GitHub Actions runs on PRs #1-#10

**REQ-022 CD with Jenkins on GKE** · Done · FR-18, NFR-6
- AC1: A new commit on `main` (webhook, or poll every 2 min) runs: test → build the image with Cloud Build → roll out the CI/CD
  database, the mock dashboard, the fleet PostgreSQL and the real cloud (Zenoh router + CloudService) → record the deployment → print the public URLs.
- AC2: Images are tagged with the build number, never `:latest` (except the CI/CD database image, on purpose).
- Note: the Jenkins test stage has no PostgreSQL, so the PostgreSQL store tests only run in GitHub Actions.
- Code: `Jenkinsfile`, `cloudbuild.yaml`, `deploy/k8s/*`, `deploy/jenkins/values.yaml`, `deploy/cicd-db/*` · Evidence: Jenkins build history, `deployments` table

**REQ-023 Containers and dependencies** · Done, **Changed in V1** · NFR-4 · D-17
- AC1: Databroker, vehicle apps and dashboard/cloud each have a Dockerfile; the vehicle image runs any vehicle app by its command.
- AC2 (**V1**): the dependencies are split by half, because `apache-beam` and `kuksa-client` need incompatible `protobuf` versions:

| File | Packages | Used by |
|---|---|---|
| `requirements-vehicle.txt` | `kuksa-client`, `eclipse-zenoh` | vehicle image (Ankaios VM), `tools.inject_hazards` |
| `requirements-cloud.txt` | `fastapi`, `uvicorn`, `eclipse-zenoh`, `psycopg2-binary` | everything on the cloud side |
| `requirements-pipeline.txt` | `apache-beam[gcp]`, `google-cloud-pubsub` | the bridge and the Beam pipeline |
| `requirements.txt` | `-r requirements-cloud.txt` and `-r requirements-pipeline.txt` | default laptop demo, cloud/dashboard image, CI (through `requirements-dev.txt`) |

- AC3 (**V1**): `pip install -r requirements.txt` and `pip install -r requirements-vehicle.txt` each succeed in a fresh venv, and
  the vehicle image no longer contains the cloud packages.
- AC4 (**V1**): no cloud or test code imports `kuksa_client` (only `vehicle/common/databroker.py` and `tools/inject_hazards.py`
  do, and only when the real Databroker is used).
- Code: `deploy/docker/*.Dockerfile`, `requirements*.txt`

**REQ-024 Integration test** · Partial · FR-19
- AC1: One van + the cloud, wired with the fake Kuksa and fake Zenoh: a hard-braking value reaches `/api/alerts` in under 2 s with route and location.
- Gap: FR-19 asks for tests "against the integrated system". This test uses fakes; the real Kuksa + Zenoh + PostgreSQL chain is
  only checked by hand on GCP (REQ-011 AC3).
- Code: `tests/test_end_to_end.py` · Tests: `test_hazard_reaches_cloud_within_two_seconds`

**REQ-025 One-command demo** · Done · FR-1, NFR-3
- AC1: `python run_demo.py` (or `run_demo.bat` / `run_demo.sh`) starts 3 vans, the cloud and the dashboard in one process and opens the browser.
- AC2: Options `--inject`, `--port`, `--seed`, `--time-scale`, `--net-delay`, `--no-browser`, `--databroker kuksa`, `--host` work as the README says.
- AC3 (**V1**, D-17): `--databroker kuksa` needs a second venv with `requirements-vehicle.txt` + `requirements-cloud.txt`
  (no Beam). In that venv the live path works fully and the route report says "pipeline not installed"; the README explains both venvs.
- Code: `run_demo.py`, `run_demo.bat`, `run_demo.sh` · Tests: no test yet (manual)

**REQ-026 Latency test tool** · Done · charter section 2 (≥ 50 hazards)
- AC1: `tools.inject_hazards` writes a hard-braking value into each van's Databroker, round-robin, N times with a random gap of ~2 s.
- AC2: It works in the demo (`--inject N`) and against real Databrokers (`python -m tools.inject_hazards --ports ... --count 50`).
- Code: `tools/inject_hazards.py` · Tests: no test yet; evidence: README latency results

---

## 5. Requirements: new in V1

New tests put the REQ id in the name: `test_req_027_...` (CLAUDE.md). REQ-029 changes `cloud-live` code but is listed here,
next to the `validate()` function it uses.

### Module `pipeline`

**REQ-027 Pub/Sub bridge** · New in V1 · FR-8, rubric "Data platform" · D-1, D-7
A small cloud service copies every raw vehicle message from Zenoh to Pub/Sub. It does not touch the live path.
- AC1: It subscribes to `fleet/*/telemetry` and `fleet/*/hazards` and publishes each payload **unchanged** to topic
  `fleet-telemetry` or `fleet-hazards`, with attributes `vehicle_id` and `kind`.
- AC2: If a publish fails, the bridge logs it and keeps going; CloudService, alerts and latency are not affected.
- AC3: Like Kuksa and Zenoh, Pub/Sub has a fake (in-memory buffer) for the laptop demo and tests, and only one file knows
  which one is used (`PUBSUB=fake|gcp`).
- AC4: On GKE it runs as an extra container in the `sdv-cloud` pod (same image), next to the Zenoh router.
- Code (planned): `cloud/pipeline/bridge.py`, `cloud/pipeline/pubsub.py`, `fakes/pubsub.py`

**REQ-028 Shared quality check `validate()`** · New in V1 · FR-10, NFR-2 · D-6
One pure function (no I/O, no Beam) decides whether a message is valid. Both CloudService and Beam use it, so the rules exist once.
- AC1: `validate(message, kind, known_vehicles, arrival_ms)` returns a list of problems; an empty list means valid.
- AC2: Problem codes and rules:

| Code | Telemetry is flagged when |
|---|---|
| `UNKNOWN_VEHICLE` | `vehicle_id` is not in `config/fleet.json` |
| `MISSING_FIELD` | any of `vehicle_id`, `ts_ms`, `trip_id`, `speed_kmh`, `lat`, `lon`, `soc_pct`, `odometer_km` is missing or null |
| `OUT_OF_RANGE` | speed outside 0-250 km/h, SoC outside 0-100%, lat outside 43.85-43.98, lon outside −78.95 to −78.78 (Oshawa area around all routes), odometer < 0 |
| `LATE` | the record arrives more than 30 s after its `ts_ms`, or `ts_ms` is more than 5 s in the future |

  Hazard events use the same codes, with required fields `vehicle_id`, `type`, `severity`, `t0_ms`, `lat`, `lon`, `trip_id`
  (`LATE` uses `t0_ms`).
- AC3: Every rule in the table has a passing and a failing test case.
- Code (planned): `cloud/quality.py`

**REQ-029 The live path rejects invalid telemetry** · New in V1 · FR-10, NFR-2 · D-6
- AC1: Telemetry with any problem from `validate()` does not update the twin, the map or the `telemetry` table.
- AC2: **Hazard events are never rejected** on the live path: a hazard with a problem still becomes an alert (safety first);
  Beam flags it (REQ-030).
- AC3: Nothing is lost silently: every rejected record is still copied by the bridge, so Beam records it in `quality_flags`.
- AC4: The existing tests in REQ-009, REQ-011 and REQ-024 still pass.
- Code: `cloud/app/analytics.py` or `cloud/app/main.py`

**REQ-030 Beam: quality flags** · New in V1 · FR-10, NFR-2 · D-4
- AC1: The Beam pipeline runs `validate()` on every message it reads. Invalid messages go to `quality_flags` (vehicle, route if
  known, kind, problem codes, the raw payload, the time it was processed) and are left out of all statistics.
- AC2: Replaying the sample file (REQ-036) gives exactly one `quality_flags` row per bad record, with the expected codes, and none for good records.
- AC3: A message that is not a JSON object at all is flagged with the code `MALFORMED`. `validate()` never sees it, because
  there is no message to check; the live path ignores it (REQ-009 AC2), so this flag is the only trace it leaves (NFR-2).
- Code (planned): `cloud/pipeline/transforms.py`

**REQ-031 Beam: trip and route efficiency and safety** · New in V1 · FR-12, charter "Route efficiency and safety" · D-4, D-5
From valid telemetry and hazard events, Beam computes per completed trip and per route:

| Metric | Per trip | Per route (over its completed trips) |
|---|---|---|
| Distance | last − first odometer (km) | sum |
| Energy | sum of battery % drops (charging is ignored), and % per km | total % / total km |
| Average speed | mean of the speed samples (km/h) | mean of the trip averages |
| Stop time | time spent below 2 km/h (s) | average per trip |
| Hazards | hazard events with this vehicle and `trip_id` | total hazards per 100 km |

- AC1: Only trips seen from start to end count: the first trip seen for a van after the pipeline starts, and the trip still in progress, are left out.
- AC2: With the sample file (REQ-036), every metric equals a value computed by hand and written in the test.
- AC3: Running the same input twice gives the same rows: a trip row is keyed by van, trip id and the trip's start time, and is
  overwritten, not added. (The start time is in the key because trip ids start again at 1 when a simulator restarts.)
- AC4: In the laptop demo with the default seed, after each van has finished two trips, Route B has the highest hazards per 100 km
  and the most stop time (charter scenario step 5).
- Code (planned): `cloud/pipeline/transforms.py`

**REQ-032 Pipeline tables** · New in V1 · FR-9 · D-2
- AC1: Tables `trip_stats` and `quality_flags`, and a view `route_stats` that sums `trip_stats` per route, exist in both schema
  files (`cloud/db/schema.*.sql`) with the same columns, created idempotently. Route numbers are pure sums and ratios of trip
  numbers, so a view keeps one source (D-5) and cannot double-count.
- AC1a: a `quality_flags` row is keyed by a hash of the raw message, so a Pub/Sub redelivery or a batch re-run does not add a second row.
- AC2: Each row has `processed_at_ms`, so pipeline lag (processing time − record time) can be measured.
- AC3: The old `trips` table and its code are removed (REQ-014).
- AC4: On GKE, `fleet-db` gets a second, **internal** load balancer Service so Dataflow workers in the VPC can reach it; the
  existing `ClusterIP` Service stays.
- Code: `cloud/db/schema.sqlite.sql`, `cloud/db/schema.postgres.sql`, `cloud/app/store.py`, `deploy/k8s/fleet-db.yaml`

**REQ-033 Runners** · New in V1 · rubric "Dataflow / Apache Beam" · D-3, D-5
The pipeline is one composite Beam transform; only its input and runner change.
- AC1: **Tests and CI**: the transforms run on the DirectRunner with in-memory input (`TestPipeline` + `Create`), with no GCP access.
  Batch runs use the DirectRunner's in-process engine, `FnApiRunner`, by name: in Beam 2.77 a plain `DirectRunner` first tries the
  Prism runner, which downloads a Go binary from GitHub releases and starts it as a subprocess (found in spike S2, T06).
- AC2: **Laptop demo and mock dashboard**: every 30 s, the same transform runs in batch on the DirectRunner over the bridge's
  in-memory buffer and writes the tables. A finished trip shows in the route report within about 30 s. The buffer keeps the
  last hour of messages, so the mock dashboard on GKE (which runs for days) does not slow down; older trips are already stored.
- AC3: **GCP**: the same transform runs as a streaming Dataflow job reading the two Pub/Sub subscriptions and writing to the fleet PostgreSQL.
- AC4: If the pipeline is not running, the live dashboard still works; the route report shows the last results.
- Code (planned): `cloud/pipeline/run.py`, `run_demo.py`

**REQ-036 Sample data and replay** · New in V1 · FR-10, rubric "Reproducible input data" · D-9
- AC1: `data/samples/telemetry.jsonl` holds about 20 good telemetry records, a few hazard events, and at least 10 bad records
  covering every problem code in REQ-028.
- AC2: `python -m tools.replay_samples` publishes the file to the Zenoh telemetry and hazard keys, so the **whole system** sees it:
  CloudService rejects the bad records and Beam flags them. Timestamps are shifted so each record keeps its offset from "now"
  (late records stay 60 s old).
- AC2a (found in T12): into a **running fleet** the replay sends only the bad records; `--all` also sends the good ones,
  for a system without vans (as the tests do). The good sample records reuse real van and trip ids, so in a running fleet
  they mixed with the live vans' trips (Route B showed 30,751 km) and moved Van 02 on the map. Sample hazard events use
  offset 0, because older t0 values were counted as hazard latency (p95 rose to 11.4 s); their trip comes from `trip_id`.
- AC3: It works in the laptop demo and against the real Zenoh router (`--zenoh tcp/<ip>:7447`).
- AC4: The Beam tests read the same file.
- Code (planned): `data/samples/telemetry.jsonl`, `tools/replay_samples.py`

**REQ-041 Pipeline documentation** · New in V1 · rubric "Pipeline diagram, schemas and contracts, deployment instructions"
- AC1: `docs/pipeline.md` has the pipeline diagram, links to the JSON Schemas (REQ-007 AC3) and the table definitions, and the
  exact commands to create the topics, start and drain the Dataflow job, and replay the samples.
- AC2: The README links to it and its "How it works" section shows the pipeline.
- Code: `docs/pipeline.md`, `README.md`

### Module `dashboard`

**REQ-034 Route report** · New in V1 · FR-12, FR-16, NFR-3, charter scenario step 5 · D-5
- AC1: `/api/routes` reads `route_stats`; `/api/trips` reads `trip_stats`.
- AC2: The Route performance panel shows per route: completed trips, distance, energy % per km, average speed, stop time per trip,
  hazards per 100 km; the worst route on hazards per 100 km is highlighted.
- AC3: The panel shows the number of flagged records (`quality_flags`) and when the stats were last updated.
- AC4: Before any trip is complete, the panel says so instead of showing zeros.
- Code: `cloud/app/main.py`, `cloud/app/store.py`, `cloud/app/static/*`
- Tests: API tests (`test_req_034_...`); UI by hand

### Module `vehicle`

**REQ-035 Delivery stops** · New in V1 · FR-1, FR-12 · D-8
- AC1: Each route profile has a stop chance and a stop length; Route B (downtown) stops most often and longest.
- AC2: When stopping, the van slows at its normal rate (no harsh-braking hazard from a stop), waits at 0 km/h, then drives on.
- AC3: The stops are repeatable with `--seed`.
- AC4: Over the same number of ticks with the same seed, Route B spends more time stopped than Routes A and C.
- AC5: The existing simulator tests still pass.
- Code: `vehicle/simulator/main.py`, `vehicle/simulator/routes.py`

### Module `cloud-live`

**REQ-038 Health reflects the database** · New in V1 · NFR-6 · D-11
- AC1: `/api/health` runs `SELECT 1`; when the database does not answer, it returns HTTP 503 with the reason.
- AC2: `deploy/k8s/cloud.yaml` has a `livenessProbe` on `/api/health`, so Kubernetes restarts the pod and it reconnects on start.
- Note: no reconnect logic or connection pool is added.
- Code: `cloud/app/main.py`, `cloud/app/store.py`, `deploy/k8s/cloud.yaml`

### Module `devops`

**REQ-037 Pipeline deployment** · New in V1 · FR-18, NFR-6 · D-7
- AC1: On every merge to `main`, new Jenkins steps create the Pub/Sub topics and subscriptions if missing, apply the internal
  load balancer for `fleet-db`, and roll out the bridge with `sdv-cloud`. The existing stages and their order stay.
- AC2: `python -m tools.dataflow_job start` and `... drain` start and drain the streaming Dataflow job; they are idempotent
  (start does nothing if a job is running) and work from a laptop or as a manual Jenkins stage.
- AC2a (D-16): by default the job runs with exactly 1 worker (no autoscaling above 1) on the smallest machine type Dataflow
  accepts for a streaming job. It is started only for a demo or a measurement and drained right after; `docs/pipeline.md`
  says so next to the start command.
- AC3: The Jenkins test stage also runs the pipeline tests (DirectRunner).
- AC4: The one manual setup step is documented: give the `sdv-cloud` pod permission to publish to Pub/Sub, and give Dataflow access to the database secret.
- Code: `Jenkinsfile`, `deploy/k8s/cloud.yaml`, `deploy/k8s/fleet-db.yaml`, `tools/dataflow_job.py`

**REQ-039 Tests run on Windows** · New in V1 · NFR-4 · D-10, D-17
- AC1: With the split (REQ-023), the default venv has no `kuksa-client` and therefore no `pyreadline`, so `python -m pytest`
  works on Windows with no extra step. The README notes `pip uninstall -y pyreadline` only for the Kuksa venv (installed by
  `kuksa-client`, broken on Python 3.10+, and imported by pytest at start-up).
- AC2: Checked before writing it: our code imports only `kuksa_client.grpc` (`vehicle/common/databroker.py`, `tools/inject_hazards.py`), and that works without `pyreadline`.
- AC3: After the step, `python -m pytest` runs on Windows.
- Code: `README.md`

**REQ-040 Docstrings match the code** · New in V1 · NFR-4 · D-12
- AC1: No comment or docstring says something that is done is "next phase" or "fake today" (25 places in 18 files at baseline).
  Notes that are still true (Velocitas, Phase 2 / V2 work) stay.
- AC2: Unused code is removed: `Detector.stop()`, `FleetAnalytics.costs`.
- AC3: No behavior changes; all tests pass.

---

## 6. Commands

| What | Command |
|---|---|
| Install (default: cloud + pipeline + tests) | `pip install -r requirements-dev.txt` |
| Install (Kuksa mode, second venv) | `pip install -r requirements-vehicle.txt -r requirements-cloud.txt` (Windows: then `pip uninstall -y pyreadline`) |
| Test | `python -m pytest` |
| Test with PostgreSQL | `TEST_DATABASE_URL=postgresql://fleet:fleet@localhost:5432/fleet python -m pytest` |
| Demo | `python run_demo.py` · `python run_demo.py --inject 50` |
| Replay sample data (V1) | `python -m tools.replay_samples` |
| Dataflow (V1) | `python -m tools.dataflow_job start` · `python -m tools.dataflow_job drain` |
| Ankaios manifest | `python -m tools.ankaios_manifest [--zenoh tcp/<ip>:7447]` |

## 7. Testing strategy

- Framework: pytest. Tests live next to their module (`vehicle/tests/`, `cloud/tests/`, `tests/`); pipeline tests go in `cloud/tests/`.
- New tests are named `test_req_<id>_<what>`. Existing test names stay.
- Beam transforms are tested with `TestPipeline` on the DirectRunner and the sample file; pure functions (`validate()`, metric
  helpers) are tested without Beam.
- Every REQ marked "no test yet" that V1 touches gets a test; the others stay as they are and are listed in the traceability table.

**Mocked versus integrated** (rubric "Evidence distinguishing mocked from integrated behaviour"):

| Part | In tests and CI | Real, where the evidence comes from |
|---|---|---|
| Kuksa Databroker | fake (`fakes/kuksa.py`) | `--databroker kuksa` and Ankaios on the VM |
| Zenoh | fake (`fakes/zenoh.py`) | GKE router ↔ VM; latency run (REQ-011 AC3) |
| PostgreSQL | SQLite and **real PostgreSQL** in GitHub Actions | GKE `fleet-db` |
| Pub/Sub | fake (`fakes/pubsub.py`) | GCP topics; message counts in the console |
| Beam | **real Beam** on the DirectRunner | Dataflow job; rows in `trip_stats`, `quality_flags` |

**Runtime evidence for V1** (for the report and video): a Dataflow job graph screenshot; `quality_flags` rows after a replay on
GCP; the route report on the real dashboard; a new latency run of ≥ 50 hazards showing p95 still under 2 s with the bridge running.

## 8. Differences from the SRS and the charter

| # | SRS / charter says | The project does | Reason |
|---|---|---|---|
| DV-1 | The HazardDetector and CloudPublisher are Velocitas apps (SRS 2.4, 5.2; charter features table, section 6) | Kuksa Python SDK, no Velocitas | D-14. velocitas-sdk 0.15.7 can only write actuator targets (our hazard signals are sensors), needs an MQTT broker per app, pins gRPC/protobuf versions that conflict with kuksa-client, and its last release was July 2025 (the charter's top risk). The rules are separate (`vehicle/hazard_rules`), so adding Velocitas later only changes the detector's input and output. |
| DV-2 | Use an older Kuksa that works with Velocitas (SRS 2.4) | Kuksa Databroker 0.6.0, VSS 5.1 | Follows from DV-1: no Velocitas, so no need for the old Kuksa. |
| DV-3 | Build automation with GitHub Actions (SRS 2.4, 5.2; charter sections 4 and 10) | GitHub Actions runs the tests; **Jenkins on GKE** builds and deploys | D-15: to apply what the team learned in the course labs and assignments, which use Jenkins. |
| DV-4 | No new tools in Phase 2 (SRS 2.4; charter risks) | V1 adds Google Pub/Sub and Apache Beam / Dataflow | Required by the course rubric ("Data platform integration": Pub/Sub, storage, Dataflow / Apache Beam). |
| DV-5 | FR-10 and FR-12 are Phase 2 | They are built in V1 | The course's V1/V2 stages are not the SRS phases. The pipeline needs real transforms, and these are the charter's two Phase 2 "Must" features (D-4). |
| DV-6 | Fleet data is stored in PostgreSQL (SRS 2.4) | PostgreSQL on GCP; **SQLite in memory** in the laptop demo and tests | The demo and tests need nothing installed. The same SQL runs on both, and GitHub Actions also runs the store tests on PostgreSQL. |
| DV-7 | FR-19: tests run against the integrated system before deployment | The automated integration test uses the fake Kuksa and Zenoh; the real chain is checked by hand on GCP | Real Kuksa and Zenoh in CI need containers in the CI job; not chosen for V1 (REQ-024). |
| DV-8 | FR-6: Ankaios manages **and updates** the vehicle apps | Ankaios starts and restarts them; updates are a manual manifest apply | Remote update is "Could", Phase 2 in the charter (REQ-008). |
| DV-9 | "All components run on cloud VMs with NTP clocks" (charter section 2) | The vans run on a VM; the cloud runs on GKE. Both use Google's NTP servers | GKE gives the deployment, rollouts and load balancers that Jenkins uses (REQ-022). The clocks are still synchronised, so latency is still t1 − t0. |
| DV-10 | Route efficiency uses "energy per km" (charter) | Battery % per km | The vehicle contract (REQ-007) carries state of charge in %, not kWh. All vans have the same battery, so routes stay comparable. |
| DV-11 | Hazard events have route and location (charter) | They also carry `trip_id` from V1 | Needed to count hazards per trip (REQ-007 AC2, REQ-031). An addition, not a removal. |
| DV-12 | FR-4 "including harsh braking and traction loss" | Five rules; OVERHEAT and LOW_ENERGY never fire in the simulator | D-13. Not worth V1 time; both are tested at rule level (REQ-004). |
| DV-13 | Anomaly detection (FR-11), hotspot map, fleet history (FR-17) | Not in V1 | D-4: planned for V2. FR-11 exists only as two live rules (REQ-013); `/api/history` exists but the dashboard does not use it. |

## 9. Decisions log

The user answered each question in chat on 2026-11-14. For D-1 to D-14 the user accepted the recommended option without adding a
reason of their own, so the reason column is the reason given with the recommendation. D-15 and D-16 are the user's own answers. D-17 came up while planning; the user accepted the recommended option.

| # | Question | Decision | Reason |
|---|---|---|---|
| D-1 | Where does the Pub/Sub + Beam pipeline connect? | (a) A separate bridge copies raw Zenoh messages to Pub/Sub, next to the unchanged live path. (Rejected: CloudService publishes; Pub/Sub replaces the live path.) | Keeps the 2 s hazard target and the deployment safe; Beam gets raw data, so its transforms do real work; one job per component. Before choosing, the user asked three follow-ups: arrow diagrams of (a) and (c), where the analytics are shown, and a clearer drawing. |
| D-2 | Where does Beam write? | (a) New tables in the existing PostgreSQL. (Rejected: BigQuery; Cloud Storage files.) | One database and one dashboard; matches SRS 2.4. Costs an internal load balancer for `fleet-db`. |
| D-3 | Where does Beam run? | (a) DirectRunner for tests, CI and the laptop; streaming Dataflow on GCP, started and drained on demand. (Rejected: DirectRunner only; Dataflow always on.) | Same code on both; tests need no cloud; real Dataflow evidence without spending credits all day. |
| D-4 | What does Beam compute in V1? | Quality checks (FR-10) and route efficiency and safety (FR-12). Hotspots and anomaly detection wait for V2. | The charter's two Phase 2 "Must" features; real transforms; answers Maria's scenario step 5. |
| D-5 | Who owns route stats? | (a) Beam only. Trip tracking leaves CloudService; the laptop demo runs the same transform in batch every 30 s. (Rejected: keep both; Beam only on GCP.) | One implementation per metric (DRY); CloudService keeps only live state; the demo works without GCP. |
| D-6 | Does the live path check quality too? | (a) One shared `validate()`: CloudService rejects bad telemetry, Beam flags it, hazards are never rejected. (Rejected: live path unchanged.) | Meets FR-10 "before storing" and NFR-2 on both paths with one implementation; a safety alert is never dropped. |
| D-7 | How much does Jenkins deploy? | (a) Topics, subscriptions, internal LB and bridge on every merge; the Dataflow job by one start/drain script. (Rejected: relaunch Dataflow on every merge; all manual.) | Automates everything free to keep running; the paid part stays on demand; existing stages untouched. |
| D-8 | Should the vans stop? | (a) Add delivery stops to the simulator; stop time = time below 2 km/h. (Rejected: drop stop time; measure "slow time".) | The vans never stop today, so stop time would be 0 on every route; the charter scenario needs Route B to stop most. |
| D-9 | Where does bad data come from? | (a) One sample file plus a replay tool. (Rejected: random bad records from the simulator.) | Repeatable input for tests and demos; keeps test data out of the driving model. |
| D-10 | P1: fix the Windows test crash? | Yes: README step plus a check that `kuksa_client.grpc` does not need `pyreadline`. | `pytest` crashes on Windows before any test runs; CI (Linux) cannot see it. |
| D-11 | P2: cloud recovery when PostgreSQL drops? | Yes: health checks the database (503), plus a liveness probe. | The store never reconnects and health says "ok" while writes fail; Beam now uses the same database. |
| D-12 | P3: outdated comments and dead code? | Yes: rewrite them to match the code; remove `Detector.stop()` and `FleetAnalytics.costs`. | 25 comments in 18 files describe done work as future work and mislead readers and AI agents. |
| D-13 | P4: hazard rules the simulator never triggers? | (a) Document only. (Rejected: change the simulator.) | FR-4 only needs harsh braking and traction loss; not worth V1 time. |
| D-14 | P5: Velocitas? | (a) Keep it deferred and record the deviation. (Rejected: try again in V1.) | Same four blockers as in the MVP, and the V1 deadline is 2026-11-16. |
| D-15 | Open question 1: why Jenkins and not GitHub Actions for deployment? | Jenkins deploys; GitHub Actions keeps running the tests. | The user's reason: to apply what was learned in the course labs and assignments. |
| D-16 | Open question 2: Dataflow budget? | 1 worker, the smallest machine type, started only for a demo or measurement and drained right after (REQ-037 AC2a). | The user's reason: a safe default for the credits. |
| D-17 | Found while planning: `apache-beam` (protobuf < 7) and `kuksa-client` 0.6.0 (protobuf ≥ 7.35.1) cannot share an environment. How to split? | (a) Split the dependencies by half: vehicle set and cloud set (REQ-023). (Rejected: Beam in its own process even on the laptop; downgrade `kuksa-client`.) | Matches the rule that the two halves never import each other; the cloud code and tests never use `kuksa-client`. Cost: Kuksa mode on the laptop needs a second venv without the route report. |

**Looked at, not proposed** (found while reading; left out to keep V1 small): `limit` and `minutes` query parameters have no upper
bound; Jenkins has no smoke test after deploy (rollout status and readiness probes only); the Jenkins test stage has no
PostgreSQL; `Bridge.telemetry_loop` reads `latest` without the lock; edge alerts stay active until acknowledged or replaced (by
design: Maria acknowledges them).

## 10. Boundaries

- **Always**: write or change the spec before the code (its own commit); test first; put the REQ id in new test names; run the
  whole test suite before saying anything is done; add a row to `measurements/dev-log.csv` after each step.
- **Ask first**: any change to the database schema beyond REQ-032; new dependencies beyond `apache-beam[gcp]`, `jsonschema` (tests only, added in T03 to check the JSON Schemas) and
  `google-cloud-pubsub`; changes to existing Jenkins stages or Kubernetes Services; anything that costs GCP credits while idle.
- **Never**: edit `docs/requirements/srs.md` or `charter.md`; put the pipeline on the live alert path; drop a hazard event; commit
  secrets or service-account keys; delete or weaken a test without a spec change that says why.

## 11. Code style

Follow the MVP's existing style: small modules, pure logic without I/O, one file per real-or-fake switch, docstrings that say
what the code does now. Example from `vehicle/hazard_rules/rules.py`:

```python
def _traction_loss(f: Frame, t: Thresholds) -> Finding | None:
    speed = f.get("speed_kmh") or 0.0
    if f.get("tcs_active") and speed >= t.traction_min_speed_kmh:
        return Finding("TRACTION_LOSS", CRITICAL, f"Traction control active at {speed:.0f} km/h")
    return None
```

The vehicle and cloud halves never import each other; `cloud/quality.py` and `cloud/pipeline/` are on the cloud side.

## 12. Open questions

None. Both were answered by the user on 2026-11-14:

1. ~~Why does Jenkins deploy instead of GitHub Actions?~~ To apply what was learned in the labs and assignments (D-15, DV-3).
2. ~~Dataflow budget?~~ 1 worker, the smallest machine type, only for demos and measurements, drained right after (D-16, REQ-037 AC2a).
