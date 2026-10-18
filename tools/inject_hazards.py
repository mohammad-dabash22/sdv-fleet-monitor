"""Inject harsh-braking hazards for the latency test (charter: at least 50 hazards).

It writes a hard-braking value into each van's Databroker, round-robin. The
normal pipeline then detects it (t0), sends it, and the cloud records the
arrival (t1). The dashboard "Latency" panel shows median, p95 and max.

Today: run_demo.py calls inject() with the fake Databroker clients:
    python run_demo.py --inject 50

NEXT PHASE: run it on its own against the real Kuksa Databrokers:
    python -m tools.inject_hazards --host <vehicle-vm-ip> --ports 55555,55556,55557 --count 50
"""

from __future__ import annotations

import argparse
import random
import threading
import time
from typing import Any, Callable

from vehicle.common import vss


def inject(clients: list[Any], datapoint: type, count: int = 50, interval_s: float = 2.0,
           stop: threading.Event | None = None, log: Callable[[str], None] = print) -> int:
    stop = stop or threading.Event()
    rng = random.Random(7)
    sent = 0
    for i in range(count):
        if stop.is_set():
            break
        client = clients[i % len(clients)]
        braking = {vss.SPEED: datapoint(45.0), vss.ACCEL_LONG: datapoint(-6.0)}
        # Write twice, 0.1 s apart: the simulator writes its own value every 0.5 s and
        # could overwrite the first write before the detector reads it.
        client.set_current_values(braking)
        stop.wait(0.1)
        client.set_current_values(braking)
        sent += 1
        if sent % 10 == 0:
            log(f"[inject] {sent}/{count} hazards injected")
        stop.wait(interval_s * rng.uniform(0.8, 1.2))  # random gap so we do not lock onto the simulator's rhythm
    log(f"[inject] done: {sent} hazards injected. See the Latency panel on the dashboard.")
    return sent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--ports", default="55555,55556,55557")
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()

    from kuksa_client.grpc import Datapoint, VSSClient  # type: ignore[import-not-found]

    clients = [VSSClient(args.host, int(p)) for p in args.ports.split(",")]
    for c in clients:
        c.connect()
    try:
        inject(clients, Datapoint, args.count, args.interval)
    finally:
        for c in clients:
            c.disconnect()
    time.sleep(0.5)


if __name__ == "__main__":
    main()
