# The three vehicle apps (simulator, hazard_detector, cloud_publisher) as one image.
# They share the same code; the command picks which app runs:
#
#   podman build -f deploy/docker/vehicle.Dockerfile -t localhost/sdv-fleet/vehicle:dev .
#   podman run --rm --net=host -e VEHICLE_ID=veh-01 localhost/sdv-fleet/vehicle:dev vehicle.simulator.main
#   podman run --rm --net=host -e VEHICLE_ID=veh-01 localhost/sdv-fleet/vehicle:dev vehicle.hazard_detector.main
#
# Every setting comes from environment variables (VehicleConfig.from_env()):
# VEHICLE_ID, ROUTE_ID, SPEED_LIMIT_KMH, DATABROKER_HOST, DATABROKER_PORT, TRANSPORT, ZENOH_ENDPOINT.
# Ankaios starts these containers next to each van's Kuksa Databroker (deploy/ankaios/state.yaml).
#
# Build from the repository root: the context needs vehicle/, fakes/ and config/.

FROM python:3.12-slim

WORKDIR /srv

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY vehicle/ ./vehicle/
COPY fakes/ ./fakes/
COPY config/ ./config/

# The apps talk to a real Kuksa Databroker; Zenoh stays fake until TRANSPORT=zenoh.
ENV DATABROKER=kuksa \
    PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m"]
CMD ["vehicle.simulator.main"]
