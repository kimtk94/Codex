-- R5_LIVE_TOP1 live-vs-research attribution.
-- Read-only analytical query. No production trading state is mutated.

WITH entry_exec AS (
    SELECT
        te.client_order_id,
        te.run_id,
        te.symbol,
        te.signal_as_of,
        te.status,
        te.estimated_notional_krw,
        te.created_at,
        te.metadata->'signal_context' AS signal_context,
        COALESCE(
            (te.metadata->'signal_context'->>'research_non_overlap_entry')::boolean,
            false
        ) AS research_non_overlap_entry
    FROM trade_execution te
    WHERE te.market = 'US'
      AND te.side = 'BUY'
      AND te.strategy_version = 'R5.1_BASE_HGB'
      AND te.signal_policy = 'R5_LIVE_TOP1'
),
closed AS (
    SELECT
        mp.entry_client_order_id,
        mp.state,
        mp.exit_reason,
        (mp.metadata->'execution_quality'->'round_trip'->>'net_return_pct')::double precision
            AS net_return_pct
    FROM managed_position_mirror mp
    WHERE mp.market = 'US'
      AND mp.strategy_version = 'R5.1_BASE_HGB'
)
SELECT
    CASE
        WHEN e.research_non_overlap_entry THEN 'RESEARCH_NON_OVERLAP'
        ELSE 'LIVE_OVERLAP_ADDED'
    END AS cohort,
    count(*) AS entries,
    count(*) FILTER (WHERE c.net_return_pct IS NOT NULL) AS closed_with_return,
    avg(c.net_return_pct) FILTER (WHERE c.net_return_pct IS NOT NULL) AS avg_net_return_pct,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY c.net_return_pct)
        FILTER (WHERE c.net_return_pct IS NOT NULL) AS median_net_return_pct,
    avg((c.net_return_pct > 0)::int::double precision)
        FILTER (WHERE c.net_return_pct IS NOT NULL) AS win_rate,
    sum(e.estimated_notional_krw) AS estimated_entry_notional_krw
FROM entry_exec e
LEFT JOIN closed c
  ON c.entry_client_order_id = e.client_order_id
GROUP BY 1
ORDER BY 1;
