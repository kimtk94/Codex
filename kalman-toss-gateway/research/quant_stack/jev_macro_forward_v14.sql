-- Kalman JEV V1.4 forward shadow research tables.
-- Research-only. These tables have no live execution authority.

CREATE TABLE IF NOT EXISTS public.jev_macro_forward_event_v1 (
  event_id text PRIMARY KEY,
  source text NOT NULL,
  event_family text NOT NULL,
  event_name text NOT NULL,
  scheduled_at timestamptz NOT NULL,
  first_observed_at timestamptz NOT NULL,
  actual double precision NOT NULL,
  previous double precision NULL,
  consensus double precision NULL,
  unit text NULL,
  source_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  research_only boolean NOT NULL DEFAULT true CHECK (research_only IS TRUE),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (first_observed_at >= scheduled_at)
);

CREATE INDEX IF NOT EXISTS idx_jev_macro_forward_event_sched_v1
  ON public.jev_macro_forward_event_v1 (scheduled_at DESC);

CREATE TABLE IF NOT EXISTS public.jev_macro_rate_proxy_v1 (
  observation_id text PRIMARY KEY,
  event_id text NOT NULL REFERENCES public.jev_macro_forward_event_v1(event_id) ON DELETE CASCADE,
  proxy_symbol text NOT NULL DEFAULT 'SHY',
  horizon_minutes integer NOT NULL CHECK (horizon_minutes IN (5,15,30,60)),
  pre_bar_at timestamptz NOT NULL,
  post_bar_at timestamptz NOT NULL,
  observed_at timestamptz NOT NULL,
  shy_return_pct double precision NOT NULL,
  implied_us2y_reaction_bps double precision NOT NULL,
  calibration jsonb NOT NULL DEFAULT '{}'::jsonb,
  research_only boolean NOT NULL DEFAULT true CHECK (research_only IS TRUE),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(event_id,horizon_minutes),
  CHECK (observed_at >= post_bar_at)
);

CREATE INDEX IF NOT EXISTS idx_jev_macro_rate_proxy_event_v1
  ON public.jev_macro_rate_proxy_v1 (event_id,horizon_minutes);

CREATE TABLE IF NOT EXISTS public.jev_macro_overlay_forward_v1 (
  decision_id text PRIMARY KEY,
  run_id text NOT NULL,
  market text NOT NULL DEFAULT 'US',
  symbol text NOT NULL,
  strategy_version text NOT NULL,
  signal_as_of timestamptz NOT NULL,
  decision_as_of timestamptz NOT NULL,
  evaluation_version text NOT NULL,
  evaluation_status text NOT NULL,
  event_id text NULL REFERENCES public.jev_macro_forward_event_v1(event_id),
  event_family text NULL,
  event_age_minutes double precision NULL,
  rate_horizons jsonb NOT NULL DEFAULT '{}'::jsonb,
  state jsonb NOT NULL DEFAULT '{}'::jsonb,
  event_risk text NULL,
  event_risk_probabilities jsonb NOT NULL DEFAULT '{}'::jsonb,
  event_risk_confidence double precision NULL,
  execution_timing text NULL,
  execution_timing_probabilities jsonb NOT NULL DEFAULT '{}'::jsonb,
  execution_timing_confidence double precision NULL,
  exposure_impact text NULL,
  exposure_impact_probabilities jsonb NOT NULL DEFAULT '{}'::jsonb,
  exposure_impact_confidence double precision NULL,
  evidence_sufficient_probability double precision NULL,
  adverse_next_4h_probability double precision NULL,
  supportive_next_4h_probability double precision NULL,
  materiality_score double precision NULL,
  materiality_confidence double precision NULL,
  gate_pass boolean NOT NULL DEFAULT false,
  gated_execution_timing text NOT NULL DEFAULT 'NOW',
  answer_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  usage jsonb NOT NULL DEFAULT '{}'::jsonb,
  provider_cost_usd double precision NULL,
  error_message text NULL,
  shadow_only boolean NOT NULL DEFAULT true CHECK (shadow_only IS TRUE),
  can_veto_live boolean NOT NULL DEFAULT false CHECK (can_veto_live IS FALSE),
  can_size_live boolean NOT NULL DEFAULT false CHECK (can_size_live IS FALSE),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(run_id,symbol,strategy_version,evaluation_version)
);

CREATE INDEX IF NOT EXISTS idx_jev_macro_overlay_forward_signal_v1
  ON public.jev_macro_overlay_forward_v1 (signal_as_of DESC);

GRANT SELECT,INSERT ON public.jev_macro_forward_event_v1 TO jev_shadow_writer;
GRANT SELECT,INSERT ON public.jev_macro_rate_proxy_v1 TO jev_shadow_writer;
GRANT SELECT,INSERT,UPDATE ON public.jev_macro_overlay_forward_v1 TO jev_shadow_writer;
GRANT SELECT ON public.market_price TO jev_shadow_writer;
