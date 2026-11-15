# Review: V1 phases F-G (T14-T19) and the final verification

| | |
|---|---|
| Date | 2026-11-15 |
| Skills | `code-review-and-quality`, `verification-before-completion` |
| Scope | `8f9302f..v1/sdd`: Kubernetes and Jenkins for the bridge, the Dataflow job script and streaming entry point, the pipeline docs, the docstring cleanup, the traceability table, the CI trigger |
| Reviewer | Claude, the same model that wrote the code (see "Limits" in [`v1-phase-a-e.md`](v1-phase-a-e.md)) |

## Verdict

**Approve the code; the GCP part stays open.** Everything that can run off GCP is tested, including a real CI run on Linux with
PostgreSQL. Nothing has run on the deployment's GCP project, because it could not be reached from the machine V1 was built on;
six REQs are Partial for that reason only (`docs/traceability.md`).

## Mutation check

| Mutant | Result |
|---|---|
| `bridge.connect_publisher`: crash instead of waiting for Pub/Sub | caught |
| `dataflow_job.start`: start even when a job is running | caught |
| `dataflow_job`: `--max_num_workers=2` | caught |
| `dataflow_job`: a bigger default machine type | caught |
| `run.pubsub_element`: publish time in seconds instead of ms | caught |
| `run.run_streaming`: read only the telemetry subscription | caught |
| `Jenkinsfile`: `start` as the default DATAFLOW choice (a merge would start a billed job) | caught |
| `Jenkinsfile`: no `catchError` around the pubsub stage (it could stop the deploy) | caught |
| `cloud.yaml`: bridge with `PUBSUB=fake` | caught |
| `main.py`: pipeline status inverted | caught |

10/10 caught.

## Findings

### Fixed during this phase

1. **A commit was pushed with a failing test** (`c036df9`). The commit command was chained after `pytest` with `;` instead of
   being gated on its exit code, so the failure (the traceability guard, which correctly noticed a new test missing from the
   table) did not stop it. Fixed in `08c522c`; every later commit is gated on a green run. The CI history shows it honestly: run
   43684835416 failed, run 43684869360 passed, and the only difference between the two commits is that one table row.
   This is a process defect, not a code defect, and a candidate for a V2 skill customization: `verification-before-completion`
   says "no commit without fresh evidence" but nothing enforces it mechanically (for example, a pre-commit hook).
2. **The bridge sidecar could have taken the live dashboard down** (found while designing T14): a container that crashes on
   missing Pub/Sub credentials makes the whole `sdv-cloud` pod not-Ready. It now waits and logs.

### Consider

- **The Jenkins `dataflow` stage assumes `python3 -m venv` works in the `google/cloud-sdk` image.** Not verifiable here. If it
  does not, run the stage in the `python` container with the Cloud SDK installed, or use the laptop command from `docs/pipeline.md`.
- **The bridge runs in the cloud image, which now carries Apache Beam** (about 300 MB more). A slimmer bridge image would start
  faster; not worth a second image in V1.

### FYI

- Groovy and Kubernetes cannot run here, so `tests/test_deploy.py` reads the files instead: names, stage order, the default
  parameter, the bridge's environment. That catches drift between the files and the code, not runtime problems.
- `--db-url` is visible in the Dataflow console to people who can view the project's jobs (documented in `docs/pipeline.md`).

## Verification story (end of V1)

| Check | Result |
|---|---|
| Full suite, Windows, Python 3.12, fresh venv | 125 passed |
| CI, Linux, Python 3.11, PostgreSQL 16 service | [run 43684869360](https://github.com/mohammad-dabash22/sdv-fleet-monitor/actions/runs/43684869360): success (first CI run of the V1 code) |
| PostgreSQL 16.2, local | store tests and a Beam run pass (`v1-phase-a-e.md`) |
| Mutation checks | 21 of 22 caught across both reviews; the 22nd is an equivalent mutant |
| Laptop demo | Route B worst on hazards per 100 km (64.5) and stop time (12.1 s per trip); 12 flagged; latency p95 149 ms |
| Docker images | not built here (no Docker); Cloud Build builds them on the next deploy |
| GCP: bridge on GKE, internal LB, Jenkins stages, Dataflow run, latency with the bridge running | **not run**: no access to the deployment's project from this machine |
| Merge to `main` | **not done**: needs a pull request and someone who can watch the deploy |
