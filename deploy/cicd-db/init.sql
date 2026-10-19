-- The CI/CD deployment log: one row per rollout, written by the pipeline.
-- Separate from the fleet data; the application never touches it.

CREATE TABLE IF NOT EXISTS deployments (
    id            SERIAL PRIMARY KEY,
    build_number  INTEGER     NOT NULL,
    image         TEXT        NOT NULL,
    git_commit    TEXT,
    branch        TEXT,
    deployed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS deployments_deployed_at_idx ON deployments (deployed_at DESC);
