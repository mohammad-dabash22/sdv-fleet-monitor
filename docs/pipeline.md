# The V1 data pipeline: Pub/Sub + Apache Beam

Spec: [`specs/fleet-monitor.md`](../specs/fleet-monitor.md), REQ-027 to REQ-037, REQ-041. Decisions D-1 to D-17.

The pipeline answers step 5 of Maria's scenario: at the end of the week, which route is the least efficient and the
least safe, from data she can trust. It sits **next to** the live path, never on it, so hazard alerts still reach the
dashboard in about 0.1 s.

```
                ┌──────────── live path (unchanged, ~0.1 s) ──────────────┐
van ──Zenoh──► Zenoh router ──► CloudService ──► PostgreSQL ──► dashboard
                    │            validate(): REJECT bad telemetry   ▲
                    │                                               │ /api/routes, /api/trips
                    └──► bridge ──► Pub/Sub ──► Beam ──► trip_stats, quality_flags, route_stats (view)
                         raw copy   2 topics    validate(): FLAG bad messages;       (same PostgreSQL)
                                                trip efficiency and safety
                └──────────── analytics path (seconds are fine) ──────────┘
```

## Parts

| Part | Code | What it does |
|---|---|---|
| Bridge | [`cloud/pipeline/bridge.py`](../cloud/pipeline/bridge.py) | Subscribes to `fleet/*/telemetry` and `fleet/*/hazards` on Zenoh and publishes every payload **unchanged** to Pub/Sub, with attributes `vehicle_id` and `kind`. A failed publish is logged and skipped; missing credentials make it wait, never crash (it shares a pod with the live service). |
| Topics | [`cloud/pipeline/pubsub.py`](../cloud/pipeline/pubsub.py) | `fleet-telemetry`, `fleet-hazards`; Dataflow reads `fleet-telemetry-beam` and `fleet-hazards-beam`. The only file that knows `PUBSUB=fake` or `gcp`. |
| Quality rules | [`cloud/quality.py`](../cloud/quality.py) | `validate()`: `UNKNOWN_VEHICLE`, `MISSING_FIELD`, `OUT_OF_RANGE`, `LATE`. One function, used by CloudService (reject) and Beam (flag). |
| Beam graph | [`cloud/pipeline/transforms.py`](../cloud/pipeline/transforms.py) | `FleetPipeline`: parse → validate → flagged messages to `quality_flags` (non-JSON as `MALFORMED`); valid ones grouped per van → `metrics.trips` → `trip_stats`. In streaming: a global window per van, fired every 30 s, accumulating; the rows are upserts, so batch and streaming give the same rows. |
| Trip math | [`cloud/pipeline/metrics.py`](../cloud/pipeline/metrics.py) | Per completed trip: distance, energy % used and per km, average speed, stop time (below 2 km/h), hazards and hazards per 100 km. The first trip seen and the trip in progress are left out. |
| Runners | [`cloud/pipeline/run.py`](../cloud/pipeline/run.py) | Laptop: a batch every 30 s on `FnApiRunner` (the DirectRunner's in-process engine) over the last hour in the fake Pub/Sub. Dataflow: `run_streaming()` reads both subscriptions; the Pub/Sub publish time is the arrival time for `LATE`. |
| Storage | [`cloud/app/store.py`](../cloud/app/store.py), [`cloud/db/`](../cloud/db/) | `trip_stats` (key: van, trip id, start time), `quality_flags` (key: SHA-256 of the raw message), and the `route_stats` view that sums `trip_stats` per route. |
| Report | `/api/routes`, `/api/trips`, the dashboard's Route performance panel | Reads only what the pipeline wrote; also shows the flagged-record count and the pipeline status. |

## Schemas and contracts

- Telemetry: [`cloud/pipeline/schemas/telemetry.schema.json`](../cloud/pipeline/schemas/telemetry.schema.json)
- Hazard event: [`cloud/pipeline/schemas/hazard.schema.json`](../cloud/pipeline/schemas/hazard.schema.json) (`trip_id` is new in V1, optional for readers)
- Tables and view: [`cloud/db/schema.postgres.sql`](../cloud/db/schema.postgres.sql) (same columns in `schema.sqlite.sql`)
- `tests/test_contract.py` checks the publisher's real messages against the schemas.

The schemas describe the **shape** of a message. Whether its values make sense (ranges, lateness) is `validate()`'s job.

## Reproducible input

[`data/samples/telemetry.jsonl`](../data/samples/telemetry.jsonl): 36 lines, 24 good and 12 bad, every line saying which
problem codes it must produce. Times are offsets from "now", so good records always arrive in time and late ones stay late.
The good part has one complete trip whose numbers were worked out by hand: 1.00 km, 0.9 % energy, 26.33 km/h average,
3 s stopped, 2 hazards = 200 per 100 km (`cloud/tests/test_metrics.py`).

## Run it on a laptop

```bash
python run_demo.py --replay-samples          # pipeline on; after 15 s the 12 bad sample records are replayed
```

The Route performance panel fills a little after each van's second trip (about 3 minutes at the default time scale).
`--replay-samples` sends **only the bad records** into the running fleet: the good ones reuse real van and trip ids and would
mix with the live vans' trips (spec REQ-036 AC2a).

In the Kuksa venv (no Apache Beam, see the README's "Two environments") the demo runs without the pipeline and the panel says so.

## Run it on GCP

> **Status (2026-11-15): written and tested offline, not yet run on GCP.** The account used to build V1 could not reach the
> project the deployment runs in. Every command below was checked against the code and the Google Cloud docs, but the
> one-time setup and the first Dataflow run still have to be done once by someone with access to that project.

What Jenkins already does on every merge to `main` (no action needed):

- the `pubsub` stage creates the two topics and subscriptions if they are missing (it can mark a build UNSTABLE, never stop the deploy);
- the `deploy` stage rolls out the bridge container in the `sdv-cloud` pod and the internal load balancer `sdv-fleet-db-internal`.

### One-time setup

```bash
PROJECT=<project-id>; REGION=us-central1
gcloud services enable pubsub.googleapis.com dataflow.googleapis.com --project $PROJECT
gcloud storage buckets create gs://$PROJECT-sdv-dataflow --location=$REGION --project $PROJECT

# The bridge publishes as the sdv-cloud pod's Kubernetes service account (Workload Identity Federation for GKE):
NUMBER=$(gcloud projects describe $PROJECT --format='value(projectNumber)')
gcloud projects add-iam-policy-binding $PROJECT --role=roles/pubsub.publisher \
  --member="principal://iam.googleapis.com/projects/$NUMBER/locations/global/workloadIdentityPools/$PROJECT.svc.id.goog/subject/ns/default/sa/default"

# Jenkins creates the topics and subscriptions: its service account needs Pub/Sub editor.
gcloud projects add-iam-policy-binding $PROJECT --role=roles/pubsub.editor --member="serviceAccount:<jenkins-sa-email>"

# The Dataflow workers run as the Compute Engine default service account:
gcloud projects add-iam-policy-binding $PROJECT --role=roles/dataflow.worker   --member="serviceAccount:$NUMBER-compute@developer.gserviceaccount.com"
gcloud projects add-iam-policy-binding $PROJECT --role=roles/pubsub.subscriber --member="serviceAccount:$NUMBER-compute@developer.gserviceaccount.com"

# The database's internal address for the Dataflow workers:
kubectl get service sdv-fleet-db-internal        # EXTERNAL-IP is an internal VPC address
```

Until the publisher permission exists, the bridge logs `Pub/Sub not ready ... retrying in 60 s`; the live dashboard is not affected.

### Start, then drain right after

A streaming job keeps one worker VM running and costs credits every hour (spec D-16).

```bash
python -m tools.dataflow_job start --project $PROJECT \
    --db-url "postgresql://fleet:<password>@<sdv-fleet-db-internal IP>:5432/fleet"
python -m tools.dataflow_job drain --project $PROJECT        # always, right after the demo or measurement
```

Or in Jenkins: **Build with Parameters**, `DATAFLOW = start` (then `drain`). Jenkins reads the database URL from the
`sdv-fleet-db` secret, so the password is never a build parameter. A normal build (`none`) never starts a job.

Defaults: 1 worker and no autoscaling above 1, `e2-medium`, Streaming Engine, `us-central1`. `e2-medium` is the smallest
machine type with enough memory for the Beam Python SDK harness; Dataflow accepts it but does not recommend shared-core
types or cover them by its SLA. If a job fails on it: `--machine-type e2-standard-2` (spec REQ-037 AC2b).
`start` does nothing while a fleet job is running; `drain` drains every running fleet job.

Note: Dataflow shows a job's options in its console, so people who can view the project's Dataflow jobs can see the
`--db-url` password. The database has no public address.

### Check it

```bash
python -m tools.replay_samples --zenoh tcp/<sdv-zenoh IP>:7447      # from a VM in the VPC: the 12 bad records
gcloud dataflow jobs list --region $REGION --status=active             # empty after drain
```

On the real dashboard, the Route performance panel shows the flagged records and, after the vans' second trips, the routes.

## What is verified, and how

| What | How | Where |
|---|---|---|
| Quality rules | a passing and a failing case per rule | `cloud/tests/test_quality.py` |
| Live path rejects, pipeline flags | the sample file through the whole laptop system | `tests/test_end_to_end.py` |
| Trip math | hand-computed values | `cloud/tests/test_metrics.py` |
| Beam graph | runs for real (FnApiRunner); streaming mode on the local streaming runner gives the same rows | `cloud/tests/test_pipeline.py` |
| Dataflow entry point | `run_streaming()` end to end with only `ReadFromPubSub` faked | `tests/test_dataflow_job.py` |
| PostgreSQL | store tests and a Beam run against PostgreSQL 16.2 (local) | `docs/reviews/v1-phase-a-e.md` |
| Deploy files agree with the code | topic names, stage order, bridge container, internal Service | `tests/test_deploy.py` |
| Laptop demo | Route B worst on hazards per 100 km and stop time; 12 flagged; latency p95 149 ms | `docs/evidence/v1-laptop-route-report.jpg` |
| **On GCP** | **not yet**: see the status note above | |
