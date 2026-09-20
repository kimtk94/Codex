-- Kalman News/Event ingestion v1
-- Additive sidecar schema. Does not alter R5.1 scoring or live-trading tables.

CREATE TABLE IF NOT EXISTS public.news_article (
    article_id text PRIMARY KEY,
    source text NOT NULL,
    source_item_id text,
    canonical_url text,
    title text NOT NULL,
    summary text,
    published_at timestamptz,
    first_seen_at timestamptz NOT NULL,
    available_at timestamptz NOT NULL,
    time_quality text NOT NULL CHECK (time_quality IN ('EXACT_SOURCE_TS','PUBLISHER_TS','FIRST_SEEN_TS','GDELT_OBSERVED_PROXY','DATE_ONLY')),
    language text,
    content_sha256 text,
    raw_drive_path text,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_news_article_available_at ON public.news_article (available_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_article_source_available ON public.news_article (source, available_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_article_published_at ON public.news_article (published_at DESC);

CREATE TABLE IF NOT EXISTS public.news_entity (
    article_id text NOT NULL REFERENCES public.news_article(article_id) ON DELETE CASCADE,
    market text NOT NULL CHECK (market IN ('US','KR','CRYPTO','GLOBAL')),
    symbol text NOT NULL,
    entity_type text NOT NULL DEFAULT 'ASSET',
    relevance double precision NOT NULL DEFAULT 1.0 CHECK (relevance >= 0.0 AND relevance <= 1.0),
    mapping_method text NOT NULL,
    mapping_version text NOT NULL DEFAULT 'news-entity-v1',
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (article_id, market, symbol)
);
CREATE INDEX IF NOT EXISTS idx_news_entity_market_symbol ON public.news_entity (market, symbol, article_id);

CREATE TABLE IF NOT EXISTS public.news_event (
    article_id text NOT NULL REFERENCES public.news_article(article_id) ON DELETE CASCADE,
    event_type text NOT NULL,
    direction double precision CHECK (direction >= -1.0 AND direction <= 1.0),
    sentiment double precision CHECK (sentiment >= -1.0 AND sentiment <= 1.0),
    novelty double precision CHECK (novelty >= 0.0 AND novelty <= 1.0),
    importance double precision CHECK (importance >= 0.0 AND importance <= 1.0),
    confidence double precision CHECK (confidence >= 0.0 AND confidence <= 1.0),
    model_version text NOT NULL DEFAULT 'news-event-v1',
    classified_at timestamptz NOT NULL DEFAULT now(),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (article_id, event_type, model_version)
);

CREATE TABLE IF NOT EXISTS public.news_source_state (
    source text PRIMARY KEY,
    market_scope text[] NOT NULL DEFAULT ARRAY['GLOBAL']::text[],
    cursor text,
    etag text,
    last_modified text,
    last_attempt_at timestamptz,
    last_success_at timestamptz,
    last_error_at timestamptz,
    last_error text,
    rows_seen bigint NOT NULL DEFAULT 0,
    rows_inserted bigint NOT NULL DEFAULT 0,
    rows_duplicate bigint NOT NULL DEFAULT 0,
    lag_seconds double precision,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.news_coverage_hourly (
    as_of timestamptz NOT NULL,
    market text NOT NULL CHECK (market IN ('US','KR','CRYPTO','GLOBAL')),
    source text NOT NULL,
    articles integer NOT NULL DEFAULT 0,
    mapped_articles integer NOT NULL DEFAULT 0,
    unique_symbols integer NOT NULL DEFAULT 0,
    duplicate_count integer NOT NULL DEFAULT 0,
    duplicate_ratio double precision,
    unmapped_ratio double precision,
    latency_p50_seconds double precision,
    latency_p95_seconds double precision,
    exact_ts_ratio double precision,
    quality_flag text NOT NULL DEFAULT 'UNKNOWN',
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (as_of, market, source)
);

CREATE TABLE IF NOT EXISTS public.news_feature_snapshot (
    market text NOT NULL CHECK (market IN ('US','KR','CRYPTO','GLOBAL')),
    symbol text NOT NULL,
    as_of timestamptz NOT NULL,
    feature_version text NOT NULL DEFAULT 'news-event-feature-v1',
    features jsonb NOT NULL,
    coverage_confidence double precision CHECK (coverage_confidence >= 0.0 AND coverage_confidence <= 1.0),
    run_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (market, symbol, as_of, feature_version)
);
CREATE INDEX IF NOT EXISTS idx_news_feature_latest ON public.news_feature_snapshot (market, symbol, as_of DESC);

CREATE OR REPLACE VIEW public.v_news_latest_coverage AS
SELECT DISTINCT ON (market, source)
       as_of, market, source, articles, mapped_articles, unique_symbols,
       duplicate_count, duplicate_ratio, unmapped_ratio,
       latency_p50_seconds, latency_p95_seconds, exact_ts_ratio,
       quality_flag, payload
FROM public.news_coverage_hourly
ORDER BY market, source, as_of DESC;

CREATE OR REPLACE VIEW public.v_news_feature_latest AS
SELECT DISTINCT ON (market, symbol, feature_version)
       market, symbol, as_of, feature_version, features,
       coverage_confidence, run_id, created_at
FROM public.news_feature_snapshot
ORDER BY market, symbol, feature_version, as_of DESC;
