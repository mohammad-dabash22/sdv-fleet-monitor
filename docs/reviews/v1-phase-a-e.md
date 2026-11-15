# Review: V1 phases A-E (T01-T12) before the merge to `main`

| | |
|---|---|
| Date | 2026-11-15 |
| Skill | `code-review-and-quality` (five axes, tests reviewed first, mutation check) |
| Scope | `main..v1/sdd` without specs and docs: 51 files, +1972 / -181 lines |
| Against | `specs/fleet-monitor.md` (REQ-007, 009, 013, 014, 020, 023, 025, 027-036, 038, 039) |
| Reviewer | Claude (the same model that wrote the code: see "Limits of this review") |

## Verdict

**Approve, after the three required changes below (all done in this review).** The change does what the spec asks, keeps the live
path's latency, and every new behaviour has a test named after its REQ.

## Tests first: mutation check

The skill asks to answer "would the tests catch a regression?" by experiment. Twelve conditions added by V1 were inverted one at a
time; the matching test file was run after each and the file restored.

| Mutant | Result |
|---|---|
| `analytics.py`: accept invalid telemetry (`if not validate(...)`) | caught |
| `quality.py`: LATE at exactly 30 s (`>` → `>=`) | caught |
| `quality.py`: range ends exclusive (`<=` → `<`) | caught |
| `metrics.py`: count the trip in progress (`[1:-1]` → `[1:]`) | caught |
| `metrics.py`: stopped at exactly 2 km/h (`<` → `<=`) | **survived** → test added, now caught |
| `metrics.py`: charging counted as energy (`max(0, …)` → `abs(…)`) | caught |
| `transforms.py`: flag the valid messages (`if problems` → `if not problems`) | caught |
| `store.py`: `ON CONFLICT (id)` → `ON CONFLICT` | survived: **equivalent mutant** (`id` is the only unique key) |
| `bridge.py`: `payload.to_bytes().strip()` | **survived** → test strengthened, now caught |
| `main.py`: accept JSON that is not an object | caught |
| `replay_samples.py`: send good records into a running fleet | caught |
| `simulator/main.py`: never start a delivery stop | caught |

Score: 9/12 caught before the review, 11/12 after (the 12th cannot be caught: it does not change behaviour).

## Findings

### Required (all fixed in this review)

1. **Missing boundary test for stop time.** REQ-031 says "below 2 km/h"; nothing checked exactly 2.0. Added
   `test_req_031_exactly_2_kmh_is_moving_not_stopped`.
2. **The bridge's "unchanged payload" test could not see trimming.** The test payload had no leading or trailing bytes. The test
   payload now starts with `" \t"` and ends with `"\n"`.
3. **No PostgreSQL code path had ever run.** The upserts, the `route_stats` view (`CREATE OR REPLACE VIEW`), the `TRUNCATE` in the
   test fixture and the Beam sinks only ran on SQLite; GitHub Actions only runs on a pull request, and a SQL error would crash the
   real cloud service at start-up. Run against a local PostgreSQL 16.2 (`pgserver` in a scratch venv): the 5 PostgreSQL store tests
   pass, and a Beam run written into PostgreSQL twice gives 12 flags, 1 trip, the hand-computed route numbers, and `int`/`float`
   (no `Decimal`) from the view.

### Consider (not required for this merge)

- **Trip distance misses the gap between trips.** `distance = last − first odometer` of the trip's own samples, so the ~1 s between
  a trip's last sample and the next trip's first is lost: about 0.2 km per trip at the demo's time scale (15×, ~50 km/h), about 2 %
  of a 10 km trip. The next trip's first odometer is available when a trip is complete; using it is a small change, but it changes
  the REQ-031 table and the hand-computed sample, so it belongs in V2 with a spec change.
- **`quality_flags.raw` has no size limit.** A Pub/Sub message can be up to 10 MB; a flood of large bad messages would grow the table.
  Truncating `raw` (the `id` already hashes the full message) is a V2 candidate.

### FYI

- The laptop batch re-reads the whole one-hour buffer every 30 s: about 2 s of CPU per run at a full buffer (spike S2), roughly 7 %
  of one core. Acceptable for a demo; Dataflow does not work this way.
- In streaming, the accumulating global window keeps every message of a van for the life of the job. Fine for a demo of a few hours,
  which D-16 drains right after; a long-running job would need windows per day.
- `/api/trips?limit=` has no upper bound (the same pattern as the MVP's `/api/alerts`; listed as "looked at, not proposed" in the spec).

## Five axes, briefly

- **Correctness:** matches the REQs listed above; edge cases (null, non-number, bool, boundaries, empty input, zero distance,
  charging, out-of-order samples, restarts) have tests. Two defects found by the demo check were fixed with a spec change first
  (REQ-036 AC2a).
- **Readability:** small modules with one job each; docstrings say what the code does now. `cloud/app/main.py` is the largest file
  touched (~300 lines).
- **Architecture:** follows the MVP's patterns: one file per real-or-fake switch (`cloud/pipeline/pubsub.py`), pure logic without
  I/O (`cloud/quality.py`, `cloud/pipeline/metrics.py`), all SQL in `cloud/app/store.py`. The vehicle and cloud halves still never
  import each other (guarded by `test_req_023_only_vehicle_code_imports_kuksa_client`). One rule, `validate()`, serves both paths (DRY).
- **Security:** SQL is parameterised; the only f-strings in SQL build column lists from constants. Raw messages are stored, never
  rendered. No secrets in code. The new dashboard text uses `textContent` or the existing `esc()`.
- **Performance:** see FYI. The live path gained one `validate()` call per telemetry message (microseconds); latency re-measured: p95
  149 ms over 78 hazards.

## Verification story

- Full suite: 108 passed on Windows, Python 3.12, fresh venv from `requirements-dev.txt`.
- PostgreSQL: store tests and a Beam run against PostgreSQL 16.2 (see Required 3).
- Laptop demo (default seed): Route B worst on hazards per 100 km and stop time; 12 flagged; latency pass
  (`docs/evidence/v1-laptop-route-report.jpg`).
- **Not verified:** CI on Linux (needs a pull request), the Docker images (no Docker here; Cloud Build builds them), anything on GCP.

## Limits of this review

The skill recommends a second model for review ("Model A writes, Model B reviews"). This review was done by the model that wrote the
code, so its blind spots are the author's. The mutation check is the part that does not depend on the reviewer's judgement.
