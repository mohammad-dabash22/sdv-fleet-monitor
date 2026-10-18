# deploy/ (next phase)

Empty on purpose: the mock demo does not need any deployment files.

Planned contents:

| File | What it does |
|---|---|
| `ankaios/state.yaml` | Ankaios manifest: for each van, a Kuksa Databroker + simulator + hazard_detector + cloud_publisher container |
| `zenoh/router.json5` | Zenoh router config (runs on the cloud VM, port 7447, internal only) |
| `cloud/docker-compose.yml` | Cloud VM: Zenoh router + PostgreSQL (mounts `cloud/db/schema.postgres.sql`) + cloud service |
| `docker/*.Dockerfile` | One image per app (NFR-4: all services in Docker) |
