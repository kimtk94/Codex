from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row


UTC = timezone.utc
EVAL_VERSION = "macro-shadow-eval-v1"


def load_env() -> None:
    load_dotenv(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"), override=True)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def classify_free_macro_regime(
    features: dict[str, Any],
    config: dict[str, Any],
) -> str:
    thresholds = config.get("regime_thresholds_bps") or {}
    tightening = float(thresholds.get("tightening", 10.0))
    easing = float(thresholds.get("easing", -10.0))
    mixed_min_abs = float(thresholds.get("mixed_min_abs", 5.0))

    us2y = _float(features.get("us2y_change_bps_1d"))
    proxy = _float(features.get("policy_proxy_change_bps_1d"))
    if us2y is None or proxy is None:
        return "UNKNOWN"
    if us2y >= tightening and proxy >= tightening:
        return "TIGHTENING"
    if us2y <= easing and proxy <= easing:
        return "EASING"
    if abs(us2y) >= mixed_min_abs and abs(proxy) >= mixed_min_abs and us2y * proxy < 0:
        return "MIXED"
    return "NEUTRAL"


def evaluation_status(
    *,
    signal_as_of: datetime,
    macro_as_of: datetime | None,
    coverage_confidence: float | None,
    config: dict[str, Any],
) -> tuple[str, float | None]:
    if macro_as_of is None:
        return "NO_MACRO_SNAPSHOT", None
    age_seconds = max(0.0, (signal_as_of - macro_as_of).total_seconds())
    max_age = float(config.get("max_macro_snapshot_age_minutes", 30)) * 60.0
    if age_seconds > max_age:
        return "STALE_MACRO_SNAPSHOT", age_seconds
    min_coverage = float(config.get("min_macro_coverage", 0.65))
    if coverage_confidence is None or float(coverage_confidence) < min_coverage:
        return "LOW_MACRO_COVERAGE", age_seconds
    return "READY", age_seconds


def deterministic_eval_id(benchmark_id: str, feature_version: str) -> str:
    material = f"{benchmark_id}|{feature_version}|{EVAL_VERSION}"
    return "macro-eval-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:28]


def fetch_candidates(
    conn: psycopg.Connection,
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    market = str(config.get("market", "US")).upper()
    strategy_version = str(config.get("strategy_version", "R5.1_BASE_HGB"))
    benchmark_names = list(config.get("benchmark_names") or [])
    if not benchmark_names:
        raise ValueError("benchmark_names is empty")
    forward_start = parse_dt(str(config.get("forward_start")))
    if forward_start is None:
        raise ValueError("forward_start is required")
    feature_version = str(config.get("feature_version", "macro-event-feature-v1"))

    rows = conn.execute(
        """
        SELECT
          b.benchmark_id::text AS benchmark_id,
          b.market,
          b.strategy_version,
          b.benchmark_name,
          b.as_of AS signal_as_of,
          b.gross_return AS baseline_gross_return,
          b.net_return AS baseline_net_return,
          b.metadata AS benchmark_metadata,
          m.as_of AS macro_as_of,
          m.run_id AS macro_run_id,
          m.coverage_confidence,
          m.features AS macro_features
        FROM public.strategy_benchmark_ledger b
        LEFT JOIN LATERAL (
          SELECT as_of,run_id,coverage_confidence,features
          FROM public.news_feature_snapshot s
          WHERE s.market='GLOBAL'
            AND s.symbol='GLOBAL'
            AND s.feature_version=%s
            AND s.as_of <= b.as_of
          ORDER BY s.as_of DESC
          LIMIT 1
        ) m ON true
        WHERE b.market=%s
          AND b.strategy_version=%s
          AND b.benchmark_name = ANY(%s)
          AND b.as_of >= %s
        ORDER BY b.as_of,b.benchmark_name
        """,
        (feature_version, market, strategy_version, benchmark_names, forward_start),
    ).fetchall()
    return list(rows)


def sync_evaluations(
    conn: psycopg.Connection,
    config: dict[str, Any],
) -> dict[str, Any]:
    rows = fetch_candidates(conn, config)
    feature_version = str(config.get("feature_version", "macro-event-feature-v1"))
    research = config.get("research_contract") or {}
    counts: dict[str, int] = {
        "seen": 0,
        "upserted": 0,
        "READY": 0,
        "NO_MACRO_SNAPSHOT": 0,
        "STALE_MACRO_SNAPSHOT": 0,
        "LOW_MACRO_COVERAGE": 0,
    }

    for row in rows:
        counts["seen"] += 1
        signal_as_of = parse_dt(row["signal_as_of"])
        macro_as_of = parse_dt(row.get("macro_as_of"))
        if signal_as_of is None:
            continue
        coverage = _float(row.get("coverage_confidence"))
        status, age_seconds = evaluation_status(
            signal_as_of=signal_as_of,
            macro_as_of=macro_as_of,
            coverage_confidence=coverage,
            config=config,
        )
        counts[status] += 1

        features = row.get("macro_features")
        if not isinstance(features, dict):
            features = {}
        regime = classify_free_macro_regime(features, config) if macro_as_of else "UNKNOWN"

        metadata = {
            "evaluation_version": EVAL_VERSION,
            "feature_version": feature_version,
            "observation_only": bool(research.get("observation_only", True)),
            "changes_r51": False,
            "changes_trade_execution": False,
            "promotion_allowed": False,
            "benchmark_metadata": row.get("benchmark_metadata") or {},
        }

        conn.execute(
            """
            INSERT INTO public.macro_shadow_evaluation_v1(
              evaluation_id,benchmark_id,market,strategy_version,benchmark_name,
              signal_as_of,macro_as_of,macro_run_id,macro_age_seconds,
              coverage_confidence,evaluation_status,free_macro_regime,
              us2y_change_bps_1d,policy_proxy_change_bps_1d,
              policy_proxy_spread_bps,official_macro_decay,broad_macro_decay,
              macro_event_free_reaction_score,macro_event_free_reaction_direction,
              macro_event_free_reaction_ready,
              baseline_gross_return,baseline_net_return,macro_features,metadata,updated_at
            ) VALUES(
              %s,%s::uuid,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
              %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,now()
            )
            ON CONFLICT(benchmark_id) DO UPDATE SET
              macro_as_of=excluded.macro_as_of,
              macro_run_id=excluded.macro_run_id,
              macro_age_seconds=excluded.macro_age_seconds,
              coverage_confidence=excluded.coverage_confidence,
              evaluation_status=excluded.evaluation_status,
              free_macro_regime=excluded.free_macro_regime,
              us2y_change_bps_1d=excluded.us2y_change_bps_1d,
              policy_proxy_change_bps_1d=excluded.policy_proxy_change_bps_1d,
              policy_proxy_spread_bps=excluded.policy_proxy_spread_bps,
              official_macro_decay=excluded.official_macro_decay,
              broad_macro_decay=excluded.broad_macro_decay,
              macro_event_free_reaction_score=excluded.macro_event_free_reaction_score,
              macro_event_free_reaction_direction=excluded.macro_event_free_reaction_direction,
              macro_event_free_reaction_ready=excluded.macro_event_free_reaction_ready,
              baseline_gross_return=excluded.baseline_gross_return,
              baseline_net_return=excluded.baseline_net_return,
              macro_features=excluded.macro_features,
              metadata=excluded.metadata,
              updated_at=now()
            """,
            (
                deterministic_eval_id(str(row["benchmark_id"]), feature_version),
                str(row["benchmark_id"]),
                row["market"],
                row["strategy_version"],
                row["benchmark_name"],
                signal_as_of,
                macro_as_of,
                row.get("macro_run_id"),
                age_seconds,
                coverage,
                status,
                regime,
                _float(features.get("us2y_change_bps_1d")),
                _float(features.get("policy_proxy_change_bps_1d")),
                _float(features.get("policy_proxy_spread_bps")),
                _float(features.get("official_macro_decay")),
                _float(features.get("broad_macro_decay")),
                _float(features.get("macro_event_free_reaction_score")),
                (
                    str(features.get("macro_event_free_reaction_direction"))
                    if features.get("macro_event_free_reaction_direction") is not None
                    else None
                ),
                (
                    bool(features.get("macro_event_free_reaction_ready"))
                    if features.get("macro_event_free_reaction_ready") is not None
                    else None
                ),
                float(row["baseline_gross_return"]),
                float(row["baseline_net_return"]),
                json.dumps(features, ensure_ascii=False, sort_keys=True),
                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
            ),
        )
        counts["upserted"] += 1

    conn.commit()
    return counts


def status(conn: psycopg.Connection, config: dict[str, Any]) -> dict[str, Any]:
    market = str(config.get("market", "US")).upper()
    strategy_version = str(config.get("strategy_version", "R5.1_BASE_HGB"))
    benchmark_names = list(config.get("benchmark_names") or [])
    minimum_ready = int(config.get("minimum_ready_observations_for_rule_research", 60))

    readiness = conn.execute(
        """
        SELECT *
        FROM public.v_macro_shadow_eval_readiness_v1
        WHERE market=%s
          AND strategy_version=%s
          AND benchmark_name = ANY(%s)
        ORDER BY benchmark_name
        """,
        (market, strategy_version, benchmark_names),
    ).fetchall()
    summary = conn.execute(
        """
        SELECT *
        FROM public.v_macro_shadow_eval_summary_v1
        WHERE market=%s
          AND strategy_version=%s
          AND benchmark_name = ANY(%s)
        ORDER BY benchmark_name,free_macro_regime
        """,
        (market, strategy_version, benchmark_names),
    ).fetchall()

    free_reaction_summary = conn.execute(
        """
        SELECT *
        FROM public.v_macro_shadow_eval_free_reaction_v1
        WHERE market=%s
          AND strategy_version=%s
          AND benchmark_name = ANY(%s)
        ORDER BY benchmark_name,macro_event_free_reaction_direction
        """,
        (market, strategy_version, benchmark_names),
    ).fetchall()

    ready_counts = {
        str(row["benchmark_name"]): int(row["ready_rows"])
        for row in readiness
    }
    rule_research_ready = bool(ready_counts) and all(
        ready_counts.get(name, 0) >= minimum_ready for name in benchmark_names
    )
    return {
        "status": "READY",
        "evaluation_version": EVAL_VERSION,
        "market": market,
        "strategy_version": strategy_version,
        "forward_start": config.get("forward_start"),
        "minimum_ready_observations_for_rule_research": minimum_ready,
        "rule_research_ready": rule_research_ready,
        "promotion_allowed": False,
        "changes_r51": False,
        "changes_trade_execution": False,
        "readiness": list(readiness),
        "summary": list(summary),
        "free_reaction_summary": list(free_reaction_summary),
    }


def selftest() -> None:
    cfg = {
        "max_macro_snapshot_age_minutes": 30,
        "min_macro_coverage": 0.65,
        "regime_thresholds_bps": {
            "tightening": 10,
            "easing": -10,
            "mixed_min_abs": 5,
        },
    }
    assert classify_free_macro_regime(
        {"us2y_change_bps_1d": 12, "policy_proxy_change_bps_1d": 15}, cfg
    ) == "TIGHTENING"
    assert classify_free_macro_regime(
        {"us2y_change_bps_1d": -12, "policy_proxy_change_bps_1d": -15}, cfg
    ) == "EASING"
    assert classify_free_macro_regime(
        {"us2y_change_bps_1d": 8, "policy_proxy_change_bps_1d": -7}, cfg
    ) == "MIXED"
    assert classify_free_macro_regime(
        {"us2y_change_bps_1d": -7, "policy_proxy_change_bps_1d": -4}, cfg
    ) == "NEUTRAL"
    assert classify_free_macro_regime(
        {"us2y_change_bps_1d": None, "policy_proxy_change_bps_1d": -4}, cfg
    ) == "UNKNOWN"

    signal = datetime(2026, 9, 21, 14, 30, tzinfo=UTC)
    macro = datetime(2026, 9, 21, 14, 15, tzinfo=UTC)
    s, age = evaluation_status(
        signal_as_of=signal,
        macro_as_of=macro,
        coverage_confidence=0.65,
        config=cfg,
    )
    assert s == "READY" and age == 900.0
    s, _ = evaluation_status(
        signal_as_of=signal,
        macro_as_of=datetime(2026, 9, 21, 13, 0, tzinfo=UTC),
        coverage_confidence=0.65,
        config=cfg,
    )
    assert s == "STALE_MACRO_SNAPSHOT"
    s, _ = evaluation_status(
        signal_as_of=signal,
        macro_as_of=macro,
        coverage_confidence=0.64,
        config=cfg,
    )
    assert s == "LOW_MACRO_COVERAGE"
    print("MACRO_SHADOW_EVAL_V1_SELFTEST_OK")


def main() -> int:
    load_env()
    parser = argparse.ArgumentParser(description="Kalman Macro Shadow Evaluation V1")
    parser.add_argument("command", choices=["sync", "status", "selftest"])
    parser.add_argument(
        "--config",
        default=os.environ.get(
            "KALMAN_MACRO_SHADOW_EVAL_CONFIG",
            "/opt/kalman/app/config/macro-shadow-eval-v1.json",
        ),
    )
    args = parser.parse_args()

    if args.command == "selftest":
        selftest()
        return 0

    config = load_config(Path(args.config))
    db_url = os.environ.get("DATABASE_URL_WRITER") or os.environ.get("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL_WRITER/DATABASE_URL missing")

    if args.command == "sync":
        if not env_bool("KALMAN_MACRO_SHADOW_EVAL_ENABLED", False):
            print("[MACRO_EVAL][SYNC] disabled by KALMAN_MACRO_SHADOW_EVAL_ENABLED")
            return 0
        with psycopg.connect(db_url, connect_timeout=15, row_factory=dict_row) as conn:
            result = sync_evaluations(conn, config)
        print("[MACRO_EVAL][SYNC]", json.dumps(result, sort_keys=True))
        return 0

    with psycopg.connect(db_url, connect_timeout=15, row_factory=dict_row) as conn:
        result = status(conn, config)
    print("[MACRO_EVAL][STATUS]", json.dumps(result, default=str, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
