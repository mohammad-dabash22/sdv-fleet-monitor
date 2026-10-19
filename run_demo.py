"""Run the whole system in ONE process with mock data, then open the dashboard.

    python run_demo.py                 # 3 vans + cloud + dashboard
    python run_demo.py --inject 50     # also inject 50 hazards for the latency test
    python run_demo.py --databroker kuksa   # real Kuksa Databrokers (start deploy/kuksa first)
    python run_demo.py --help          # all options

What runs (same parts as the real design; fakes unless a flag picks the real tool):

    per van (x3):  simulator  ->  Databroker (fake, or Kuksa)  ->  hazard_detector
                                                  ->  cloud_publisher  ->  fake Zenoh
    cloud:         fake Zenoh  ->  CloudService  ->  SQLite (in memory)  +  WebSocket  ->  dashboard

NEXT PHASE: this file is only for the mock demo. With the real tools, Ankaios
starts the vehicle apps (vehicle/*/main.py) in containers on the vehicle VM,
and the cloud runs with `python -m cloud.app.main` (or Docker) on the cloud VM.
"""

from __future__ import annotations

import sys

if sys.version_info < (3, 11):
    sys.exit(f"Python 3.11 or newer is needed (you have {sys.version.split()[0]}). See README.md.")

import argparse
import json
import os
import random
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def start_vehicle(cfg, stop: threading.Event) -> None:
    """Start the 3 apps of one van, each with its own Databroker client (like 3 containers)."""
    from vehicle.cloud_publisher import main as publisher
    from vehicle.common import databroker
    from vehicle.hazard_detector import main as detector
    from vehicle.simulator import main as simulator

    def app(module, name: str) -> None:
        with databroker.connect(cfg) as client:
            module.run(cfg, client, stop)

    # detector and publisher subscribe first, then the simulator starts writing
    for module, name in ((detector, "detector"), (publisher, "publisher"), (simulator, "simulator")):
        threading.Thread(target=app, args=(module, name), name=f"{cfg.vehicle_id}-{name}", daemon=True).start()


def main() -> None:
    parser = argparse.ArgumentParser(description="SDV Fleet Monitor - mock demo")
    parser.add_argument("--port", type=int, default=8000, help="dashboard port (default 8000)")
    parser.add_argument("--seed", type=int, default=42, help="random seed: same seed, same demo")
    parser.add_argument("--time-scale", type=float, default=15.0,
                        help="vans move this many times faster on the map, so trips finish during the demo")
    parser.add_argument("--net-delay", type=float, default=40.0, help="fake network delay in ms")
    parser.add_argument("--inject", type=int, default=0, metavar="N", help="inject N hazards for the latency test")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser")
    parser.add_argument("--databroker", choices=["fake", "kuksa"], default=os.environ.get("DATABROKER", "fake"),
                        help="fake (default) or kuksa: real Databrokers on the ports in config/fleet.json, "
                             "started with deploy/kuksa/docker-compose.yml")
    parser.add_argument("--host", default="127.0.0.1",
                        help="address to serve on (0.0.0.0 in a container)")
    args = parser.parse_args()

    import uvicorn

    from cloud.app.config import CloudConfig
    from cloud.app.main import create_app
    from fakes import zenoh as fake_zenoh
    from vehicle.common import databroker
    from vehicle.common.config import VehicleConfig

    random.seed(args.seed)
    fake_zenoh.configure(delay_ms=args.net_delay, jitter_ms=args.net_delay * 0.75, seed=args.seed)
    fleet = json.loads((ROOT / "config" / "fleet.json").read_text(encoding="utf-8"))

    app = create_app(CloudConfig(transport="fake", port=args.port))
    stop = threading.Event()

    vehicle_cfgs = []
    for i, v in enumerate(fleet["vehicles"]):
        cfg = VehicleConfig(
            vehicle_id=v["vehicle_id"],
            route_id=v["route_id"],
            speed_limit_kmh=fleet["routes"][v["route_id"]]["speed_limit_kmh"],
            databroker=args.databroker,
            databroker_port=v["databroker_port"],
            transport="fake",
            time_scale=args.time_scale,
            seed=args.seed + i,
        )
        vehicle_cfgs.append(cfg)
        start_vehicle(cfg, stop)

    if args.inject > 0:
        from tools.inject_hazards import inject

        def run_injection() -> None:
            if stop.wait(8):  # let the fleet start first
                return
            clients = [databroker.connect(c) for c in vehicle_cfgs]
            for c in clients:
                c.connect()
            try:
                inject(clients, databroker.datapoint_class(vehicle_cfgs[0]), count=args.inject,
                       interval_s=2.0, stop=stop)
            finally:
                for c in clients:
                    c.disconnect()

        threading.Thread(target=run_injection, name="inject", daemon=True).start()

    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '::') else args.host}:{args.port}"
    print("\n  SDV Fleet Monitor (MOCK DATA)")
    print(f"  Databroker: {args.databroker}   Transport: fake   Database: SQLite in memory")
    print(f"  Dashboard: {url}")
    print("  Press Ctrl+C to stop.\n")
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()

    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    finally:
        stop.set()


if __name__ == "__main__":
    main()
