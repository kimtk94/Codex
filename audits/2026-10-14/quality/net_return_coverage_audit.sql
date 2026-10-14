-- SELECT-only verification of live mirror net-return fill coverage.
-- PRODUCTION SAFE: no INSERT/UPDATE/DELETE/DDL. Snapshot counts may evolve.
-- v_live_trade_ledger reads managed_position_mirror only (not trade_execution).
-- This query does not claim broker real-time reconciliation.
WITH per_position AS (
 SELECT m.position_id,m.symbol,m.state,
        m.entry_filled_quantity AS expected_entry_qty,
        m.exit_filled_quantity AS expected_exit_qty,
        nullif(m.metadata #>> '{execution_quality,entry,filled_quantity}','')::numeric AS observed_entry_qty,
        nullif(m.metadata #>> '{execution_quality,exit,filled_quantity}','')::numeric AS observed_exit_qty,
        v.realized_return_pct AS gross_return_fraction,
        v.net_return AS displayed_net_return_fraction
 FROM public.managed_position_mirror m
 JOIN public.v_live_trade_ledger v USING(position_id)
 WHERE m.state='CLOSED'
), classified AS (
 SELECT *, (
    displayed_net_return_fraction IS NOT NULL
    AND (observed_entry_qty IS NULL OR observed_exit_qty IS NULL
    OR abs(expected_entry_qty-observed_entry_qty)>0.00000001
    OR abs(expected_exit_qty-observed_exit_qty)>0.00000001)
 ) AS invalid_net_leg_coverage
 FROM per_position
)
SELECT count(*) AS total_closed,
       count(*) FILTER (WHERE displayed_net_return_fraction IS NOT NULL) AS net_displayed,
       count(*) FILTER (WHERE invalid_net_leg_coverage) AS net_unreliable,
       count(*) FILTER (
         WHERE displayed_net_return_fraction IS NOT NULL
           AND NOT invalid_net_leg_coverage
       ) AS net_leg_covered,
       round(avg(displayed_net_return_fraction)
             FILTER(WHERE displayed_net_return_fraction IS NOT NULL)*100,3)
         AS reported_mean_net_percent_on_36,
       round(avg(displayed_net_return_fraction)
             FILTER(WHERE displayed_net_return_fraction IS NOT NULL
               AND NOT invalid_net_leg_coverage)*100,3)
         AS leg_covered_mean_net_percent_on_31
FROM classified;

-- Returns are percentages only after *100: realized_return_pct view column
-- itself stores fraction (exit_avg / entry_avg - 1).
WITH p AS (
 SELECT m.symbol, v.realized_return_pct, v.net_return,
        m.entry_filled_quantity,
        nullif(m.metadata #>> '{execution_quality,entry,filled_quantity}','')::numeric AS covered_entry
 FROM public.managed_position_mirror m
 JOIN public.v_live_trade_ledger v USING(position_id)
 WHERE m.state='CLOSED' AND v.net_return IS NOT NULL
)
SELECT symbol,round(realized_return_pct*100,3) AS price_return_percent,
       round(net_return*100,3) AS reported_net_percent,
       entry_filled_quantity,covered_entry
FROM p WHERE covered_entry < entry_filled_quantity-0.00000001
ORDER BY net_return DESC;
