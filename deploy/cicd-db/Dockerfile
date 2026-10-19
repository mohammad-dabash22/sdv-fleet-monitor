# PostgreSQL for the CI/CD deployment log.
# The official image runs every .sql in this directory on first start.

FROM postgres:14.1-alpine

COPY init.sql /docker-entrypoint-initdb.d/
