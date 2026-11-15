"""REQ-037 AC2/AC2a/AC2b, REQ-033 AC3: starting and draining the Dataflow job, with the cloud calls faked.

A real run costs credits and needs access to the deployment's GCP project, so here every gcloud and
Dataflow call goes through a fake `run` that records the command and answers like gcloud would.
"""

import datetime as dt
import json
import subprocess

from cloud.pipeline.run import pubsub_element
from tools import dataflow_job


class FakeRun:
    def __init__(self, active_jobs=()):
        self.active = [{"id": j, "name": f"fleet-pipeline-{j}"} for j in active_jobs]
        self.commands = []

    def __call__(self, cmd, **kwargs):
        self.commands.append(cmd)
        out = json.dumps(self.active) if "list" in cmd else ""
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")


ARGS = ["--project", "p1", "--db-url", "postgresql://fleet:x@10.0.0.9:5432/fleet"]


def launch_command(fake):
    return next(c for c in fake.commands if "cloud.pipeline.run" in c)


def test_req_037_start_args():
    fake = FakeRun()
    dataflow_job.main(["start", *ARGS], run=fake)
    cmd = launch_command(fake)
    for option in ("--runner=DataflowRunner", "--project=p1", "--region=us-central1", "--streaming",
                   "--enable_streaming_engine", "--num_workers=1", "--max_num_workers=1",
                   "--autoscaling_algorithm=NONE", "--worker_machine_type=e2-medium",
                   "--setup_file=./setup.py", "--vehicles=veh-01,veh-02,veh-03"):
        assert option in cmd, option
    assert any(o.startswith("--job_name=fleet-pipeline-") for o in cmd)
    assert any(o.startswith("--temp_location=gs://p1-sdv-dataflow/") for o in cmd)


def test_req_037_machine_type_can_be_changed():
    fake = FakeRun()
    dataflow_job.main(["start", *ARGS, "--machine-type", "e2-standard-2"], run=fake)
    assert "--worker_machine_type=e2-standard-2" in launch_command(fake)


def test_req_037_start_refuses_when_running(capsys):
    fake = FakeRun(active_jobs=["2026-11-15_01"])
    dataflow_job.main(["start", *ARGS], run=fake)
    assert not any("cloud.pipeline.run" in c for c in fake.commands)
    assert "already running" in capsys.readouterr().out


def test_req_037_drain_all():
    fake = FakeRun(active_jobs=["job-a", "job-b"])
    dataflow_job.main(["drain", "--project", "p1"], run=fake)
    drains = [c for c in fake.commands if "drain" in c]
    assert [c[c.index("drain") + 1] for c in drains] == ["job-a", "job-b"]
    assert all("--region=us-central1" in c for c in drains)


def test_req_033_pubsub_publish_time_is_the_arrival_time():
    class Msg:
        data = b"{}"
        publish_time = dt.datetime(2026, 11, 15, 12, 0, 0, 250000, tzinfo=dt.timezone.utc)

    kind, raw, arrival_ms = pubsub_element("telemetry", Msg())
    assert (kind, raw) == ("telemetry", b"{}")
    assert arrival_ms == int(Msg.publish_time.timestamp() * 1000)


def test_req_033_streaming_entry_reads_both_subscriptions(monkeypatch):
    """run_streaming() as Dataflow runs it, on the local streaming runner, with only ReadFromPubSub swapped
    for a fake source of PubsubMessages (one per subscription)."""
    import apache_beam as beam
    from apache_beam.io.gcp import pubsub as beam_pubsub

    from cloud.app.store import Store, register_store
    from cloud.pipeline import run as run_module
    from cloud.pipeline.samples import load_samples

    now = dt.datetime.now(dt.timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    by_kind = {"telemetry": [], "hazard": []}
    for s in load_samples(now_ms=now_ms):
        by_kind[s.kind].append(beam_pubsub.PubsubMessage(json.dumps(s.message).encode(), {}, publish_time=now))
    subscriptions_read = []

    class FakeRead(beam.PTransform):
        def __init__(self, subscription, with_attributes):
            super().__init__()
            subscriptions_read.append(subscription)
            self.messages = by_kind["telemetry" if "telemetry" in subscription else "hazard"]

        def expand(self, pbegin):
            return pbegin | beam.Create(self.messages)

    monkeypatch.setattr(beam_pubsub, "ReadFromPubSub", FakeRead)
    store = Store("sqlite:///:memory:")
    register_store(store, "sqlite:///:memory:")
    run_module.run_streaming(["--runner=BundleBasedDirectRunner", "--project=p1",
                              "--database_url=sqlite:///:memory:", "--vehicles=veh-01,veh-02,veh-03",
                              "--fire_every_s=1"])   # the real 30 s trigger would make the test wait 30 s
    assert subscriptions_read == ["projects/p1/subscriptions/fleet-telemetry-beam",
                                  "projects/p1/subscriptions/fleet-hazards-beam"]
    assert store.quality_flag_count() == 12
    assert [t["trip_id"] for t in store.trip_stats()] == [2]


def test_req_033_missing_publish_time_falls_back_to_now():
    class Msg:
        data = b"{}"
        publish_time = None

    _, _, arrival_ms = pubsub_element("hazard", Msg(), now_ms=lambda: 42)
    assert arrival_ms == 42
