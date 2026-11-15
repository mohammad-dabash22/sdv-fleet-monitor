# SDV Fleet Monitor: V1 (spec-driven extension of the MVP)

This repo is the MVP. V1 extends and improves it with spec-driven development.
You may change, refactor or remove MVP code when a spec requirement needs it.
Every change to existing behavior must be in the spec first, with the reason.
Don't make changes that no requirement asks for.
Keep the existing tests passing, unless the spec changes what they check
(then update the spec, then the test, then the code).
Don't break the deployment (Jenkinsfile, deploy/, Helm values).

## Requirement sources

Read these before writing or changing a spec:

| File | What it is |
|---|---|
| `docs/requirements/srs.md` | SRS v1.0: the `FR-x` and `NFR-x` ids that every spec requirement links to |
| `docs/requirements/charter.md` | Project Charter v2: objectives, usage scenario (Maria), feature priorities, latency target, success criteria |

The SRS and the charter are from October 2026, before the MVP was built. Some parts no longer match the
project (for example: Jenkins deploys instead of GitHub Actions, and Velocitas is not used).
Don't edit these two files. When a spec requirement differs from them, say so in the spec and give the reason.

## Workflow

Every change goes through these steps, in order, using the skills in `.claude/skills/`:

1. `grilling`: interview the user until the requirements are clear.
2. `spec-driven-development`: write or update the spec in `specs/`. Every requirement gets an id
   (`REQ-001`) and acceptance criteria, and links to the SRS id it comes from
   (`FR-x` / `NFR-x` in `docs/requirements/srs.md`).
3. `tdd`: build one task at a time, test first. Put the REQ id in the test name (`test_req_001_...`).
4. `verification-before-completion`: run the tests and show the output before saying anything is done.
5. `code-review-and-quality`: review the change against the spec before it is merged.

No code without a spec. If the spec is wrong, fix the spec first (its own commit), then the code.

## Where things go

| What | Where |
|---|---|
| Requirement sources (SRS, charter) | `docs/requirements/` |
| Specs, plans, tasks | `specs/` |
| Traceability table | `docs/traceability.md` |
| Development measurements (time, tokens, defects, rework) | `measurements/dev-log.csv` |
| Where each skill came from and why | `skills-vendor/VENDOR.md` |
| Skill versions | `skills-CHANGELOG.md` |

After each step, add a row to `measurements/dev-log.csv`.

## Stack

- Python, pytest, FastAPI dashboard.
- Vehicle side: Eclipse Kuksa (VSS), Eclipse Zenoh, Eclipse Ankaios.
- Cloud: PostgreSQL on GKE, Jenkins CI/CD.
- New in V1: Google Pub/Sub, then Apache Beam (Dataflow), then storage.
