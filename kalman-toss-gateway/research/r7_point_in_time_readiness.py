#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import psycopg

SCHEMA = "kalman-r7-point-in-time-readiness-v1"

SQL = {
    "macro_release": """
        SELECT
          count(*)::bigint AS n,
          min(available_at) AS first_available,
          max(available_at) AS last_available,
          count(DISTINCT indicator_key)::bigint AS indicators,
          avg((actual IS NOT NULL)::int)::float8 AS actual_ratio,
          avg((consensus IS NOT NULL)::int)::float8 AS consensus_ratio,
          avg((time_quality IN ('EXACT_SOURCE_TS','PUBLISHER_TS','PROVIDER_RELEASE_TS'))::int)::float8 AS strong_time_ratio
        FROM macro_release_observation
        WHERE market IN ('US','GLOBAL')
    """,
    "macro_repricing": """
        SELECT count(*)::bigint AS n,
               min(available_at) AS first_available,
               max(available_at) AS last_available
        FROM macro_policy_repricing_observation
    """,
    "news_article": """
        SELECT
          count(*)::bigint AS n,
          min(available_at) AS first_available,
          max(available_at) AS last_available,
          count(DISTINCT source)::bigint AS sources,
          avg((time_quality IN ('EXACT_SOURCE_TS','PUBLISHER_TS','FIRST_SEEN_TS'))::int)::float8 AS usable_time_ratio
        FROM news_article
    """,
    "news_entity": """
        SELECT
          count(*)::bigint AS n,
          count(DISTINCT CASE
            WHEN market='US' AND symbol NOT IN ('US_NEWS','GLOBAL') THEN symbol
          END)::bigint AS us_stock_symbols,
          count(DISTINCT article_id)::bigint AS mapped_articles
        FROM news_entity
    """,
    "news_snapshot": """
        SELECT
          count(*)::bigint AS n,
          min(as_of) AS first_as_of,
          max(as_of) AS last_as_of,
          count(DISTINCT CASE
            WHEN market='US' AND symbol NOT IN ('US_NEWS','GLOBAL') THEN symbol
          END)::bigint AS us_stock_symbols,
          count(DISTINCT feature_version)::bigint AS versions
        FROM news_feature_snapshot
    """,
    "news_coverage": """
        SELECT
          count(*)::bigint AS n,
          avg(duplicate_ratio)::float8 AS duplicate_ratio,
          avg(unmapped_ratio)::float8 AS unmapped_ratio,
          avg(exact_ts_ratio)::float8 AS exact_ts_ratio
        FROM news_coverage_hourly
    """,
}

def years_between(a, b):
    if a is None or b is None:
        return 0.0
    return max(0.0, (b - a).total_seconds() / (365.2425 * 86400.0))

def one(cur, sql):
    cur.execute(sql)
    row = cur.fetchone()
    cols = [d.name for d in cur.description]
    return dict(zip(cols, row))

def main():
    dsn = os.getenv("NEON_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not dsn:
        raise SystemExit("Set NEON_DATABASE_URL or DATABASE_URL")

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        data = {k: one(cur, q) for k, q in SQL.items()}

    m = data["macro_release"]
    macro_span = years_between(m["first_available"], m["last_available"])
    macro_ready = bool(
        m["n"] >= 120
        and macro_span >= 2
        and m["indicators"] >= 5
        and (m["actual_ratio"] or 0) >= 0.95
        and (m["consensus_ratio"] or 0) >= 0.80
        and (m["strong_time_ratio"] or 0) >= 0.95
    )

    na = data["news_article"]
    ne = data["news_entity"]
    ns = data["news_snapshot"]
    nc = data["news_coverage"]
    news_span = years_between(na["first_available"], na["last_available"])
    news_ready = bool(
        na["n"] > 0
        and news_span >= 1
        and ne["us_stock_symbols"] >= 80
        and ns["us_stock_symbols"] >= 80
        and (na["usable_time_ratio"] or 0) >= 0.95
        and (nc["duplicate_ratio"] is None or nc["duplicate_ratio"] <= 0.20)
        and (nc["unmapped_ratio"] is None or nc["unmapped_ratio"] <= 0.25)
    )

    report = {
        "schema": SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "production_changed": False,
        "r5_1_untouched": True,
        "axes": {
            "M_MACRO": {
                "status": "READY" if macro_ready else "BLOCKED",
                "span_years": macro_span,
                "observed": m,
                "repricing": data["macro_repricing"],
                "blockers": [] if macro_ready else [
                    "MACRO_RELEASE_HISTORY_INSUFFICIENT_OR_EMPTY",
                    "CONSENSUS_SURPRISE_COVERAGE_NOT_READY",
                    "INTRADAY_EVENT_REACTION_CONTRACT_NOT_VERIFIED",
                ],
            },
            "N_NEWS": {
                "status": "READY" if news_ready else "BLOCKED",
                "span_years": news_span,
                "articles": na,
                "entities": ne,
                "snapshots": ns,
                "coverage": nc,
                "blockers": [] if news_ready else [
                    "SYMBOL_LEVEL_HISTORY_INSUFFICIENT",
                    "R5_UNIVERSE_COVERAGE_NOT_READY",
                ],
            },
            "E_EARNINGS_REVISIONS": {
                "status": "BLOCKED",
                "blockers": [
                    "NO_POINT_IN_TIME_ANALYST_REVISION_DATA_CONTRACT"
                ],
            },
        },
        "r7_1_model_fitting_allowed": False,
    }
    report["r7_1_model_fitting_allowed"] = any(
        x["status"] == "READY" for x in report["axes"].values()
    )

    print(json.dumps(report, indent=2, default=str))

if __name__ == "__main__":
    main()
