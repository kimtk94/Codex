-- Shadow-only tables derived from read-only Neon Production describe_table_schema
-- (2026-10-15). No actual accounts or Production connections.
CREATE TABLE managed_position_mirror (
    position_id TEXT PRIMARY KEY,
    run_id TEXT,
    market TEXT NOT NULL DEFAULT 'US',
    symbol TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    state TEXT NOT NULL,
    entry_signal_as_of TIMESTAMPTZ,
    entry_client_order_id TEXT,
    entry_order_id TEXT,
    entry_filled_quantity NUMERIC,
    entry_average_price NUMERIC,
    remaining_quantity NUMERIC,
    target_exit_buckets INTEGER,
    exit_client_order_id TEXT,
    exit_order_id TEXT,
    exit_filled_quantity NUMERIC,
    exit_average_price NUMERIC,
    note TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    exit_reason TEXT
);
CREATE INDEX idx_managed_position_mirror_state_updated
    ON managed_position_mirror (state, updated_at DESC);
CREATE TABLE trade_execution (
    execution_id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
    client_order_id TEXT NOT NULL UNIQUE,
    broker_order_id TEXT,
    run_id TEXT,
    market TEXT NOT NULL DEFAULT 'US',
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
    strategy_version TEXT NOT NULL,
    execution_mode TEXT NOT NULL CHECK (execution_mode IN ('DRY_RUN','LIVE')),
    signal_policy TEXT NOT NULL,
    signal_as_of TIMESTAMPTZ,
    status TEXT NOT NULL,
    requested_usd NUMERIC,
    requested_quantity NUMERIC,
    filled_quantity NUMERIC,
    average_filled_price NUMERIC,
    estimated_notional_krw BIGINT,
    position_id TEXT,
    error TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT trade_execution_market_check CHECK (market='US')
);
CREATE INDEX idx_trade_execution_symbol_updated
    ON trade_execution (symbol, updated_at DESC);
CREATE INDEX idx_trade_execution_position
    ON trade_execution (position_id, updated_at DESC)
    WHERE position_id IS NOT NULL;
