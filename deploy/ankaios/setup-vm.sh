#!/bin/bash
# Set up the vans on a Linux VM with Ankaios, sending to a Zenoh router.
#
#   sudo deploy/ankaios/setup-vm.sh tcp/<zenoh-router-ip>:7447
#
# Run it from the repository root, as root. Needs podman and Ankaios 1.0
# (see README "Run the vans with Eclipse Ankaios"). It:
#   1. builds the two images (Kuksa Databroker with our overlay, vehicle apps)
#   2. writes /etc/ankaios/state.yaml from config/fleet.json, with a cloud_publisher per van
#   3. installs systemd units: ank-server + one ank-agent per van, started on boot
# Stop or start the whole fleet with: systemctl stop|start ank-server 'ank-agent@*'
set -euo pipefail

ZENOH_ENDPOINT=${1:?usage: setup-vm.sh tcp/<zenoh-router-ip>:7447}
[ "$(id -u)" -eq 0 ] || { echo "run as root (sudo)"; exit 1; }
cd "$(dirname "$0")/../.."

podman build -q -f deploy/docker/databroker.Dockerfile -t localhost/sdv-fleet/databroker:dev .
podman build -q -f deploy/docker/vehicle.Dockerfile -t localhost/sdv-fleet/vehicle:dev .

mkdir -p /etc/ankaios
python3 -m tools.ankaios_manifest --zenoh "$ZENOH_ENDPOINT" --out /etc/ankaios/state.yaml

install -m 0644 deploy/ankaios/ank-server.service deploy/ankaios/ank-agent@.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now ank-server
for vid in $(python3 -c 'import json; print(" ".join(v["vehicle_id"] for v in json.load(open("config/fleet.json"))["vehicles"]))'); do
  systemctl enable --now "ank-agent@$vid"
done

sleep 10
ank -k get workloads
