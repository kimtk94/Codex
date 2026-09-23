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


-- R9.2 prospective shadow is isolated from production trading state.
CREATE TABLE IF NOT EXISTS research.r9_shadow_source_state (
    source_key text PRIMARY KEY,
    last_complete_day date,
    status text NOT NULL CHECK (
        status IN ('READY', 'WAITING', 'BLOCKED_QUOTA', 'FAILED')
    ),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS research.r9_shadow_feature_snapshot (
    symbol text NOT NULL REFERENCES research.r9_news_alias_registry(symbol),
    feature_as_of timestamptz NOT NULL,
    news_day_used date NOT NULL,
    feature_version text NOT NULL,
    ngram_log1p_d1 double precision NOT NULL,
    ngram_log1p_7d double precision NOT NULL,
    ngram_abnormal_z_30d double precision NOT NULL,
    source_complete boolean NOT NULL,
    run_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, feature_as_of, feature_version)
);

CREATE INDEX IF NOT EXISTS idx_r9_shadow_feature_snapshot_asof
    ON research.r9_shadow_feature_snapshot(feature_as_of);

CREATE TABLE IF NOT EXISTS research.r9_shadow_signal (
    signal_id text PRIMARY KEY,
    signal_as_of timestamptz NOT NULL,
    expected_seq bigint NOT NULL,
    expected_exit_seq bigint NOT NULL,
    selected_symbol text NOT NULL,
    score double precision NOT NULL,
    position_weight double precision NOT NULL,
    universe_coverage integer NOT NULL,
    news_day_used date NOT NULL,
    model_sha256 text NOT NULL,
    r5_selected_symbol text,
    r5_score double precision,
    top1_agree boolean,
    score_spearman double precision,
    top10_overlap integer,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_r9_shadow_signal_asof
    ON research.r9_shadow_signal(signal_as_of);

CREATE TABLE IF NOT EXISTS research.r9_shadow_trade_entry (
    trade_id text PRIMARY KEY,
    signal_id text NOT NULL REFERENCES research.r9_shadow_signal(signal_id),
    signal_as_of timestamptz NOT NULL,
    expected_seq bigint NOT NULL,
    expected_exit_seq bigint NOT NULL,
    selected_symbol text NOT NULL,
    score double precision NOT NULL,
    position_weight double precision NOT NULL,
    model_sha256 text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS research.r9_shadow_outcome (
    trade_id text PRIMARY KEY REFERENCES research.r9_shadow_trade_entry(trade_id),
    signal_as_of timestamptz NOT NULL,
    entry_day date NOT NULL,
    expected_seq bigint NOT NULL,
    expected_exit_seq bigint NOT NULL,
    selected_symbol text NOT NULL,
    net10_return double precision NOT NULL,
    matched_qqq_net10_return double precision,
    matched_universe_net10_return double precision,
    log_excess_vs_qqq double precision,
    log_excess_vs_universe double precision,
    r5_selected_symbol text,
    r5_net10_return double precision,
    paired_log_diff_r9_minus_r5 double precision,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
