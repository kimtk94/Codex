-- Kalman R9 News research-only Neon store
-- BigQuery remains the historical extraction source. Neon is the durable store/serving layer.

CREATE SCHEMA IF NOT EXISTS research;

CREATE TABLE IF NOT EXISTS research.r9_news_alias_registry (
    symbol text PRIMARY KEY,
    company_name text NOT NULL,
    alias text NOT NULL,
    alias_lower text NOT NULL,
    ngram_order smallint NOT NULL CHECK (ngram_order IN (1, 2)),
    status text NOT NULL CHECK (status = 'SUPPORTED'),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS research.r9_news_mentions_daily (
    symbol text NOT NULL REFERENCES research.r9_news_alias_registry(symbol),
    day_utc date NOT NULL,
    mention_count bigint NOT NULL CHECK (mention_count >= 0),
    source text NOT NULL DEFAULT 'GDELT_BIGQUERY_WEB_1GRAMS_2GRAMS',
    loaded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, day_utc)
);

CREATE INDEX IF NOT EXISTS idx_r9_news_mentions_daily_day
    ON research.r9_news_mentions_daily(day_utc);

CREATE TABLE IF NOT EXISTS research.r9_news_manifest (
    manifest_key text PRIMARY KEY,
    payload jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
