-- Read-only captured Production definition on 2026-10-15 KST.
-- Executed exclusively inside disposable CI PostgreSQL, never against production.
CREATE VIEW v_live_trade_ledger AS
SELECT position_id,
    market,
    symbol,
    strategy_version,
    state,
    entry_signal_as_of,
    entry_order_id,
    entry_filled_quantity,
    entry_average_price,
    exit_order_id,
    exit_filled_quantity,
    exit_average_price,
    exit_reason,
        CASE
            WHEN entry_average_price IS NOT NULL AND exit_average_price IS NOT NULL AND entry_average_price <> 0::numeric THEN exit_average_price / entry_average_price - 1::numeric
            ELSE NULL::numeric
        END AS realized_return_pct,
    note,
    first_seen_at,
    updated_at,
    NULLIF(metadata #>> '{execution_quality,round_trip,net_return}'::text[], ''::text)::numeric AS net_return,
    NULLIF(metadata #>> '{execution_quality,round_trip,round_trip_cost_bps}'::text[], ''::text)::numeric AS round_trip_cost_bps,
    NULLIF(metadata #>> '{execution_quality,entry,slippage_bps}'::text[], ''::text)::numeric AS entry_slippage_bps,
    NULLIF(metadata #>> '{execution_quality,exit,slippage_bps}'::text[], ''::text)::numeric AS exit_slippage_bps,
    NULLIF(metadata #>> '{execution_quality,entry,spread_bps}'::text[], ''::text)::numeric AS entry_spread_bps,
    NULLIF(metadata #>> '{execution_quality,exit,spread_bps}'::text[], ''::text)::numeric AS exit_spread_bps,
    NULLIF(metadata #>> '{execution_quality,entry,cost_bps}'::text[], ''::text)::numeric AS entry_cost_bps,
    NULLIF(metadata #>> '{execution_quality,exit,cost_bps}'::text[], ''::text)::numeric AS exit_cost_bps,
    NULLIF(metadata #>> '{execution_quality,entry,broker_fill_latency_ms}'::text[], ''::text)::double precision AS entry_fill_latency_ms,
    NULLIF(metadata #>> '{execution_quality,exit,broker_fill_latency_ms}'::text[], ''::text)::double precision AS exit_fill_latency_ms,
    NULLIF(metadata #>> '{execution_quality,entry,submit_http_latency_ms}'::text[], ''::text)::double precision AS entry_submit_latency_ms,
    NULLIF(metadata #>> '{execution_quality,exit,submit_http_latency_ms}'::text[], ''::text)::double precision AS exit_submit_latency_ms,
    NULLIF(metadata #>> '{execution_quality,entry,rate_limit_remaining}'::text[], ''::text)::integer AS entry_rate_limit_remaining,
    NULLIF(metadata #>> '{execution_quality,exit,rate_limit_remaining}'::text[], ''::text)::integer AS exit_rate_limit_remaining
   FROM managed_position_mirror;
