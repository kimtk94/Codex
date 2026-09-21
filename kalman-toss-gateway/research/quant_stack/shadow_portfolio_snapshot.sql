CREATE TABLE IF NOT EXISTS shadow_portfolio_snapshot (
  snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  as_of timestamptz NOT NULL,
  seed_end timestamptz NOT NULL,
  status text NOT NULL CHECK (status IN ('READY','STALE','INVALID')),
  source_version text NOT NULL,
  code_sha text,
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (as_of, source_version)
);

CREATE INDEX IF NOT EXISTS idx_shadow_portfolio_snapshot_asof
  ON shadow_portfolio_snapshot (as_of DESC);

CREATE OR REPLACE VIEW v_latest_shadow_portfolio_snapshot AS
SELECT
  snapshot_id,
  as_of,
  seed_end,
  status,
  source_version,
  code_sha,
  payload,
  created_at,
  updated_at
FROM shadow_portfolio_snapshot
ORDER BY as_of DESC, updated_at DESC
LIMIT 1;

GRANT SELECT ON shadow_portfolio_snapshot TO web_reader;
GRANT SELECT ON v_latest_shadow_portfolio_snapshot TO web_reader;
