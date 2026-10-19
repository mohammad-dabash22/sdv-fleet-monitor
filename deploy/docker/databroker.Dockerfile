# Kuksa Databroker with our VSS overlay (Vehicle.Fleet.*, Vehicle.Hazard.*) baked in,
# so it runs the same on a laptop or a cloud VM without mounting files.
#
#   podman build -f deploy/docker/databroker.Dockerfile -t localhost/sdv-fleet/databroker:dev .
#   podman run --rm --net=host localhost/sdv-fleet/databroker:dev --port 55555
#
# Extra arguments are added after the defaults below (for example --port).

FROM ghcr.io/eclipse-kuksa/kuksa-databroker:0.6.0

COPY vehicle/vss/fleet_overlay.json /fleet_overlay.json

ENTRYPOINT ["/app/databroker", "--insecure", "--enable-databroker-v1", \
            "--vss", "vss_release_5.1.json,/fleet_overlay.json"]
