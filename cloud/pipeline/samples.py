"""Load data/samples/telemetry.jsonl: reproducible input for the tests and the replay tool (spec REQ-036).

Each line is one vehicle message plus what it should do:

    {"kind": "telemetry" | "hazard",
     "at_ms": -23000,            # when it was "sent", relative to replay time (0 = now)
     "message": {...},           # the message without its time field
     "_expect": ["LATE"],        # the problem codes validate() must return ([] = valid)
     "_note": "..."}             # what the line is for

load_samples() fills in the time field (ts_ms for telemetry, t0_ms for hazards) as now + at_ms,
so good records always arrive within 30 s and late records stay late.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

SAMPLE_FILE = Path(__file__).resolve().parents[2] / "data" / "samples" / "telemetry.jsonl"
TIME_FIELD = {"telemetry": "ts_ms", "hazard": "t0_ms"}


@dataclass(frozen=True)
class Sample:
    kind: str
    message: dict
    expect: tuple[str, ...]
    note: str


def load_samples(path: Path = SAMPLE_FILE, now_ms: int = 0) -> list[Sample]:
    samples = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        message = dict(row["message"])
        message[TIME_FIELD[row["kind"]]] = now_ms + row["at_ms"]
        samples.append(Sample(row["kind"], message, tuple(row.get("_expect", ())), row.get("_note", "")))
    return samples
