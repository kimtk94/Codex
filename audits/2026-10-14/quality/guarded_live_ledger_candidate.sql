-- Candidate consumer projection ONLY, for disposable PostgreSQL integration.
-- This is not a production migration. Source trade/order provenance has to be
-- independently attested before a numeric NET RETURN may be displayed.
-- Market gross price return and portfolio P&L are different metrics.
CREATE VIEW v_live_trade_ledger_guarded_candidate AS
WITH parsed AS (
 SELECT p.position_id, p.state, p.remaining_quantity,
        p.entry_filled_quantity, p.exit_filled_quantity,
        p.metadata #>> '{execution_quality,round_trip,quality_status}' AS local_quality,
        (p.metadata #> '{execution_quality,round_trip,independent_order_manifest_verified}')
            = 'true'::jsonb AS manifest_ok,
        CASE WHEN (p.metadata #>> '{execution_quality,entry,filled_quantity}') ~ '^[0-9]+([.][0-9]+)?$'
          THEN (p.metadata #>> '{execution_quality,entry,filled_quantity}')::numeric END AS covered_entry_qty,
        CASE WHEN (p.metadata #>> '{execution_quality,exit,filled_quantity}') ~ '^[0-9]+([.][0-9]+)?$'
          THEN (p.metadata #>> '{execution_quality,exit,filled_quantity}')::numeric END AS covered_exit_qty,
        CASE WHEN (p.metadata #>> '{execution_quality,entry,commission}') ~ '^[0-9]+([.][0-9]+)?$'
          THEN (p.metadata #>> '{execution_quality,entry,commission}')::numeric END AS entry_commission,
        CASE WHEN (p.metadata #>> '{execution_quality,exit,commission}') ~ '^[0-9]+([.][0-9]+)?$'
          THEN (p.metadata #>> '{execution_quality,exit,commission}')::numeric END AS exit_commission,
        CASE WHEN (p.metadata #>> '{execution_quality,entry,tax}') ~ '^[0-9]+([.][0-9]+)?$'
          THEN (p.metadata #>> '{execution_quality,entry,tax}')::numeric END AS entry_tax,
        CASE WHEN (p.metadata #>> '{execution_quality,exit,tax}') ~ '^[0-9]+([.][0-9]+)?$'
          THEN (p.metadata #>> '{execution_quality,exit,tax}')::numeric END AS exit_tax,
        p.metadata #>> '{execution_quality,entry,broker_currency}' AS entry_currency,
        p.metadata #>> '{execution_quality,exit,broker_currency}' AS exit_currency,
        p.metadata #>> '{execution_quality,entry,fee_currency}' AS entry_fee_currency,
        p.metadata #>> '{execution_quality,exit,fee_currency}' AS exit_fee_currency
 FROM managed_position_mirror p
), eligibility AS (
 SELECT p.position_id,
   (
      p.state = 'CLOSED'
      AND p.remaining_quantity = 0
      AND p.entry_filled_quantity > 0
      AND p.exit_filled_quantity > 0
      AND p.local_quality = 'FULL_LEG_COVERAGE'
      AND p.manifest_ok IS TRUE
      AND abs(p.covered_entry_qty-p.entry_filled_quantity) <= 0.00000001
      AND abs(p.covered_exit_qty-p.exit_filled_quantity) <= 0.00000001
      AND p.entry_commission IS NOT NULL AND p.entry_tax IS NOT NULL
      AND p.exit_commission IS NOT NULL AND p.exit_tax IS NOT NULL
      AND p.entry_currency IN ('USD','KRW')
      AND p.entry_currency = p.exit_currency
      AND p.entry_fee_currency = p.entry_currency
      AND p.exit_fee_currency = p.exit_currency
   ) IS TRUE AS eligible
 FROM parsed p
)
SELECT v.position_id, v.symbol, v.state, v.realized_return_pct,
       CASE WHEN e.eligible THEN v.net_return ELSE NULL::numeric END AS net_return,
       CASE WHEN e.eligible THEN v.round_trip_cost_bps ELSE NULL::numeric END AS round_trip_cost_bps,
       CASE WHEN e.eligible THEN 'LOCAL_PROVENANCE_ATTESTED'
            ELSE 'UNVERIFIED' END AS net_return_evidence_status
FROM v_live_trade_ledger v
JOIN eligibility e ON e.position_id = v.position_id;
