# The dashboard with mock data, as one self-contained image: run_demo.py runs
# the vans, the fakes, the cloud service and the web UI in a single process.
#
#   docker build -f deploy/docker/dashboard.Dockerfile -t sdv-fleet/dashboard:dev .
#   docker run --rm -p 8080:8000 sdv-fleet/dashboard:dev
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

CMD ["python", "-u", "run_demo.py", "--host", "0.0.0.0", "--port", "8000", "--no-browser"]
