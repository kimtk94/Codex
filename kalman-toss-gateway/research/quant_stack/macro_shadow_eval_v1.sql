-- Kalman Macro Shadow Evaluation V1
-- Forward-only research ledger. Does not alter R5.1 signals or trade execution.

CREATE TABLE IF NOT EXISTS public.macro_shadow_evaluation_v1 (
    evaluation_id text PRIMARY KEY,
    benchmark_id uuid NOT NULL UNIQUE
        REFERENCES public.strategy_benchmark_ledger(benchmark_id) ON DELETE CASCADE,
    market text NOT NULL,
    strategy_version text NOT NULL,
    benchmark_name text NOT NULL,
    signal_as_of timestamptz NOT NULL,
    macro_as_of timestamptz,
    macro_run_id text,
    macro_age_seconds double precision,
    coverage_confidence double precision,
    evaluation_status text NOT NULL
        CHECK (evaluation_status IN (
            'READY','NO_MACRO_SNAPSHOT','STALE_MACRO_SNAPSHOT','LOW_MACRO_COVERAGE'
        )),
    free_macro_regime text NOT NULL
        CHECK (free_macro_regime IN (
            'TIGHTENING','EASING','MIXED','NEUTRAL','UNKNOWN'
        )),
    us2y_change_bps_1d double precision,
    policy_proxy_change_bps_1d double precision,
    policy_proxy_spread_bps double precision,
    official_macro_decay double precision,
    broad_macro_decay double precision,
    macro_event_free_reaction_score double precision,
    macro_event_free_reaction_direction text
        CHECK (macro_event_free_reaction_direction IN (
            'HAWKISH_TIGHTENING','DOVISH_EASING','NEUTRAL','BLOCKED'
        )),
    macro_event_free_reaction_ready boolean,
    baseline_gross_return double precision NOT NULL,
    baseline_net_return double precision NOT NULL,
    macro_features jsonb NOT NULL DEFAULT '{}'::jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.macro_shadow_evaluation_v1
    ADD COLUMN IF NOT EXISTS macro_event_free_reaction_score double precision;
ALTER TABLE public.macro_shadow_evaluation_v1
    ADD COLUMN IF NOT EXISTS macro_event_free_reaction_direction text;
ALTER TABLE public.macro_shadow_evaluation_v1
    ADD COLUMN IF NOT EXISTS macro_event_free_reaction_ready boolean;

CREATE INDEX IF NOT EXISTS idx_macro_shadow_eval_signal
    ON public.macro_shadow_evaluation_v1
       (strategy_version, benchmark_name, signal_as_of DESC);

CREATE INDEX IF NOT EXISTS idx_macro_shadow_eval_regime
    ON public.macro_shadow_evaluation_v1
       (benchmark_name, free_macro_regime, signal_as_of DESC);

CREATE OR REPLACE VIEW public.v_macro_shadow_eval_summary_v1 AS
SELECT
    market,
    strategy_version,
    benchmark_name,
    free_macro_regime,
    count(*) FILTER (WHERE evaluation_status='READY') AS ready_n,
    avg(baseline_net_return) FILTER (WHERE evaluation_status='READY') AS avg_net_return,
    stddev_samp(baseline_net_return) FILTER (WHERE evaluation_status='READY') AS stddev_net_return,
    avg(CASE WHEN baseline_net_return > 0 THEN 1.0 ELSE 0.0 END)
        FILTER (WHERE evaluation_status='READY') AS win_rate,
    min(signal_as_of) FILTER (WHERE evaluation_status='READY') AS first_ready_as_of,
    max(signal_as_of) FILTER (WHERE evaluation_status='READY') AS last_ready_as_of
FROM public.macro_shadow_evaluation_v1
GROUP BY market,strategy_version,benchmark_name,free_macro_regime;

CREATE OR REPLACE VIEW public.v_macro_shadow_eval_readiness_v1 AS
SELECT
    market,
    strategy_version,
    benchmark_name,
    count(*) AS matured_baseline_rows,
    count(*) FILTER (WHERE evaluation_status='READY') AS ready_rows,
    count(*) FILTER (WHERE evaluation_status='NO_MACRO_SNAPSHOT') AS no_macro_snapshot_rows,
    count(*) FILTER (WHERE evaluation_status='STALE_MACRO_SNAPSHOT') AS stale_macro_snapshot_rows,
    count(*) FILTER (WHERE evaluation_status='LOW_MACRO_COVERAGE') AS low_macro_coverage_rows,
    min(signal_as_of) AS first_signal_as_of,
    max(signal_as_of) AS last_signal_as_of,
    max(updated_at) AS updated_at
FROM public.macro_shadow_evaluation_v1
GROUP BY market,strategy_version,benchmark_name;

GRANT SELECT, INSERT, UPDATE ON public.macro_shadow_evaluation_v1 TO investment_hub_owner;
GRANT SELECT ON public.macro_shadow_evaluation_v1 TO kalman_colab_ro;
GRANT SELECT ON public.v_macro_shadow_eval_summary_v1 TO kalman_colab_ro;
GRANT SELECT ON public.v_macro_shadow_eval_readiness_v1 TO kalman_colab_ro;


CREATE OR REPLACE VIEW public.v_macro_shadow_eval_free_reaction_v1 AS
SELECT
    market,
    strategy_version,
    benchmark_name,
    macro_event_free_reaction_direction,
    count(*) FILTER (
        WHERE evaluation_status='READY'
          AND macro_event_free_reaction_ready IS TRUE
    ) AS ready_n,
    avg(baseline_net_return) FILTER (
        WHERE evaluation_status='READY'
          AND macro_event_free_reaction_ready IS TRUE
    ) AS avg_net_return,
    stddev_samp(baseline_net_return) FILTER (
        WHERE evaluation_status='READY'
          AND macro_event_free_reaction_ready IS TRUE
    ) AS stddev_net_return,
    avg(CASE WHEN baseline_net_return > 0 THEN 1.0 ELSE 0.0 END) FILTER (
        WHERE evaluation_status='READY'
          AND macro_event_free_reaction_ready IS TRUE
    ) AS win_rate,
    avg(macro_event_free_reaction_score) FILTER (
        WHERE evaluation_status='READY'
          AND macro_event_free_reaction_ready IS TRUE
    ) AS avg_free_reaction_score,
    min(signal_as_of) FILTER (
        WHERE evaluation_status='READY'
          AND macro_event_free_reaction_ready IS TRUE
    ) AS first_ready_as_of,
    max(signal_as_of) FILTER (
        WHERE evaluation_status='READY'
          AND macro_event_free_reaction_ready IS TRUE
    ) AS last_ready_as_of
FROM public.macro_shadow_evaluation_v1
GROUP BY market,strategy_version,benchmark_name,macro_event_free_reaction_direction;

GRANT SELECT ON public.v_macro_shadow_eval_free_reaction_v1 TO kalman_colab_ro;
