from __future__ import annotations

import json
import os

import psycopg
from dotenv import load_dotenv


BENCHMARKS = (
    ("TOP1_4B_10BP", 1),
    ("TOP6_EQUAL_4B_10BP", 6),
)


def sync_benchmark(conn, *, name: str, top_n: int, strategy_version: str, hold_buckets: int, cost_bps: float) -> int:
    sql = """
    WITH ranked AS (
      SELECT run_id, as_of, symbol, rank, score
      FROM model_output
      WHERE market='US'
        AND model_version=%s
        AND rank BETWEEN 1 AND %s
    ),
    fills AS (
      SELECT r.*,
             ep.close::double precision AS entry_price,
             xp.close::double precision AS exit_price
      FROM ranked r
      JOIN LATERAL (
        SELECT close
        FROM market_price p
        WHERE p.market='US'
          AND p.symbol=r.symbol
          AND p.timeframe='60m'
          AND p.ts <= r.as_of
        ORDER BY p.ts DESC
        LIMIT 1
      ) ep ON true
      JOIN LATERAL (
        SELECT close
        FROM (
          SELECT p.close, p.ts,
                 row_number() OVER (ORDER BY p.ts) AS rn
          FROM market_price p
          WHERE p.market='US'
            AND p.symbol=r.symbol
            AND p.timeframe='60m'
            AND p.ts > r.as_of
        ) q
        WHERE rn=%s
        LIMIT 1
      ) xp ON true
    ),
    snap AS (
      SELECT
        as_of,
        count(*) AS constituent_count,
        avg(exit_price/entry_price - 1.0) AS gross_return,
        jsonb_agg(
          jsonb_build_object(
            'rank', rank,
            'symbol', symbol,
            'score', score,
            'entry_price', entry_price,
            'exit_price', exit_price,
            'gross_return', exit_price/entry_price - 1.0
          ) ORDER BY rank
        ) AS constituents
      FROM fills
      WHERE entry_price > 0
      GROUP BY as_of
      HAVING count(*)=%s
    )
    INSERT INTO strategy_benchmark_ledger (
      market,strategy_version,benchmark_name,as_of,hold_buckets,top_n,
      constituent_count,cost_bps,gross_return,net_return,metadata,updated_at
    )
    SELECT
      'US',%s,%s,as_of,%s,%s,constituent_count,%s,gross_return,
      gross_return-(%s/10000.0),
      jsonb_build_object(
        'source','model_output+market_price',
        'weighting',CASE WHEN %s=1 THEN 'TOP1' ELSE 'EQUAL_WEIGHT' END,
        'exit_rule','MAX_HOLD_4_BUCKETS',
        'price_basis','signal-bar close to fourth subsequent 60m close',
        'cost_model','flat round-trip bps approximation',
        'constituents',constituents
      ),
      now()
    FROM snap
    ON CONFLICT (market,strategy_version,benchmark_name,as_of)
    DO UPDATE SET
      constituent_count=EXCLUDED.constituent_count,
      cost_bps=EXCLUDED.cost_bps,
      gross_return=EXCLUDED.gross_return,
      net_return=EXCLUDED.net_return,
      metadata=EXCLUDED.metadata,
      updated_at=now()
    RETURNING benchmark_id
    """
    params = (
        strategy_version,
        top_n,
        hold_buckets,
        top_n,
        strategy_version,
        name,
        hold_buckets,
        top_n,
        cost_bps,
        cost_bps,
        top_n,
    )
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return len(cur.fetchall())


def main() -> int:
    load_dotenv(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"), override=True)
    db_url = os.environ.get("DATABASE_URL_WRITER")
    if not db_url:
        raise RuntimeError("DATABASE_URL_WRITER is missing")

    strategy_version = os.environ.get("AUTO_TRADE_STRATEGY_VERSION", "R5.1_BASE_HGB").strip() or "R5.1_BASE_HGB"
    hold_buckets = int(os.environ.get("AUTO_TRADE_TARGET_EXIT_BUCKETS", "4"))
    cost_bps = float(os.environ.get("AUTO_TRADE_BENCHMARK_COST_BPS", "10"))

    report = {}
    with psycopg.connect(db_url) as conn:
        for name, top_n in BENCHMARKS:
            report[name] = sync_benchmark(
                conn,
                name=name,
                top_n=top_n,
                strategy_version=strategy_version,
                hold_buckets=hold_buckets,
                cost_bps=cost_bps,
            )
        conn.commit()

    print(json.dumps({
        "status": "READY",
        "strategyVersion": strategy_version,
        "holdBuckets": hold_buckets,
        "costBps": cost_bps,
        "upserts": report,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
