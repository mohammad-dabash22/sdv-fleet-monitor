# Tasks: SDV Fleet Monitor, V1

| | |
|---|---|
| Status | **Approved** by the user on 2026-11-14 as 29 tasks; regrouped into **19** at the user's request on 2026-11-15 (same scope, same acceptance criteria, same test names). Implementation starts with T01. |
| Spec / plan | [`fleet-monitor.md`](fleet-monitor.md), [`fleet-monitor.plan.md`](fleet-monitor.plan.md), both approved |
| Skill | `spec-driven-development`, Phase 3 (Tasks), using its task template (`planning-and-task-breakdown` is not vendored) |

## How every task is done

1. **Test first** (`tdd`): write the failing `test_req_<id>_...` test, see it fail, make it pass, refactor.
2. **Verify** (`verification-before-completion`): run the task's *Verify* command and the **whole** suite (`python -m pytest`); show the output.
3. **Commit**: one commit per task, message starting with the task id (`T07: ...`). A task that changes the spec commits the spec first.
4. **Log**: one row in `measurements/dev-log.csv` (date, task id, stage, skill, minutes, tokens, defects, rework).
5. If a task shows the spec is wrong: stop, fix the spec (own commit), then continue.

`[P]` = can run in parallel with the other `[P]` tasks of the same phase. **You** = needs you (GCP access, credits, a PR approval or a manual check in the browser).

Grouping 29 tasks into 19 makes several tasks touch more than the skill's "about 5 files". Each such task says so; the diffs are
bigger to review, and the REQ ids in the test names keep the traceability the same.

---

## Phase A: Foundations

- [ ] **T01** Split the dependencies, images and README (REQ-023, REQ-025 AC3, REQ-039, D-17)
  - Acceptance: `requirements-vehicle.txt`, `requirements-cloud.txt`, `requirements-pipeline.txt` (with `apache-beam[gcp]==2.77.0`,
    `google-cloud-pubsub`) exist as in the REQ-023 table; `requirements.txt` is `-r` cloud + `-r` pipeline; `requirements-dev.txt`
    unchanged. `vehicle.Dockerfile` installs only `requirements-vehicle.txt`; `dashboard.Dockerfile` copies the three files that
    `requirements.txt` needs. README explains the default venv and the Kuksa venv (with the `pyreadline` note), after checking that
    `kuksa_client.grpc` imports without `pyreadline`.
  - Verify: `test_req_023_only_vehicle_code_imports_kuksa_client`, `test_req_023_requirements_are_split`; a fresh venv from
    `requirements-dev.txt` runs `python -m pytest` on Windows **without** the readline workaround (REQ-039 AC3); a fresh venv from
    `requirements-vehicle.txt` installs, and `import kuksa_client.grpc` works after `pip uninstall -y pyreadline`. CI green on the
    branch. The images are built for real by Cloud Build (T14) and on the VM (T16): there is no Docker on this laptop.
  - Files (8): `requirements.txt`, `requirements-cloud.txt`, `requirements-pipeline.txt`, `requirements-vehicle.txt`,
    `deploy/docker/vehicle.Dockerfile`, `deploy/docker/dashboard.Dockerfile`, `README.md`, `tests/test_dependencies.py`

- [ ] **T02** [P] Health check reflects the database (REQ-038)
  - Acceptance: `Store.ping()`; `/api/health` returns 503 with the reason when `ping` fails; `cloud.yaml` has a `livenessProbe`.
  - Verify: `test_req_038_health_returns_503_when_database_is_down`, `test_req_038_health_ok_when_database_answers`;
    `python sdd/track-a/tools/validate_manifests.py deploy/k8s/cloud.yaml`; `kubectl apply --dry-run=client -f deploy/k8s/cloud.yaml`.
  - Files: `cloud/app/store.py`, `cloud/app/main.py`, `deploy/k8s/cloud.yaml`, `cloud/tests/test_api.py`

**Checkpoint A**: the plan's checkpoint A (section 5).

## Phase B: Contract and checks

- [ ] **T03** [P] Hazard event carries `trip_id`; JSON Schemas (REQ-007 AC2-AC3)
  - Acceptance: `Bridge.flush_hazard()` adds `trip_id`; `cloud/pipeline/schemas/telemetry.schema.json` and `hazard.schema.json`
    describe the two shapes (`trip_id` optional for hazard readers).
  - Verify: `test_req_007_hazard_event_has_trip_id`; `test_req_007_messages_match_json_schemas` in `tests/` (cross-cutting, like
    the end-to-end test), using `jsonschema` (installed with Beam).
  - Files: `vehicle/cloud_publisher/main.py`, `vehicle/tests/test_bridge.py`, `cloud/pipeline/__init__.py`, `cloud/pipeline/schemas/*.json`, `tests/test_contract.py`

- [ ] **T04** [P] Shared `validate()` and the live path rejects invalid telemetry (REQ-028, REQ-029, REQ-009 AC2)
  - Acceptance: every rule in the REQ-028 table, for telemetry and hazard events, returns its code, and valid messages return `[]`;
    invalid telemetry does not change the twin or the `telemetry` table; hazards with problems still become alerts; malformed
    JSON is ignored without a crash.
  - Verify: `test_req_028_*` (one passing and one failing case per rule); `test_req_029_invalid_telemetry_does_not_update_twin`,
    `test_req_029_hazard_with_problem_still_alerts`, `test_req_029_partial_message_then_full_message`,
    `test_req_009_malformed_json_is_ignored`; the REQ-011 and REQ-024 tests still pass.
  - Files (6): `cloud/quality.py`, `cloud/tests/test_quality.py`, `cloud/app/analytics.py`, `cloud/app/main.py`, `cloud/tests/test_analytics.py`, `cloud/tests/test_api.py`

**Checkpoint B**: the plan's checkpoint B.

## Phase C: Delivery stops

- [ ] **T05** [P with A and B] Delivery stops in the simulator (REQ-035)
  - Acceptance: per-route stop chance and length in `PROFILES` (Route B highest); the van slows at its normal rate, waits at 0 km/h,
    drives on; repeatable with the seed.
  - Verify: `test_req_035_route_b_stops_longest` (fixed seed, same ticks, all three routes), `test_req_035_stop_does_not_cause_harsh_braking`,
    `test_req_035_same_seed_same_stops`; the old simulator tests pass.
  - Files: `vehicle/simulator/main.py`, `vehicle/simulator/routes.py`, `vehicle/tests/test_simulator.py`

**Checkpoint C**: the plan's checkpoint C.

## Phase D: Pipeline core

- [ ] **T06** Spike S2: Beam in the same process as the store (plan risks R2, R3) · after T01
  - Acceptance: a throwaway pipeline on the DirectRunner writes to a `Store` found through a per-process registry, and the writes
    are visible to code outside the pipeline; the time of one batch run of ~10,000 messages is measured.
  - Verify: the spike script's output, kept in the scratchpad (not committed); the result goes into the dev log. If it fails:
    switch the laptop demo to a SQLite file (plan R2 fallback) with a one-line spec note **before** T08. If a run takes over ~10 s:
    60 s interval and a spec update to REQ-033 AC2.
  - Files: none committed

- [ ] **T07** Sample data and trip math (REQ-036 AC1, AC4; REQ-031 AC1-AC2) · after T03
  - Acceptance: `data/samples/telemetry.jsonl` has good telemetry for at least three trips of one van (so one trip is complete), a
    few hazard events in the middle trip, and at least 10 bad records covering every REQ-028 code, each with a `_note`; timestamps
    are offsets in ms that the replay tool and tests turn into real times. `metrics.trips(records, hazards)` drops the first trip
    seen and the trip in progress, and returns per trip: distance, energy % used, energy % per km, average speed, stop time (below
    2 km/h), hazards, hazards per 100 km, start and end time.
  - Verify: `test_req_036_sample_covers_every_problem_code`; `test_req_031_*`: hand-computed values from a small inline example and
    from the sample file, charging not counted as energy used, the first trip seen dropped.
  - Files: `data/samples/telemetry.jsonl`, `cloud/tests/test_samples.py`, `cloud/pipeline/metrics.py`, `cloud/tests/test_metrics.py`

- [ ] **T08** Pipeline tables, store methods and the Beam graph (REQ-032 AC1, AC1a, AC2; REQ-030; REQ-031 AC3) · after T04, T06, T07
  - Acceptance: `trip_stats` (key: van, trip id, start time) and `quality_flags` (key: hash of the raw message) tables and the
    `route_stats` view in both schema files; `Store.upsert_trip_stats`, `upsert_quality_flag`, `route_stats`, `trip_stats`,
    `quality_flag_count`; `store_for(url)` registry; the old `trips` table stays until T11. One composite Beam transform: parse →
    `validate()` → flagged to the `quality_flags` sink; valid → key by van → global window, 30 s accumulating trigger →
    `metrics.trips` → `trip_stats` sink.
  - Verify: `test_req_032_*` on SQLite and, in CI, PostgreSQL (upserting twice gives one row; the view matches the trip rows);
    `test_req_030_one_flag_per_bad_record`, `test_req_031_second_run_changes_nothing`, `test_req_031_trip_rows_match_metrics`
    with `TestPipeline` and the sample file.
  - Files (6): `cloud/db/schema.sqlite.sql`, `cloud/db/schema.postgres.sql`, `cloud/app/store.py`, `cloud/tests/test_store.py`, `cloud/pipeline/transforms.py`, `cloud/tests/test_pipeline.py`

**Checkpoint D**: the plan's checkpoint D.

## Phase E: Laptop end to end

- [ ] **T09** Bridge, fake Pub/Sub and the batch runner in the demo (REQ-027 AC1-AC3; REQ-033 AC1, AC2, AC4) · after T08
  - Acceptance: `fakes/pubsub.py` (in-memory buffer, keeps the last hour); `cloud/pipeline/pubsub.py` (the only file that knows
    `PUBSUB=fake|gcp`); `cloud/pipeline/bridge.py` (Zenoh → Pub/Sub, payload unchanged, attributes `vehicle_id`, `kind`; a failed
    publish is logged and skipped); `cloud/pipeline/run.py` runs the graph in batch over a list; `run_demo.py` starts the bridge and
    runs a batch every 30 s over the buffer; without Beam it prints "pipeline not installed" and the rest of the demo runs.
  - Verify: `test_req_027_payload_is_copied_unchanged`, `test_req_027_attributes`, `test_req_027_publish_failure_does_not_stop_bridge`,
    `test_req_027_buffer_keeps_last_hour`, `test_req_033_batch_run_writes_tables`, `test_req_033_live_path_works_without_pipeline`;
    a manual `python run_demo.py` run.
  - Files (7): `fakes/pubsub.py`, `cloud/pipeline/pubsub.py`, `cloud/pipeline/bridge.py`, `cloud/pipeline/run.py`, `run_demo.py`, `cloud/tests/test_bridge_pubsub.py`, `cloud/tests/test_run.py`

- [ ] **T10** Route report: API and panel, `ENERGY_DROP` kept working (REQ-034, REQ-020, REQ-025 AC3, REQ-013 AC2, plan R10) · after T09
  - Acceptance: the missing `ENERGY_DROP` test exists and passes, and the last battery value lives on the `Twin`; `/api/routes`
    reads `route_stats`, `/api/trips` reads `trip_stats`, and the response says whether the pipeline is installed; the panel shows
    trips, distance, energy % per km, average speed, stop time per trip, hazards per 100 km, flagged records and last update; "no
    completed trip yet" before data; worst route highlighted.
  - Verify: `test_req_013_energy_drop_alert` (before **and** after the `Twin` change), `test_req_034_routes_read_route_stats`,
    `test_req_034_trips_read_trip_stats`, `test_req_034_flagged_count`; **You**: check the panel in the browser.
  - Files (7): `cloud/app/analytics.py`, `cloud/app/main.py`, `cloud/app/store.py`, `cloud/app/static/app.js`, `cloud/app/static/index.html`, `cloud/tests/test_analytics.py`, `cloud/tests/test_api.py`

- [ ] **T11** Remove CloudService trip tracking (REQ-014 replaced, REQ-032 AC3) · after T10
  - Acceptance: `TripTracker`, `_track_trip`, `trip_result`, `add_trip`, `route_summary`, the `trips` table and the `trip` WebSocket
    event are gone; `test_trip_result_after_first_full_trip` and `test_route_summary_joins_trips_and_alerts` are deleted, because the
    spec replaced what they check with REQ-031 and REQ-034 tests.
  - Verify: the whole suite; a search for `TripTracker`, `add_trip` and `route_summary` finds nothing.
  - Files (7, deletions only): `cloud/app/analytics.py`, `cloud/app/main.py`, `cloud/app/store.py`, both schema files, `cloud/tests/test_analytics.py`, `cloud/tests/test_store.py`

- [ ] **T12** Replay tool, full-chain test and the laptop demo check (REQ-036 AC2-AC3, REQ-029 AC3, REQ-031 AC4, checkpoint E) · after T11 · **You** for the demo check
  - Acceptance: `python -m tools.replay_samples [--zenoh tcp/<ip>:7447]` publishes the file to the Zenoh keys with real times (late
    records stay 60 s old). In the laptop demo with the default seed, after two trips per van, Route B is worst on hazards per 100 km
    and stop time; replaying raises the flagged count; the latency panel still passes.
  - Verify: `test_req_036_replay_reaches_both_paths` in `tests/test_end_to_end.py`; then `python run_demo.py --inject 50` and
    `python -m tools.replay_samples`, with screenshots for the report. If Route B is not worst, tune only the stop chances in
    `routes.py` and re-run T05's tests.
  - Files: `tools/replay_samples.py`, `tests/test_end_to_end.py` (and `vehicle/simulator/routes.py` only if tuning is needed)

**Checkpoint E**: the plan's checkpoint E.

## Phase F: GCP

- [ ] **T13** **You**: review A-E and merge to `main` (CLAUDE.md step 5)
  - Acceptance: `code-review-and-quality` review of the branch against the spec, with findings fixed or recorded; a PR to `main`
    that you approve; Jenkins deploys it with the **existing** stages green.
  - Verify: Jenkins build log; both dashboards still answer.
  - Files: none (fixes from the review are their own commits)

- [ ] **T14** Kubernetes and Jenkins for the bridge (REQ-027 AC4, REQ-032 AC4, REQ-037 AC1, AC3) · after T13
  - Acceptance: `fleet-db.yaml` gets a second, internal LoadBalancer Service; `cloud.yaml` gets the `bridge` container (same image,
    `PUBSUB=gcp`, project and topic names); a new Jenkins stage creates the two topics and subscriptions if missing, before the deploy
    stage. Existing stages untouched.
  - Verify: `python sdd/track-a/tools/validate_manifests.py deploy/k8s`, `kubectl apply --dry-run=client`; after the merge, the
    Jenkins log, and `gcloud pubsub topics list` shows the topics.
  - Files: `deploy/k8s/fleet-db.yaml`, `deploy/k8s/cloud.yaml`, `Jenkinsfile`

- [ ] **T15** **You** + me: one-time GCP setup and the connection check (REQ-037 AC4, plan R4, R5)
  - Acceptance: the `sdv-cloud` pod can publish to Pub/Sub (Workload Identity); a VM in the VPC can reach `fleet-db` through the
    internal LB; the smallest machine type that Dataflow accepts for streaming is found in the docs.
  - Verify: `gcloud pubsub subscriptions pull` shows bridge messages; `psql` from the VM connects. The exact commands go into `docs/pipeline.md` (T17).
  - Files: none

- [ ] **T16** Dataflow job script and the first real run (REQ-033 AC3, REQ-037 AC2, AC2a, checkpoint F) · after T08, T15 · **You** for the run
  - Acceptance: `run.py` has a streaming mode reading the two subscriptions; `setup.py` packages `cloud/`;
    `python -m tools.dataflow_job start|drain`: 1 worker, no autoscaling above 1, the machine type from T15 as default
    (`--machine-type` to change it), Streaming Engine, `us-central1`, the GKE network; `start` does nothing if a job is running;
    `drain` drains every fleet job; a manual Jenkins parameter runs the same script. First run: `start`, the vans drive and
    `replay_samples --zenoh ...` runs on the VM, rows appear in `trip_stats` and `quality_flags`, the real route report fills, then
    `drain` and no job is left running.
  - Verify: `test_req_037_start_args`, `test_req_037_start_refuses_when_running`, `test_req_037_drain_all` (Dataflow calls faked);
    Dataflow job graph and rows (screenshots); `gcloud dataflow jobs list --status=active` is empty at the end. If blocked: the
    plan's cut line; mark REQ-033 AC3 and REQ-037 AC2 Partial in the spec, with the reason.
  - Files: `cloud/pipeline/run.py`, `setup.py`, `tools/dataflow_job.py`, `cloud/tests/test_dataflow_job.py`, `Jenkinsfile`

**Checkpoint F**: the plan's checkpoint F.

## Phase G: Docs and evidence

- [ ] **T17** [P] Pipeline documentation and docstring cleanup (REQ-041, REQ-040)
  - Acceptance: `docs/pipeline.md` with the pipeline diagram, schema and table links, the one-time setup from T15, and the exact
    start, drain and replay commands (drain next to start, D-16); README links it and shows the pipeline in "How it works". No
    comment or docstring calls finished work "next phase" or "fake today" (allow-list for notes still true: Velocitas, V2 work);
    `Detector.stop()` and `FleetAnalytics.costs` are gone. Done last, so files are not rewritten twice.
  - Verify: `test_req_040_no_outdated_next_phase_notes`; every command in the doc was run once (T15, T16) and its output matches; you read it.
  - Files: `docs/pipeline.md`, `README.md`, `tests/test_docs.py`, and comment-only edits in up to 18 files (an allowed exception: no behavior changes)

- [ ] **T18** [P] Traceability table and REQ statuses (CLAUDE.md)
  - Acceptance: `docs/traceability.md` lists every REQ: SRS ids → code → tests → status; the spec's statuses are updated (New in V1
    → Done, or Partial with the reason).
  - Verify: `test_req_traceability_lists_every_req` checks that every `REQ-0xx` in the spec appears in the table and every test name in it exists.
  - Files: `docs/traceability.md`, `specs/fleet-monitor.md`, `tests/test_docs.py`

- [ ] **T19** **You** + me: runtime evidence and the final review (spec section 7; `code-review-and-quality`, `verification-before-completion`)
  - Acceptance: a latency run of ≥ 50 hazards with the bridge running on GCP, p95 still under 2 s; screenshots of the Dataflow graph,
    `quality_flags` rows and the real route report; results written in the README; a review of everything after T13 against the
    spec, with findings fixed or recorded; the whole suite green in CI; PR to `main` approved by you.
  - Verify: the `/api/latency` numbers, the saved screenshots, review notes in the PR, CI and Jenkins green.
  - Files: `README.md` (results)

---

## Order at a glance

```
A: T01 ─────────────► T06 (spike, needs Beam)          T02 [P]
B: T03 [P] ─► T07     T04 [P]
C: T05 [P with A, B]
D: T06 + T07 + T04 ─► T08
E: T08 ─► T09 ─► T10 ─► T11 ─► T12
F: T13 ─► T14 ─► T15 ─► T16
G: T17 [P]   T18 [P] ─► T19
```

Tasks that need you: T10 (browser check), T12 (demo check), T13, T15, T16, T19.

## Mapping from the approved 29 tasks

| New | Old | | New | Old |
|---|---|---|---|---|
| T01 | T01 + T02 | | T11 | T18 |
| T02 | T03 | | T12 | T19 + T20 |
| T03 | T05 | | T13 | T21 |
| T04 | T06 + T07 | | T14 | T22 |
| T05 | T08 | | T15 | T23 |
| T06 | T09 | | T16 | T24 + T25 |
| T07 | T10 + T11 | | T17 | T26 + T04 (moved to the end) |
| T08 | T12 + T13 | | T18 | T27 |
| T09 | T14 + T16 | | T19 | T28 + T29 |
| T10 | T15 + T17 | | | |
