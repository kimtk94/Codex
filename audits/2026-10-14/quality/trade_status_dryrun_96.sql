-- Kalman trade_execution 96-row audit / DRY RUN ONLY.
-- Use a SELECT-only database role. Never modify Production.
-- GitHub audit-branch candidate code: engine/trade_mirror.py, broker_status_evidence.py
-- All 21 stale SUBMITTED rows were eligible on 2026-10-14; always rerun before release.

WITH evidence AS (
 SELECT
   e.symbol, e.side, e.status, e.broker_order_id,
   e.filled_quantity, e.average_filled_price,
   e.metadata ->> 'status_source' AS source,
   e.metadata #>> '{execution_telemetry,broker_order,status}' AS broker_status,
   e.metadata #>> '{execution_telemetry,broker_order,order_id}' AS telemetry_order_id,
   e.metadata #>> '{execution_telemetry,broker_order,response_meta,status_code}' AS response_status,
   e.metadata #>> '{execution_telemetry,broker_order,filled_quantity}' AS broker_filled_quantity,
   e.metadata #>> '{execution_telemetry,broker_order,average_filled_price}' AS broker_average_price,
   e.metadata #>> '{execution_telemetry,broker_order,filled_at}' AS broker_filled_at
 FROM public.trade_execution e
), classified AS (
 SELECT *,
   (
     status = 'SUBMITTED'
     AND source = 'order_guard'
     AND broker_status = 'FILLED'
     AND telemetry_order_id = broker_order_id
     AND response_status = '200'
     AND broker_filled_quantity ~ '^[0-9]+(\.[0-9]+)?$'
     AND broker_average_price ~ '^[0-9]+(\.[0-9]+)?$'
     AND CASE WHEN broker_filled_quantity ~ '^[0-9]+(\.[0-9]+)?$'
          THEN broker_filled_quantity::numeric > 0 ELSE FALSE END
     AND CASE WHEN broker_average_price ~ '^[0-9]+(\.[0-9]+)?$'
          THEN broker_average_price::numeric > 0 ELSE FALSE END
     AND broker_filled_at ~ '^20[0-9]{2}-[0-9]{2}-[0-9]{2}T'
     AND broker_filled_at ~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
   ) AS would_project_historical_fill
 FROM evidence
)
SELECT status AS existing_status,
       CASE WHEN would_project_historical_fill THEN 'FILLED' ELSE status END AS projected_status,
       side,
       COUNT(*) AS row_count,
       COUNT(*) FILTER(WHERE would_project_historical_fill) AS changed_rows,
       COUNT(*) FILTER(WHERE would_project_historical_fill AND filled_quantity IS NULL) AS fill_quantity_backfilled,
       COUNT(*) FILTER(WHERE would_project_historical_fill AND average_filled_price IS NULL) AS avg_price_backfilled
FROM classified
GROUP BY 1,2,3
ORDER BY 1,2,3;

-- Mirrors are synchronized periodically: updated_at is NOT a broker observation clock.
SELECT date_trunc('minute',updated_at) AS sync_minute, COUNT(*) AS row_count
FROM public.trade_execution
GROUP BY 1 ORDER BY 2 DESC LIMIT 8;

-- LRCX episode weighted-average cross-check, read-only.
SELECT p.remaining_quantity AS mirror_remaining,
       p.entry_average_price AS mirror_avg_price,
       SUM(CASE WHEN e.side='BUY'
                 AND e.created_at >= p.first_seen_at - interval '5 seconds'
           THEN (e.metadata #>> '{execution_telemetry,broker_order,filled_quantity}')::numeric
           ELSE 0 END) AS current_episode_buy_qty,
       SUM(CASE WHEN e.side='BUY'
                 AND e.created_at >= p.first_seen_at - interval '5 seconds'
           THEN (e.metadata #>> '{execution_telemetry,broker_order,filled_quantity}')::numeric *
                (e.metadata #>> '{execution_telemetry,broker_order,average_filled_price}')::numeric
           ELSE 0 END) /
         NULLIF(SUM(CASE WHEN e.side='BUY'
                 AND e.created_at >= p.first_seen_at - interval '5 seconds'
           THEN (e.metadata #>> '{execution_telemetry,broker_order,filled_quantity}')::numeric
           ELSE 0 END),0) AS calculated_avg_price
FROM public.managed_position_mirror p
JOIN public.trade_execution e ON e.symbol=p.symbol
WHERE p.state='OPEN' AND p.symbol='LRCX'
GROUP BY p.remaining_quantity,p.entry_average_price;
