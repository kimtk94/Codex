-- Kalman Macro Event Feature Layer V1
-- Additive challenger-only schema. Does not alter R5.1 scoring or trade gates.

CREATE TABLE IF NOT EXISTS public.macro_release_observation (
    observation_id text PRIMARY KEY,
    indicator_key text NOT NULL,
    event_name text NOT NULL,
    market text NOT NULL DEFAULT 'GLOBAL'
        CHECK (market IN ('US','KR','CRYPTO','GLOBAL')),
    release_at timestamptz NOT NULL,
    available_at timestamptz NOT NULL,
    actual double precision,
    consensus double precision,
    previous double precision,
    unit text,
    source text NOT NULL,
    source_item_id text,
    time_quality text NOT NULL
        CHECK (time_quality IN ('EXACT_SOURCE_TS','PUBLISHER_TS','FIRST_SEEN_TS','DATE_ONLY')),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (available_at >= release_at)
);

CREATE INDEX IF NOT EXISTS idx_macro_release_available
    ON public.macro_release_observation (available_at DESC);

CREATE INDEX IF NOT EXISTS idx_macro_release_indicator_available
    ON public.macro_release_observation (indicator_key, available_at DESC);

CREATE OR REPLACE VIEW public.v_macro_release_latest AS
SELECT DISTINCT ON (indicator_key)
       observation_id, indicator_key, event_name, market,
       release_at, available_at, actual, consensus, previous,
       unit, source, source_item_id, time_quality, payload,
       created_at, updated_at
FROM public.macro_release_observation
ORDER BY indicator_key, available_at DESC, observation_id DESC;


CREATE TABLE IF NOT EXISTS public.macro_policy_repricing_observation (
    observation_id text PRIMARY KEY,
    event_name text NOT NULL,
    event_at timestamptz NOT NULL,
    available_at timestamptz NOT NULL,
    repricing_bps double precision NOT NULL,
    horizon text NOT NULL DEFAULT 'NEXT_FOMC',
    source text NOT NULL,
    source_item_id text,
    time_quality text NOT NULL
        CHECK (time_quality IN ('EXACT_SOURCE_TS','PUBLISHER_TS','FIRST_SEEN_TS','DATE_ONLY')),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (available_at >= event_at)
);

CREATE INDEX IF NOT EXISTS idx_macro_policy_repricing_available
    ON public.macro_policy_repricing_observation (available_at DESC);

CREATE OR REPLACE VIEW public.v_macro_policy_repricing_latest AS
SELECT DISTINCT ON (horizon)
       observation_id,event_name,event_at,available_at,repricing_bps,
       horizon,source,source_item_id,time_quality,payload,created_at,updated_at
FROM public.macro_policy_repricing_observation
ORDER BY horizon, available_at DESC, observation_id DESC;
