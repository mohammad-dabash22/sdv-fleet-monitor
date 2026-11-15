"""REQ-027: the bridge copies every raw vehicle message from Zenoh to Pub/Sub, without touching it."""

import time

from cloud.pipeline.bridge import PubSubBridge
from fakes import pubsub as fake_pubsub
from fakes import zenoh as fake_zenoh

PROJECT = "test-project"


def wait_for(cond, timeout=2.0):
    end = time.time() + timeout
    while time.time() < end and not cond():
        time.sleep(0.01)
    return cond()


def started_bridge(publisher=None):
    fake_pubsub.reset()
    bridge = PubSubBridge(fake_zenoh.open(), publisher or fake_pubsub.PublisherClient(), PROJECT)
    bridge.start()
    return bridge


def topic(name):
    return fake_pubsub.messages(f"projects/{PROJECT}/topics/{name}")


def test_req_027_payload_is_copied_unchanged():
    started_bridge()
    # Even an invalid message, with leading and trailing whitespace: the bridge must not touch a byte
    # (the whitespace was added after mutation testing in the T13 review showed a .strip() went unnoticed).
    raw = b' \t{"vehicle_id":"veh-02",  "speed_kmh": -40,"odd spacing": true}\n'
    fake_zenoh.open().put("fleet/veh-02/telemetry", raw)
    assert wait_for(lambda: len(topic("fleet-telemetry")) == 1)
    assert topic("fleet-telemetry")[0].data == raw
    assert topic("fleet-hazards") == []


def test_req_027_attributes():
    started_bridge()
    fake_zenoh.open().put("fleet/veh-03/hazards", b"{}")
    assert wait_for(lambda: len(topic("fleet-hazards")) == 1)
    assert topic("fleet-hazards")[0].attributes == {"vehicle_id": "veh-03", "kind": "hazard"}


class FailsOnce(fake_pubsub.PublisherClient):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def publish(self, topic, data, **attributes):
        self.calls += 1
        if self.calls == 1:
            raise ConnectionError("Pub/Sub is unreachable")
        return super().publish(topic, data, **attributes)


def test_req_027_publish_failure_does_not_stop_bridge(capfd):
    bridge = started_bridge(FailsOnce())
    bus = fake_zenoh.open()
    bus.put("fleet/veh-01/telemetry", b'{"n": 1}')
    bus.put("fleet/veh-01/telemetry", b'{"n": 2}')
    assert wait_for(lambda: len(topic("fleet-telemetry")) == 1)
    assert topic("fleet-telemetry")[0].data == b'{"n": 2}'
    assert bridge.failed == 1
    out = capfd.readouterr().out
    assert "publish failed" in out and "handler error" not in out   # logged by the bridge, not a crash


def test_req_027_buffer_keeps_last_hour():
    fake_pubsub.reset()
    clock = [0.0]
    publisher = fake_pubsub.PublisherClient(clock=lambda: clock[0])
    path = publisher.topic_path(PROJECT, "fleet-telemetry")
    publisher.publish(path, b"old")
    clock[0] = 3600.5                               # one hour and a bit later
    publisher.publish(path, b"new")
    assert [m.data for m in fake_pubsub.messages(path)] == [b"new"]
    assert fake_pubsub.messages(path)[0].publish_time_ms == 3_600_500
