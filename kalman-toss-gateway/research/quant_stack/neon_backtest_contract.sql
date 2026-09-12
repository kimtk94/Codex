-- Kalman Quant Research schema draft
-- 2026-09-12
--
-- IMPORTANT:
-- This file is a contract proposal only. It is NOT automatically applied to Neon.
-- Backtest/research rows must remain separate from production strategy_ledger.

CREATE TABLE IF NOT EXISTS quant_experiment (
    experiment_id text PRIMARY KEY,
    experiment_name text NOT NULL,
    market text NOT NULL,
    mode text NOT NULL CHECK (mode IN ('BACKTEST', 'SHADOW', 'LIVE')),
    feature_version text NOT NULL,
    model_version text NOT NULL,
    start_date date NOT NULL,
    git_sha text,
    parameter_hash text NOT NULL,
    status text NOT NULL DEFAULT 'RESEARCH',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS experiment_fold (
    experiment_id text NOT NULL REFERENCES quant_experiment(experiment_id),
    fold_id integer NOT NULL,
    train_start timestamptz NOT NULL,
    train_end timestamptz NOT NULL,
    valid_start timestamptz NOT NULL,
    valid_end timestamptz NOT NULL,
    test_start timestamptz NOT NULL,
    test_end timestamptz NOT NULL,
    purge_observations integer NOT NULL,
    selected_features jsonb NOT NULL DEFAULT '[]'::jsonb,
    best_c double precision,
    entry_threshold double precision,
    validation_metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    test_metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (experiment_id, fold_id)
);

CREATE TABLE IF NOT EXISTS strategy_backtest_run (
    backtest_id text PRIMARY KEY,
    experiment_id text NOT NULL REFERENCES quant_experiment(experiment_id),
    market text NOT NULL,
    symbol text NOT NULL,
    config jsonb NOT NULL DEFAULT '{}'::jsonb,
    metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'READY',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS strategy_backtest_trade (
    backtest_id text NOT NULL REFERENCES strategy_backtest_run(backtest_id),
    trade_no integer NOT NULL,
    symbol text NOT NULL,
    entry_ts timestamptz NOT NULL,
    exit_ts timestamptz,
    qty double precision NOT NULL,
    entry_price double precision NOT NULL,
    exit_price double precision,
    entry_fee double precision NOT NULL DEFAULT 0,
    exit_fee double precision NOT NULL DEFAULT 0,
    gross_pnl double precision,
    net_pnl double precision,
    return_pct double precision,
    exit_reason text,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (backtest_id, trade_no)
);

CREATE TABLE IF NOT EXISTS strategy_daily_equity (
    backtest_id text NOT NULL REFERENCES strategy_backtest_run(backtest_id),
    ts date NOT NULL,
    cash double precision NOT NULL,
    position_value double precision NOT NULL,
    equity double precision NOT NULL,
    open_positions integer NOT NULL,
    PRIMARY KEY (backtest_id, ts)
);

CREATE TABLE IF NOT EXISTS strategy_performance (
    backtest_id text PRIMARY KEY REFERENCES strategy_backtest_run(backtest_id),
    total_return double precision,
    cagr double precision,
    annualized_volatility double precision,
    sharpe double precision,
    sortino double precision,
    max_drawdown double precision,
    win_rate double precision,
    profit_factor double precision,
    trade_count integer,
    exposure double precision,
    metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    computed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_quant_experiment_market_created
    ON quant_experiment (market, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_strategy_backtest_run_experiment
    ON strategy_backtest_run (experiment_id, created_at DESC);
