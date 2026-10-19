-- The CI/CD deployment log.
--
-- Nothing in the application reads or writes this. The Jenkins pipeline writes
-- one row per successful rollout, so the database is a record of what the
-- pipeline actually did: which build, which image, which commit, and when.
--
-- The fleet data stays where it is; this database is only about deployments.

CREATE TABLE IF NOT EXISTS deployments (
    id            SERIAL PRIMARY KEY,
    build_number  INTEGER     NOT NULL,
    image         TEXT        NOT NULL,
    git_commit    TEXT,
    branch        TEXT,
    deployed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS deployments_deployed_at_idx ON deployments (deployed_at DESC);
