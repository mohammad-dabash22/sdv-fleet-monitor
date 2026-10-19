# The dashboard, served with mock data, as one self-contained image.
#
# run_demo.py runs the whole system in a single process against the fakes in
# fakes/: 3 simulated vans -> fake Databroker -> hazard detector -> fake Zenoh
# -> cloud service -> SQLite in memory -> this dashboard. Nothing outside the
# container is needed, so the image runs anywhere: docker run, GKE, or a
# teammate's laptop.
#
#   docker build -f deploy/docker/dashboard.Dockerfile -t sdv-fleet/dashboard:dev .
#   docker run --rm -p 8080:8000 sdv-fleet/dashboard:dev
#   open http://localhost:8080
#
# Build from the repository root: the context needs cloud/, vehicle/ and fakes/.

FROM python:3.12-slim

WORKDIR /srv

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY cloud/ ./cloud/
COPY vehicle/ ./vehicle/
COPY fakes/ ./fakes/
COPY tools/ ./tools/
COPY config/ ./config/
COPY run_demo.py ./

EXPOSE 8000

# 0.0.0.0, or the port is unreachable from outside the container.
# --no-browser: there is no browser in here to open.
CMD ["python", "-u", "run_demo.py", "--host", "0.0.0.0", "--port", "8000", "--no-browser"]
