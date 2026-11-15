"""Start and drain the streaming Dataflow job (spec REQ-037 AC2, AC2a, AC2b; D-3, D-16).

A streaming job keeps a worker VM running and costs credits every hour, so it runs only for a demo or
a measurement and is drained right after:

    python -m tools.dataflow_job start --project <project> --db-url postgresql://fleet:<pw>@<internal-ip>:5432/fleet
    python -m tools.dataflow_job drain --project <project>        # always, right after

start does nothing if a fleet job is already running; drain drains every running fleet job.
Defaults: region us-central1 (same as GKE), 1 worker and no autoscaling above 1, machine type e2-medium
(the smallest with enough memory for the Beam Python SDK harness; spec AC2b), Streaming Engine.
The one-time setup (bucket, permissions, the database's internal IP) is in docs/pipeline.md.

Note: Dataflow shows a job's options in its console, so the --db-url password is visible to people who
can view the project's Dataflow jobs. The database has no public IP (internal load balancer only).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
JOB_PREFIX = "fleet-pipeline"


def _gcloud(*args: str) -> list[str]:
    return ["gcloud", *args]


def active_jobs(project: str, region: str, run: Callable) -> list[dict]:
    out = run(_gcloud("dataflow", "jobs", "list", f"--project={project}", f"--region={region}",
                      "--status=active", f"--filter=name:{JOB_PREFIX}", "--format=json"),
              capture_output=True, text=True, check=True).stdout
    return [j for j in json.loads(out or "[]") if str(j.get("name", "")).startswith(JOB_PREFIX)]


def launch_command(args: argparse.Namespace, vehicles: list[str]) -> list[str]:
    temp = args.temp_location or f"gs://{args.project}-sdv-dataflow/tmp"
    cmd = [sys.executable, "-m", "cloud.pipeline.run",
           "--runner=DataflowRunner", f"--project={args.project}", f"--region={args.region}",
           f"--job_name={JOB_PREFIX}-{time.strftime('%Y%m%d-%H%M%S')}",
           "--streaming", "--enable_streaming_engine",
           "--num_workers=1", "--max_num_workers=1", "--autoscaling_algorithm=NONE",
           f"--worker_machine_type={args.machine_type}",
           f"--temp_location={temp}", "--setup_file=./setup.py",
           f"--database_url={args.db_url}", f"--vehicles={','.join(vehicles)}"]
    if args.subnetwork:
        cmd.append(f"--subnetwork={args.subnetwork}")
    return cmd


def start(args: argparse.Namespace, run: Callable) -> None:
    running = active_jobs(args.project, args.region, run)
    if running:
        print(f"[dataflow] a fleet job is already running ({', '.join(j['id'] for j in running)}); not starting another.")
        return
    fleet = json.loads((ROOT / "config" / "fleet.json").read_text(encoding="utf-8"))
    cmd = launch_command(args, [v["vehicle_id"] for v in fleet["vehicles"]])
    job_name = next(o for o in cmd if o.startswith("--job_name=")).split("=", 1)[1]
    print(f"[dataflow] starting {job_name} "
          f"on 1 {args.machine_type} worker in {args.region}. Drain it right after: python -m tools.dataflow_job drain")
    run(cmd, cwd=str(ROOT), check=True)


def drain(args: argparse.Namespace, run: Callable) -> None:
    running = active_jobs(args.project, args.region, run)
    if not running:
        print("[dataflow] no fleet job is running.")
    for job in running:
        print(f"[dataflow] draining {job['id']} ({job.get('name')})")
        run(_gcloud("dataflow", "jobs", "drain", job["id"], f"--project={args.project}", f"--region={args.region}"),
            check=True)


def main(argv: list[str] | None = None, run: Callable = subprocess.run) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["start", "drain"])
    parser.add_argument("--project", required=True)
    parser.add_argument("--region", default="us-central1")
    parser.add_argument("--db-url", help="start only: postgresql://... through the internal load balancer")
    parser.add_argument("--machine-type", default="e2-medium", help="fallback: e2-standard-2 (spec REQ-037 AC2b)")
    parser.add_argument("--temp-location", help="default gs://<project>-sdv-dataflow/tmp")
    parser.add_argument("--subnetwork", help="e.g. regions/us-central1/subnetworks/default (the GKE VPC)")
    args = parser.parse_args(argv)
    if args.action == "start":
        if not args.db_url:
            parser.error("start needs --db-url")
        start(args, run)
    else:
        drain(args, run)


if __name__ == "__main__":
    main()
