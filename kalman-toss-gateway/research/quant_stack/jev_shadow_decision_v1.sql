CREATE TABLE IF NOT EXISTS public.jev_shadow_decision_v1 (
  decision_id text PRIMARY KEY,
  run_id text NOT NULL,
  market text NOT NULL,
  symbol text NOT NULL,
  strategy_version text NOT NULL,
  signal_as_of timestamptz NOT NULL,
  gateway_model text NOT NULL,
  evaluation_version text NOT NULL,
  evaluation_status text NOT NULL,
  entry_support text,
  entry_support_probabilities jsonb NOT NULL DEFAULT '{}'::jsonb,
  positive_ev_probability double precision,
  regime text,
  regime_probabilities jsonb NOT NULL DEFAULT '{}'::jsonb,
  conviction_score double precision,
  conviction_probabilities jsonb NOT NULL DEFAULT '{}'::jsonb,
  addon_support_probability double precision,
  state jsonb NOT NULL DEFAULT '{}'::jsonb,
  answer_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  usage jsonb NOT NULL DEFAULT '{}'::jsonb,
  macro_as_of timestamptz,
  macro_coverage_confidence double precision,
  error_message text,
  shadow_only boolean NOT NULL DEFAULT true,
  can_veto_live boolean NOT NULL DEFAULT false,
  can_size_live boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT jev_shadow_only_v1 CHECK (shadow_only IS TRUE),
  CONSTRAINT jev_no_live_veto_v1 CHECK (can_veto_live IS FALSE),
  CONSTRAINT jev_no_live_size_v1 CHECK (can_size_live IS FALSE),
  CONSTRAINT jev_positive_ev_probability_v1 CHECK (
    positive_ev_probability IS NULL OR
    (positive_ev_probability >= 0.0 AND positive_ev_probability <= 1.0)
  ),
  CONSTRAINT jev_addon_probability_v1 CHECK (
    addon_support_probability IS NULL OR
    (addon_support_probability >= 0.0 AND addon_support_probability <= 1.0)
  ),
  UNIQUE(run_id, symbol, strategy_version, evaluation_version)
);

CREATE INDEX IF NOT EXISTS idx_jev_shadow_v1_signal_as_of
  ON public.jev_shadow_decision_v1(signal_as_of DESC);

CREATE INDEX IF NOT EXISTS idx_jev_shadow_v1_strategy_status
  ON public.jev_shadow_decision_v1(strategy_version, evaluation_status, signal_as_of DESC);

CREATE OR REPLACE VIEW public.v_jev_shadow_decision_latest_v1 AS
SELECT DISTINCT ON (market, symbol, strategy_version)
  decision_id,
  run_id,
  market,
  symbol,
  strategy_version,
  signal_as_of,
  gateway_model,
  evaluation_version,
  evaluation_status,
  entry_support,
  entry_support_probabilities,
  positive_ev_probability,
  regime,
  conviction_score,
  addon_support_probability,
  macro_as_of,
  macro_coverage_confidence,
  shadow_only,
  can_veto_live,
  can_size_live,
  error_message,
  updated_at
FROM public.jev_shadow_decision_v1
ORDER BY market, symbol, strategy_version, signal_as_of DESC, updated_at DESC;

CREATE OR REPLACE VIEW public.v_jev_shadow_decision_summary_v1 AS
SELECT
  strategy_version,
  evaluation_status,
  COALESCE(entry_support, 'UNAVAILABLE') AS entry_support,
  count(*) AS n,
  avg(positive_ev_probability) AS avg_positive_ev_probability,
  avg(conviction_score) AS avg_conviction_score,
  avg(addon_support_probability) AS avg_addon_support_probability,
  min(signal_as_of) AS first_signal_as_of,
  max(signal_as_of) AS last_signal_as_of
FROM public.jev_shadow_decision_v1
GROUP BY strategy_version, evaluation_status, COALESCE(entry_support, 'UNAVAILABLE');
