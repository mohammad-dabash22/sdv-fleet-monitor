# Plan: SDV Fleet Monitor, V1

| | |
|---|---|
| Status | **Approved** by the user on 2026-11-14 (task list is the next phase) |
| Date | 2026-11-14 |
| Spec | [`fleet-monitor.md`](fleet-monitor.md), approved, plus D-17 (dependency split) added while planning |
| Skill | `spec-driven-development`, Phase 2 (Plan). The skill points to `planning-and-task-breakdown` for the detailed mechanics; that skill is not vendored (`skills-vendor/VENDOR.md`, "Known limitations"), so this plan follows the five steps in `spec-driven-development` itself. |
| Location | `specs/`, as CLAUDE.md says (the skill's default is `tasks/plan.md`) |
| Deadline | V1 video and report on 2026-11-16 |

This plan says **how** and **in what order** the V1 REQs get built, what can go wrong, and how each phase is checked. The task
list (Phase 3) comes after this plan is approved.

---

## 1. What planning found (already in the spec)

Before writing the plan I checked the facts it depends on. One of them changed the spec:

| Check | Result | Effect |
|---|---|---|
| Can `apache-beam[gcp]` be installed next to the current `requirements.txt`? | **No.** `apache-beam` 2.77.0 needs `protobuf < 7`; `kuksa-client` 0.6.0 needs `protobuf >= 7.35.1`. pip backtracks to old Beam releases and then fails building them. | D-17: dependencies split by half (REQ-023 AC2-AC4). |
| Does the cloud set resolve on its own? | **Yes** (pip dry run, Python 3.12, Windows): `apache-beam[gcp]==2.77.0`, `google-cloud-pubsub` 2.44.0, `protobuf` 6.33.6, `grpcio` 1.85.1, `fastapi`, `eclipse-zenoh` 1.10.1, `psycopg2-binary` 2.9.13. | Pin `apache-beam[gcp]==2.77.0`, so pip does not backtrack. |
| Who imports `kuksa_client`? | Only `vehicle/common/databroker.py` and `tools/inject_hazards.py`, lazily. No cloud code or test. | The split does not touch cloud code or tests. |
| Fleet bounding box and loop lengths | Route points lie in lat 43.885-43.946, lon −78.915 to −78.818; loops are A 12.2 km, B 8.7 km, C 11.3 km. | The REQ-028 range (lat 43.85-43.98, lon −78.95 to −78.78) has margin around all routes. |

Four design choices made while planning were also written into the spec, because they change acceptance criteria:
`route_stats` is a **view** over `trip_stats` (REQ-032 AC1); trip rows are keyed by van, trip id **and start time** (REQ-031 AC3);
`quality_flags` rows are keyed by a **hash of the raw message** (REQ-032 AC1a); the laptop buffer keeps **the last hour**
(REQ-033 AC2).

## 2. Components and how they fit

```
                                 shared, pure (no I/O)
                         ┌──────────────────────────────────────┐
                         │ cloud/quality.py      validate()      │  REQ-028
                         │ cloud/pipeline/metrics.py  trip math  │  REQ-031
                         └───────┬───────────────────┬───────────┘
                                 │                   │
 Zenoh ──► CloudService ─────────┘ (reject)          │
   │       cloud/app/*                               │
   │                                                 │
   └──► bridge ──► Pub/Sub ──► Beam graph ───────────┘ (flag + compute)
        cloud/pipeline/       cloud/pipeline/transforms.py ──► sinks ──► Store ──► PostgreSQL / SQLite
        bridge.py, pubsub.py  run.py (runner + input)                     cloud/app/store.py
        fakes/pubsub.py
```

| Component | New / changed | Files | REQs | Depends on |
|---|---|---|---|---|
| Dependency split | changed | `requirements*.txt`, `deploy/docker/*.Dockerfile`, `README.md` | 023, 025, 039 | none |
| Health check | changed | `cloud/app/main.py`, `cloud/app/store.py`, `deploy/k8s/cloud.yaml` | 038 | none |
| Docstring cleanup | changed | 18 files | 040 | none |
| Contract | changed | `vehicle/cloud_publisher/main.py`, `cloud/pipeline/schemas/*.json` | 007 | none |
| `validate()` | new | `cloud/quality.py` | 028 | contract |
| Live rejection | changed | `cloud/app/analytics.py` | 029, 009 | `validate()` |
| Delivery stops | changed | `vehicle/simulator/main.py`, `routes.py` | 035 | none |
| Trip math | new | `cloud/pipeline/metrics.py` | 031 | contract |
| Tables and store | changed | `cloud/db/schema.*.sql`, `cloud/app/store.py` | 032, 014 | trip math (columns) |
| Beam graph | new | `cloud/pipeline/transforms.py` | 030, 031 | `validate()`, trip math, store |
| Sample data | new | `data/samples/telemetry.jsonl` | 036 | contract, `validate()` codes |
| Bridge + fake Pub/Sub | new | `cloud/pipeline/bridge.py`, `cloud/pipeline/pubsub.py`, `fakes/pubsub.py` | 027 | none |
| Runners | new | `cloud/pipeline/run.py`, `run_demo.py` | 033 | Beam graph, bridge |
| Route report | changed | `cloud/app/main.py`, `store.py`, `static/*` | 034, 020, 014 | tables |
| Replay tool | new | `tools/replay_samples.py` | 036 | sample data |
| GCP deployment | new / changed | `Jenkinsfile`, `deploy/k8s/cloud.yaml`, `fleet-db.yaml`, `tools/dataflow_job.py`, `setup.py` | 037, 032 AC4, 033 AC3 | everything above |
| Docs | new / changed | `docs/pipeline.md`, `README.md`, `docs/traceability.md` | 041 | everything above |

### How the Beam graph works (REQ-030, 031, 033)

The same graph runs in batch (laptop, tests) and streaming (Dataflow); only the input step and the trigger change.

1. **Read**: `Create(messages)` in batch, or `ReadFromPubSub(subscription=...)` for each of the two subscriptions in streaming.
2. **Parse and check**: decode JSON, run `validate()`. Split into *valid* and *flagged*.
3. **Flagged** → `quality_flags` sink, at once (no grouping), keyed by a hash of the raw message.
4. **Valid** telemetry and hazard events → key by `vehicle_id` → one global window with a trigger every 30 s of processing time,
   in *accumulating* mode, so each firing sees all messages for that van so far. In batch the trigger fires once at the end.
5. **Per van** → `metrics.trips(records, hazards)`, a plain Python function: sort by time, split by `trip_id`, drop the first trip
   seen and the trip in progress (REQ-031 AC1), compute distance, energy, average speed, stop time and hazards per trip.
6. **Trips** → `trip_stats` sink as upserts, keyed by van, trip id and trip start (REQ-031 AC3). Re-firing the same trip just
   overwrites it.
7. **Route numbers**: the `route_stats` view sums `trip_stats`, so no Beam step does this and nothing can count twice.

Why this shape: the metric logic sits in one pure function that can be tested without Beam; accumulating panes plus upserts make
batch and streaming give the same rows; "first trip seen after start" falls out of seeing the whole pane. The cost is that
streaming state grows for as long as the job runs. For a demo of a few hours that is a few tens of thousands of small records,
and the job is drained right after (D-16).

### How the sinks reach the database

A sink step holds only `DATABASE_URL`. In `setup()` it gets its `Store` from a small per-process registry (`store_for(url)`).

- On the **laptop**, Beam's DirectRunner runs in the same process as CloudService, so the registry returns the **same**
  in-memory SQLite `Store` the dashboard reads. Nothing new has to be installed or shared between processes.
- On **Dataflow**, the registry opens a PostgreSQL connection to the fleet database through its internal load balancer (REQ-032 AC4).

All SQL stays in `cloud/app/store.py` (the existing rule). New methods: `upsert_trip_stats`, `upsert_quality_flag`,
`route_stats`, `trip_stats`, `quality_flag_count`, `ping`.

### GCP layout

```
GKE pod sdv-cloud:  zenoh-router │ cloud (CloudService) │ bridge (new, same image, PUBSUB=gcp)
                                                           │ publishes
Pub/Sub:            fleet-telemetry ── sub fleet-telemetry-beam ─┐
                    fleet-hazards   ── sub fleet-hazards-beam ───┤
Dataflow (on demand, 1 worker):  streaming job  ◄───────────────┘
                                   │ writes over the VPC
GKE:                sdv-fleet-db  (ClusterIP for the pod + new internal LB for Dataflow)
```

- The bridge publishes using the pod's identity, set up once by hand (Workload Identity, REQ-037 AC4).
- `tools/dataflow_job.py start` packages `cloud/` with a small `setup.py`, runs in `us-central1`, 1 worker, Streaming Engine,
  the smallest machine type that streaming accepts, in the VPC network shared with GKE. `drain` drains every running job with the job's name.

## 3. Build order

Work is split into seven phases. Each one ends at a checkpoint that must be green before the next phase depends on it.

| Phase | REQs | What | Rough effort | Can run in parallel with |
|---|---|---|---|---|
| **A. Foundations** | 023, 039, 038, 040 | Dependency split, health check, docstring cleanup | 1.5 h | each other; B; C |
| **B. Contract and checks** | 007, 028, 029 | `trip_id` in hazard events, JSON Schemas, `validate()`, live rejection | 1.5 h | A, C |
| **C. Delivery stops** | 035 | Simulator stops, Route B most | 1 h | A, B |
| **D. Pipeline core** | 031, 032, 030, 036 (file) | Trip math, tables and store, Beam graph, sample file | 3 h | needs A (Beam installed) and B |
| **E. Laptop end to end** | 027, 033 (AC1, AC2, AC4), 034, 014, 036 (tool) | Bridge and fake Pub/Sub, batch runner in `run_demo.py`, route report, remove trip tracking, replay tool | 3 h | needs D |
| **F. GCP** | 033 (AC3), 037, 032 (AC4) | Dataflow runner and script, Jenkins stages, k8s changes, one real run | 3 h | needs E |
| **G. Docs and evidence** | 041, traceability, runtime evidence | `docs/pipeline.md`, README, `docs/traceability.md`, latency re-run, screenshots | 1.5 h | starts after E; finishes after F |

Order inside D: trip math (pure, test first) → schema and store methods → Beam graph on `TestPipeline` with the sample file. This
is the first point where Beam is used, so it starts with spike **S2** (section 4).

Order inside F: k8s changes (internal LB, bridge container, liveness probe) → Jenkins stages → `dataflow_job.py` → one real run →
drain. Every Jenkins change is merged on its own, so a broken deploy is easy to find and revert.

**Cut line for 2026-11-16.** Phases A-E and G give a full, demonstrable V1 on Beam's DirectRunner. If GCP (F) gets stuck, for
example on Dataflow networking, V1 still ships with the bridge and topics deployed by Jenkins and the Beam evidence from the
DirectRunner, and the report states plainly which part did not run on Dataflow and why. REQ-033 AC3 and REQ-037 AC2 would then be
marked Partial in the spec, not quietly dropped.

## 4. Risks

| # | Risk | Likelihood / impact | Mitigation |
|---|---|---|---|
| R1 | A real install of the cloud set behaves differently from the dry run (wheel missing on Linux, `google-apitools` source build) | low / high | First task of Phase A: install `requirements-dev.txt` in a fresh venv on Windows **and** in the Jenkins `python:3.12` image; run all tests. |
| R2 | The DirectRunner does not run sinks in the CloudService process, so the shared in-memory SQLite trick fails | medium / high | **Spike S2** at the start of D: a 20-line pipeline writing to a registry `Store`, run in-process. Fallback: the laptop demo uses a SQLite **file** in a temp folder, so CloudService and Beam open the same file (REQ-010 note only). |
| R3 | One batch run takes too long on Windows (DirectRunner start-up) | medium / low | Measure in S2. If a run takes more than about 10 s, use a 60 s interval; REQ-033 AC2 says "about 30 s", so the spec would need a one-line update. |
| R4 | Dataflow workers cannot reach `fleet-db` (region, VPC, firewall) | medium / high | Same region as GKE, `--network` of the GKE VPC, internal LB. Test the connection with a one-off `psql` from a VM in the VPC before the first Dataflow run. Cut line if blocked. |
| R5 | The smallest machine type is not accepted for a streaming job | medium / low | Look it up in the Dataflow docs when building `dataflow_job.py`; the script takes `--machine-type` so it can change without code. |
| R6 | Dataflow workers miss our package or `psycopg2` | medium / medium | `setup.py` installing `cloud/` and `requirements-pipeline.txt`; the first run is the test. |
| R7 | A forgotten Dataflow job spends credits | medium / medium | `drain` drains every running fleet job; `start` refuses if one is running; `docs/pipeline.md` puts drain next to start (D-16). |
| R8 | Adding Beam makes the cloud image much larger and the Cloud Build step slower | high / low | Accept; watch the Jenkins `containerize` time. The vehicle image gets **smaller** (no cloud packages). |
| R9 | Live rejection hides the first telemetry messages, which can have empty fields before all signals arrive | high / low | Expected and correct (REQ-029). The van appears after about 1 s; a test checks a partial message is rejected and the next full one is accepted. |
| R10 | Removing `TripTracker` breaks `ENERGY_DROP`, which reads the tracker's last battery value | high / medium | Keep the last battery value on the `Twin` instead; add the missing `ENERGY_DROP` test **before** the removal (REQ-013 AC2). |
| R11 | Delivery stops change the default-seed demo, so Route B may no longer have the most hazards per 100 km | low / medium | REQ-031 AC4 checks both together; tune stop chances only, not hazard chances. |
| R12 | The two-day deadline | high / high | Phase order puts the demonstrable laptop pipeline first; the cut line above; each phase is committed when its checkpoint is green. |

## 5. Verification checkpoints

Every checkpoint runs `python -m pytest` and shows its output (`verification-before-completion`). New tests are named
`test_req_<id>_...`.

| After | Must be true |
|---|---|
| A | Fresh venv from `requirements-dev.txt`: all 34 tests pass on Windows **without** the readline workaround (REQ-039 AC3). The vehicle set installs on its own. `/api/health` returns 503 when the store's `ping` fails (test). CI green on the branch. |
| B | `validate()` has a passing and a failing case for every rule (REQ-028 AC3). Invalid telemetry does not change the twin or the `telemetry` table; a hazard with a problem still becomes an alert (REQ-029 tests). Publisher messages validate against the JSON Schemas. The REQ-011 and REQ-024 tests still pass. |
| C | With a fixed seed and the same number of ticks, Route B stops longest (REQ-035 AC4); no harsh-braking hazard comes from a stop; the old simulator tests pass. |
| D | `TestPipeline` with the sample file: one `quality_flags` row per bad record with the right codes (REQ-030 AC2), trip metrics equal the hand-computed values (REQ-031 AC2), and a second run changes nothing (AC3). Store tests pass on SQLite, and on PostgreSQL in CI. |
| E | Laptop demo: replaying the samples shows the flagged count in the route report; after two trips per van, Route B is worst on hazards per 100 km and stop time (REQ-031 AC4); the latency panel still passes; the end-to-end test still passes. |
| F | A merge to `main` deploys the bridge without breaking the existing stages (Jenkins log). `dataflow_job start` → rows appear in `trip_stats` and `quality_flags` on GCP → `drain` → no job running. |
| G | Every REQ appears in `docs/traceability.md` with its tests; the latency re-run (≥ 50 hazards, bridge running) still has p95 < 2 s; screenshots for the report are saved. |

After G, `code-review-and-quality` reviews the whole change against the spec before it is merged to `main` (CLAUDE.md step 5).

## 6. What stays the same

- The live path: Zenoh → CloudService → PostgreSQL → dashboard. The only change on it is REQ-029 (rejecting bad telemetry).
- The existing Jenkins stages and their order. New steps are added; none is removed or reordered.
- The vehicle apps, except `trip_id` in the hazard event (REQ-007 AC2) and the delivery stops (REQ-035).
- Existing test names. Two tests are replaced because the spec changes what they check (REQ-014):
  `test_trip_result_after_first_full_trip` and `test_route_summary_joins_trips_and_alerts`.
