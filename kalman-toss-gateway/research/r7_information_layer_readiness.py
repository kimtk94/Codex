#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


SCHEMA = "kalman-r7-information-readiness-v1"


def scalar(cur, sql):
    cur.execute(sql)
    row = cur.fetchone()
    return row


def assess(stats: dict) -> dict:
    macro = stats["macro_release"]
    repricing = stats["macro_repricing"]
    news = stats["company_news"]
    earnings = stats["earnings"]

    macro_span_days = macro.get("span_days") or 0
    macro_ready = (
        macro["n"] >= 150
        and macro["actual_rate"] >= 0.95
        and macro["consensus_rate"] >= 0.90
        and macro["good_time_rate"] >= 0.90
        and macro["lookahead_violations"] == 0
        and macro_span_days >= 730
    )

    repricing_ready = (
        repricing["n"] >= 150
        and repricing["coverage_vs_macro"] >= 0.85
        and repricing["lookahead_violations"] == 0
    )

    news_ready = (
        news["n"] >= 5000
        and news["symbols"] >= 80
        and (news.get("span_days") or 0) >= 365
        and news["avg_coverage"] >= 0.70
    )

    earnings_ready = bool(earnings.get("pit_table_present", False))

    return {
        "macro_consensus_surprise": "READY" if macro_ready else "BLOCKED",
        "macro_event_repricing": "READY" if repricing_ready else "BLOCKED",
        "company_news": "READY" if news_ready else "BLOCKED",
        "earnings_revisions": "READY" if earnings_ready else "BLOCKED",
        "r7_1_runnable_candidates": [
            x for x, ok in [
                ("R7C1_MACRO_EVENT_HGB", macro_ready and repricing_ready),
                ("R7C2_COMPANY_NEWS_HGB", news_ready),
                ("R7C3_EARNINGS_REV_HGB", earnings_ready),
            ] if ok
        ],
    }


def collect(conn) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        macro = scalar(cur, """
            select
              count(*)::bigint as n,
              coalesce(avg((actual is not null)::int),0)::float as actual_rate,
              coalesce(avg((consensus is not null)::int),0)::float as consensus_rate,
              coalesce(avg((time_quality in ('EXACT_SOURCE_TS','PUBLISHER_TS','PROVIDER_RELEASE_TS'))::int),0)::float as good_time_rate,
              count(*) filter (where available_at < release_at)::bigint as lookahead_violations,
              extract(epoch from (max(release_at)-min(release_at)))/86400.0 as span_days
            from macro_release_observation
            where market='US'
        """)

        repricing = scalar(cur, """
            select
              count(*)::bigint as n,
              count(*) filter (where available_at < event_at)::bigint as lookahead_violations
            from macro_policy_repricing_observation
        """)
        repricing["coverage_vs_macro"] = (
            float(repricing["n"]) / float(macro["n"]) if macro["n"] else 0.0
        )

        news = scalar(cur, """
            select
              count(*)::bigint as n,
              count(distinct symbol)::bigint as symbols,
              coalesce(avg(coverage_confidence),0)::float as avg_coverage,
              extract(epoch from (max(as_of)-min(as_of)))/86400.0 as span_days
            from news_feature_snapshot
            where market='US' and symbol <> 'GLOBAL'
        """)

        cur.execute("""
            select table_name
            from information_schema.tables
            where table_schema='public'
              and (
                lower(table_name) like '%earn%'
                or lower(table_name) like '%estimate%'
                or lower(table_name) like '%revision%'
              )
            order by table_name
        """)
        earnings_tables = [r["table_name"] for r in cur.fetchall()]

        counts = scalar(cur, """
            select
              (select count(*) from news_article)::bigint as news_articles,
              (select count(*) from news_feature_snapshot)::bigint as news_snapshots,
              (select count(*) from macro_shadow_evaluation_v1)::bigint as macro_shadow_rows
        """)

    return {
        "macro_release": dict(macro),
        "macro_repricing": dict(repricing),
        "company_news": dict(news),
        "earnings": {
            "pit_table_present": bool(earnings_tables),
            "candidate_tables": earnings_tables,
        },
        "inventory": dict(counts),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--database-url", default=os.getenv("NEON_DATABASE_URL") or os.getenv("DATABASE_URL"))
    p.add_argument("--out", default="r7_information_readiness.json")
    args = p.parse_args()
    if not args.database_url:
        raise SystemExit("NEON_DATABASE_URL or DATABASE_URL is required")

    with psycopg.connect(args.database_url, autocommit=True) as conn:
        stats = collect(conn)

    result = {
        "schema": SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "production_changed": False,
        "stats": stats,
        "decision": assess(stats),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
