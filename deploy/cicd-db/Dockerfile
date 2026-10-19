# PostgreSQL for the CI/CD deployment log.
#
# Same pattern as Lab 7 (voting_record/postgres): the official image runs every
# .sql in /docker-entrypoint-initdb.d/ the first time the data directory is
# empty, so the schema is created on first start with nothing to run by hand.

FROM postgres:14.1-alpine

COPY init.sql /docker-entrypoint-initdb.d/
