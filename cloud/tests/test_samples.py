"""REQ-036: data/samples/telemetry.jsonl is reproducible input with a known answer for every line."""

from cloud.pipeline.samples import SAMPLE_FILE, load_samples
from cloud.quality import validate

KNOWN = {"veh-01", "veh-02", "veh-03"}
NOW_MS = 1_700_000_000_000


def test_req_036_every_line_gives_its_expected_problems():
    for sample in load_samples(SAMPLE_FILE, NOW_MS):
        got = sorted(p.code for p in validate(sample.message, sample.kind, KNOWN, NOW_MS))
        assert got == sorted(sample.expect), sample.note


def test_req_036_sample_covers_every_problem_code():
    samples = load_samples(SAMPLE_FILE, NOW_MS)
    codes = {code for s in samples for code in s.expect}
    assert codes == {"UNKNOWN_VEHICLE", "MISSING_FIELD", "OUT_OF_RANGE", "LATE"}
    assert sum(1 for s in samples if s.expect) >= 10                         # spec: at least 10 bad records
    assert sum(1 for s in samples if s.kind == "hazard" and not s.expect) >= 2


def test_req_036_times_are_relative_to_now():
    samples = load_samples(SAMPLE_FILE, NOW_MS)
    late = next(s for s in samples if s.note.startswith("LATE: arrives 60 s"))
    assert late.message["ts_ms"] == NOW_MS - 60_000
    hazard = next(s for s in samples if s.kind == "hazard")
    assert "t0_ms" in hazard.message and "ts_ms" not in hazard.message
