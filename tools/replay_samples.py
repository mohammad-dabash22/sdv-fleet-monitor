"""Replay data/samples/telemetry.jsonl onto the Zenoh keys, so the WHOLE system sees it (spec REQ-036).

Every line goes to fleet/{vehicle_id}/telemetry or fleet/{vehicle_id}/hazards, exactly like a van's
publisher would send it, with its time field set to now + its offset (late records stay 60 s old).
Both paths then do their job: CloudService rejects the bad telemetry (REQ-029) and the bridge copies
everything to Pub/Sub, where the Beam pipeline flags each bad record (REQ-030).

Into a RUNNING fleet only the bad records are sent (spec REQ-036 AC2a): the good sample records reuse
real van and trip ids, so they would mix with the live vans' trips and move them on the map. --all
also sends the good ones, for a system without vans (the tests do this in-process).

Laptop demo (one process, fake Zenoh): run_demo.py does the replay itself:
    python run_demo.py --replay-samples

Against the real Zenoh router (on the vehicle VM, or anywhere that reaches it):
    python -m tools.replay_samples --zenoh tcp/<router-ip>:7447 [--all]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from cloud.pipeline.samples import SAMPLE_FILE, Sample, load_samples


def key_for(sample: Sample) -> str:
    vehicle_id = sample.message.get("vehicle_id") or "unknown"
    return f"fleet/{vehicle_id}/{'telemetry' if sample.kind == 'telemetry' else 'hazards'}"


def select(samples: list[Sample], include_good: bool) -> list[Sample]:
    """All samples, or (for a running fleet) only the bad ones."""
    return list(samples) if include_good else [s for s in samples if s.expect]


def replay(session: Any, samples: list[Sample], gap_s: float = 0.02) -> int:
    """Put every sample on its Zenoh key; returns how many were sent."""
    for sample in samples:
        session.put(key_for(sample), json.dumps(sample.message))
        if gap_s:
            time.sleep(gap_s)
    return len(samples)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--zenoh", required=True, metavar="ENDPOINT", help="Zenoh router, e.g. tcp/10.0.0.5:7447")
    parser.add_argument("--file", type=Path, default=SAMPLE_FILE)
    parser.add_argument("--all", action="store_true",
                        help="also send the good records (only for a system without vans: they reuse real van ids)")
    args = parser.parse_args()

    from cloud.app.transport import open_session
    session = open_session("zenoh", args.zenoh)
    samples = select(load_samples(args.file, int(time.time() * 1000)), include_good=args.all)
    sent = replay(session, samples)
    bad = sum(1 for s in samples if s.expect)
    print(f"[replay] sent {sent} messages ({sent - bad} good, {bad} bad) to {args.zenoh}")
    time.sleep(0.5)  # let Zenoh flush before the session closes
    session.close()


if __name__ == "__main__":
    main()
