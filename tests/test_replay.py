"""REQ-036 AC2a: replaying into a running fleet must not touch the live vans' data or the latency panel."""

from cloud.pipeline.samples import SAMPLE_FILE, load_samples
from tools.replay_samples import select

NOW_MS = 1_700_000_000_000


def test_req_036_running_fleet_gets_only_the_bad_records():
    samples = load_samples(SAMPLE_FILE, NOW_MS)
    chosen = select(samples, include_good=False)
    assert len(chosen) == 12 and all(s.expect for s in chosen)
    assert select(samples, include_good=True) == samples


def test_req_036_sample_hazards_do_not_distort_latency():
    for s in load_samples(SAMPLE_FILE, NOW_MS):
        if s.kind == "hazard":
            assert s.message["t0_ms"] == NOW_MS, s.note     # replayed hazards arrive "just detected"
