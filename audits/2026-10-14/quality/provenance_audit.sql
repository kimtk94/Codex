-- Read-only evidence. Run with SELECT-only role. No DML, no mutation.
-- Displayed status vs historical broker telemetry status.
SELECT e.status AS mirror_status,
       e.metadata ->> 'status_source' AS mirror_status_source,
       e.metadata #>> '{execution_telemetry,broker_order,status}' AS broker_telemetry_status,
       count(*) AS n
FROM public.trade_execution e
GROUP BY 1,2,3
ORDER BY 1,2,3;

-- Check all validation predicates for stale SUBMITTED records.
SELECT count(*) AS submitted_total,
       count(*) FILTER (
         WHERE e.metadata #>> '{execution_telemetry,broker_order,status}' = 'FILLED'
           AND e.metadata #>> '{execution_telemetry,broker_order,order_id}' = e.broker_order_id
           AND e.metadata #>> '{execution_telemetry,broker_order,response_meta,status_code}' = '200'
           AND (e.metadata #>> '{execution_telemetry,broker_order,filled_quantity}') ~ '^[0-9]+(\.[0-9]+)?$'
           AND (e.metadata #>> '{execution_telemetry,broker_order,filled_quantity}')::numeric > 0
           AND nullif(e.metadata #>> '{execution_telemetry,broker_order,filled_at}', '') IS NOT NULL
       ) AS historical_broker_fill_evidence,
       count(*) FILTER (WHERE e.filled_quantity IS NULL) AS missing_mirror_fill_qty,
       count(*) FILTER (WHERE e.average_filled_price IS NULL) AS missing_mirror_avg_price
FROM public.trade_execution e
WHERE e.status = 'SUBMITTED';

-- Batch timestamp is mirror update provenance, not broker observation time.
SELECT date_trunc('minute', updated_at) AS mirror_update_minute,
       count(*) AS rows_refreshed
FROM public.trade_execution
GROUP BY 1 ORDER BY rows_refreshed DESC LIMIT 12;
