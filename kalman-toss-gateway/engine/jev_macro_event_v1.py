from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.jev_shadow_decision_v1 import env_bool, load_env, load_gateway_key

UTC = timezone.utc
EVAL_VERSION = "jev-macro-event-v1.3.1"
DEFAULT_MODEL = "typesafe-ai/jev"
DEFAULT_ENDPOINT = "https://ai-gateway.vercel.sh/v1/evaluate"
HOLDING_HORIZON_BARS = 4
OFFICIAL_EVENT_SOURCES = (
    "fed_monetary",
    "bls_cpi",
    "bls_employment",
    "bls_jolts",
    "bea_releases",
)

MACRO_KEYS = (
    "schema_version",
    "macro_event_family",
    "macro_event_signal_ready",
    "macro_event_signal_quality",
    "macro_event_signal_blockers",
    "macro_event_shadow_score",
    "macro_event_shadow_direction",
    "macro_event_shadow_components",
    "macro_event_free_reaction_ready",
    "macro_event_free_reaction_score",
    "macro_event_free_reaction_direction",
    "macro_event_free_reaction_quality",
    "macro_event_free_reaction_blockers",
    "us_priority_surprise_index",
    "us_priority_surprise_latest_indicator",
    "us_priority_surprise_contributor_count",
    "latest_surprise_indicator",
    "latest_surprise_actual",
    "latest_surprise_consensus",
    "us2y_change_bps_1d",
    "us2y_event_reaction_bps",
    "us2y_event_reaction_z",
    "us2y_reaction_quality",
    "fed_policy_repricing_bps",
    "fed_policy_repricing_quality",
    "fed_policy_repricing_horizon",
    "policy_proxy_change_bps_1d",
    "policy_proxy_spread_bps",
    "policy_pressure_surprise_latest",
    "us_policy_pressure_surprise_latest",
    "us_policy_pressure_surprise_decay_ema",
    "us_target_macro_event_score",
    "official_macro_count_6h",
    "official_macro_count_24h",
    "official_macro_count_72h",
    "consensus_surprise_count_72h",
    "us_consensus_surprise_count_72h",
    "release_observation_count_72h",
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_safe_value(x) for x in value[:40]]
    if isinstance(value, dict):
        return {str(k): _safe_value(v) for k, v in list(value.items())[:60]}
    return str(value)


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def official_event_family(source: str | None, title: str | None) -> str:
    source = str(source or "")
    text = str(title or "").lower()
    if source == "fed_monetary":
        return "FOMC"
    if source == "bls_cpi":
        return "CPI"
    if source == "bls_employment":
        return "NFP"
    if source == "bls_jolts":
        return "JOLTS"
    if source == "bea_releases":
        if "personal income and outlays" in text or "pce" in text:
            return "PCE"
        if "gdp" in text or "gross domestic product" in text:
            return "GDP"
        return "BEA_OTHER"
    return "OTHER"


def macro_is_informative(features: dict[str, Any]) -> tuple[bool, list[str]]:
    signals = {
        "macro_event_signal_ready": _bool(features.get("macro_event_signal_ready")),
        "macro_event_free_reaction_ready": _bool(features.get("macro_event_free_reaction_ready")),
        "us_priority_surprise_index": _float(features.get("us_priority_surprise_index")) is not None,
        "us2y_event_reaction_bps": _float(features.get("us2y_event_reaction_bps")) is not None,
        "fed_policy_repricing_bps": _float(features.get("fed_policy_repricing_bps")) is not None,
        "us_target_macro_event_score": _float(features.get("us_target_macro_event_score")) is not None,
    }
    active = [k for k, ready in signals.items() if ready]
    return bool(active), active


def build_state(
    macro: dict[str, Any],
    official_event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    features = macro.get("features")
    if not isinstance(features, dict):
        features = {}
    ready, readiness_sources = macro_is_informative(features)

    clean = {
        key: _safe_value(features.get(key))
        for key in MACRO_KEYS
        if features.get(key) is not None
    }

    official_clean: dict[str, Any] | None = None
    if isinstance(official_event, dict) and official_event.get("title"):
        family = official_event_family(
            str(official_event.get("source") or ""),
            str(official_event.get("title") or ""),
        )
        age_minutes = _float(official_event.get("age_minutes"))
        official_clean = {
            "source": str(official_event.get("source") or ""),
            "family": family,
            "headline": str(official_event.get("title") or ""),
            "age_minutes": age_minutes,
            "availability_semantics": "MAX_PROVIDER_AVAILABLE_FIRST_SEEN",
        }
        if family != "OTHER":
            ready = True
            readiness_sources = list(readiness_sources) + ["official_macro_event_first_seen_safe"]

    return {
        "contract": {
            "strategy_context": "R5.1_BASE_HGB has already produced a long Top1 candidate",
            "decision_role": "macro_event_incremental_challenger",
            "candidate_identity_blinded": True,
            "signal_timestamp_blinded": True,
            "baseline_model_features_excluded": True,
            "execution_policy_flags_excluded": True,
            "future_outcome_hidden": True,
            "live_execution_authority": False,
            "holding_horizon_bars": HOLDING_HORIZON_BARS,
            "instruction": (
                "Judge only the incremental macro/event evidence. Do not re-score the stock, "
                "do not infer asset-specific facts, and do not infer hidden signal timestamps. "
                "The official headline is usable only because it was observed by the system before "
                "the baseline signal. If surprise/reaction evidence is incomplete, prefer NEUTRAL."
            ),
        },
        "macro": {
            "coverage_confidence": _float(macro.get("coverage_confidence")),
            "event_informative": ready,
            "readiness_sources": readiness_sources,
            "official_event": official_clean,
            **clean,
        },
    }


def evaluation_questions() -> dict[str, Any]:
    return {
        "macro_entry_support": {
            "type": "choice",
            "instructions": (
                "An independent baseline model already has a long Top1 candidate. Using ONLY the supplied "
                "macro/event state, classify whether macro conditions add an incremental reason to SUPPORT, "
                "remain NEUTRAL, or VETO that long exposure over the next four hourly bars. "
                "Use NEUTRAL when the event evidence is weak, mixed, stale, or incomplete."
            ),
            "criteria": {
                "SUPPORT": "Macro/event evidence materially favors near-term US equity long exposure.",
                "NEUTRAL": "Macro/event evidence is immaterial, balanced, weak, or insufficient.",
                "VETO": "Macro/event evidence materially argues against near-term US equity long exposure.",
            },
        },
        "macro_regime": {
            "type": "choice",
            "instructions": "Classify only the supplied macro/event regime.",
            "criteria": {
                "EASING_SUPPORT": "Rates/policy repricing is materially supportive for equities.",
                "HAWKISH_TIGHTENING": "Rates/policy repricing is materially restrictive for equities.",
                "GROWTH_RISK": "Growth/labor activity evidence points to material downside risk.",
                "INFLATION_RISK": "Inflation evidence points to material tightening or valuation risk.",
                "RISK_ON": "Macro evidence is broadly supportive without a dominant easing shock.",
                "MIXED": "Material macro signals conflict.",
                "INSUFFICIENT": "Available macro/event evidence is not sufficient for a regime call.",
            },
        },
        "macro_materiality": {
            "type": "score",
            "instructions": "Rate how material the supplied macro/event information is for a four-hour US equity decision.",
            "criteria": [
                "immaterial",
                "low",
                "moderate",
                "high",
                "very high",
            ],
        },
    }


def call_gateway(
    *,
    state: dict[str, Any],
    api_key: str,
    model: str,
    endpoint: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    payload = {"model": model, "state": state, "questions": evaluation_questions()}
    request = urllib.request.Request(
        endpoint,
        data=_json(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"JEV HTTP {exc.code}: {body[:1200]}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("JEV response is not a JSON object")
    return result


def _probabilities(answer: Any) -> dict[str, float]:
    if not isinstance(answer, dict):
        return {}
    for key in ("probabilities", "scores", "distribution", "probability"):
        raw = answer.get(key)
        if isinstance(raw, dict):
            out: dict[str, float] = {}
            for k, v in raw.items():
                fv = _float(v)
                if fv is not None:
                    out[str(k)] = fv
            return out
    return {}


def _choice(answer: Any) -> str | None:
    if isinstance(answer, str):
        return answer
    if not isinstance(answer, dict):
        return None
    for key in ("choice", "value", "answer", "label"):
        value = answer.get(key)
        if isinstance(value, str):
            return value
    probs = _probabilities(answer)
    return max(probs, key=probs.get) if probs else None


def _score(answer: Any) -> float | None:
    if isinstance(answer, (int, float)):
        return float(answer)
    if not isinstance(answer, dict):
        return None
    for key in ("score", "value", "mean"):
        value = _float(answer.get(key))
        if value is not None:
            return value
    return None


def normalize(result: dict[str, Any]) -> dict[str, Any]:
    answers = result.get("answers")
    if not isinstance(answers, dict):
        answers = {}
    support = answers.get("macro_entry_support")
    regime = answers.get("macro_regime")
    materiality = answers.get("macro_materiality")
    return {
        "model": str(result.get("model") or DEFAULT_MODEL),
        "entry_support": _choice(support),
        "entry_support_probabilities": _probabilities(support),
        "regime": _choice(regime),
        "regime_probabilities": _probabilities(regime),
        "conviction_score": _score(materiality),
        "conviction_probabilities": _probabilities(materiality),
        "usage": result.get("usage") if isinstance(result.get("usage"), dict) else {},
        "answers": answers,
    }


def decision_id(run_id: str, symbol: str, strategy_version: str) -> str:
    material = f"{run_id}|{symbol}|{strategy_version}|{EVAL_VERSION}"
    return "jev-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:28]


def fetch_candidates(conn: Any, config: dict[str, Any]) -> list[dict[str, Any]]:
    market = str(config.get("market", "US")).upper()
    strategy_version = str(config.get("strategy_version", "R5.1_BASE_HGB"))
    feature_version = str(config.get("macro_feature_version", "macro-event-feature-v1"))
    start_at = str(config.get("start_at_utc") or "2026-10-07T13:30:00Z")
    limit = int(config.get("max_candidates_per_run", 24))
    official_max_age_hours = float(config.get("official_event_max_age_hours", 6.0))
    official_sources = list(config.get("official_event_sources") or OFFICIAL_EVENT_SOURCES)

    return list(
        conn.execute(
            """
            SELECT
              s.run_id::text AS run_id,
              s.market,
              s.symbol,
              s.as_of,
              s.strategy_version,
              m.as_of AS macro_as_of,
              m.coverage_confidence,
              m.features AS macro_features,
              o.source AS official_source,
              o.title AS official_title,
              o.safe_available_at AS official_available_at
            FROM public.strategy_signal s
            LEFT JOIN LATERAL (
              SELECT as_of,coverage_confidence,features
              FROM public.news_feature_snapshot n
              WHERE n.market='GLOBAL'
                AND n.symbol='GLOBAL'
                AND n.feature_version=%s
                AND n.as_of <= s.as_of
              ORDER BY n.as_of DESC
              LIMIT 1
            ) m ON true
            LEFT JOIN LATERAL (
              SELECT
                a.source,
                a.title,
                GREATEST(a.available_at,a.first_seen_at) AS safe_available_at
              FROM public.news_article a
              JOIN public.news_event e ON e.article_id=a.article_id
              WHERE e.event_type='MACRO'
                AND a.source = ANY(%s)
                AND GREATEST(a.available_at,a.first_seen_at) <= s.as_of
                AND GREATEST(a.available_at,a.first_seen_at)
                    >= s.as_of - (%s * interval '1 hour')
              ORDER BY GREATEST(a.available_at,a.first_seen_at) DESC
              LIMIT 1
            ) o ON true
            LEFT JOIN public.jev_shadow_decision_v1 j
              ON j.run_id=s.run_id::text
             AND j.symbol=s.symbol
             AND j.strategy_version=s.strategy_version
             AND j.evaluation_version=%s
            WHERE s.market=%s
              AND s.strategy_version=%s
              AND s.as_of >= %s::timestamptz
              AND s.signal='SHADOW'
              AND lower(COALESCE(s.payload->>'allow_trade_shadow','false'))='true'
              AND j.decision_id IS NULL
            ORDER BY s.as_of,s.symbol
            LIMIT %s
            """,
            (
                feature_version,
                official_sources,
                official_max_age_hours,
                EVAL_VERSION,
                market,
                strategy_version,
                start_at,
                limit,
            ),
        ).fetchall()
    )


def reusable_result(conn: Any, state: dict[str, Any]) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT entry_support,entry_support_probabilities,regime,regime_probabilities,
               conviction_score,conviction_probabilities,answer_payload,usage,gateway_model
        FROM public.jev_shadow_decision_v1
        WHERE evaluation_version=%s
          AND evaluation_status='READY'
          AND state=%s::jsonb
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (EVAL_VERSION, _json(state)),
    ).fetchone()
    return dict(row) if row else None


def store(
    conn: Any,
    *,
    signal: dict[str, Any],
    macro: dict[str, Any],
    state: dict[str, Any],
    status: str,
    normalized: dict[str, Any] | None = None,
    raw: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    normalized = normalized or {}
    conn.execute(
        """
        INSERT INTO public.jev_shadow_decision_v1(
          decision_id,run_id,market,symbol,strategy_version,signal_as_of,
          gateway_model,evaluation_version,evaluation_status,
          entry_support,entry_support_probabilities,positive_ev_probability,
          regime,regime_probabilities,conviction_score,conviction_probabilities,
          addon_support_probability,state,answer_payload,usage,
          macro_as_of,macro_coverage_confidence,error_message,
          shadow_only,can_veto_live,can_size_live,updated_at
        ) VALUES(
          %s,%s,%s,%s,%s,%s,
          %s,%s,%s,
          %s,%s::jsonb,NULL,
          %s,%s::jsonb,%s,%s::jsonb,
          NULL,%s::jsonb,%s::jsonb,%s::jsonb,
          %s,%s,%s,
          true,false,false,now()
        )
        ON CONFLICT(decision_id) DO UPDATE SET
          evaluation_status=excluded.evaluation_status,
          entry_support=excluded.entry_support,
          entry_support_probabilities=excluded.entry_support_probabilities,
          regime=excluded.regime,
          regime_probabilities=excluded.regime_probabilities,
          conviction_score=excluded.conviction_score,
          conviction_probabilities=excluded.conviction_probabilities,
          state=excluded.state,
          answer_payload=excluded.answer_payload,
          usage=excluded.usage,
          macro_as_of=excluded.macro_as_of,
          macro_coverage_confidence=excluded.macro_coverage_confidence,
          error_message=excluded.error_message,
          shadow_only=true,can_veto_live=false,can_size_live=false,updated_at=now()
        """,
        (
            decision_id(str(signal["run_id"]), str(signal["symbol"]), str(signal["strategy_version"])),
            str(signal["run_id"]),
            str(signal.get("market") or "US"),
            str(signal["symbol"]),
            str(signal["strategy_version"]),
            signal["as_of"],
            str(normalized.get("model") or DEFAULT_MODEL),
            EVAL_VERSION,
            status,
            normalized.get("entry_support"),
            _json(normalized.get("entry_support_probabilities") or {}),
            normalized.get("regime"),
            _json(normalized.get("regime_probabilities") or {}),
            normalized.get("conviction_score"),
            _json(normalized.get("conviction_probabilities") or {}),
            _json(state),
            _json(raw or {}),
            _json(normalized.get("usage") or {}),
            macro.get("as_of"),
            _float(macro.get("coverage_confidence")),
            error,
        ),
    )


def sync(config: dict[str, Any]) -> dict[str, Any]:
    if not env_bool("JEV_SHADOW_ENABLED", True):
        return {"status": "DISABLED", "evaluation_version": EVAL_VERSION}
    if not env_bool("JEV_SHADOW_ONLY", True):
        raise RuntimeError("JEV_SHADOW_ONLY must remain true")
    if env_bool("JEV_CAN_VETO_LIVE", False) or env_bool("JEV_CAN_SIZE_LIVE", False):
        raise RuntimeError("Live JEV authority is forbidden")

    import psycopg
    from psycopg.rows import dict_row

    db_url = os.environ.get("DATABASE_URL_WRITER") or os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL_WRITER/DATABASE_URL missing")

    model = str(config.get("model") or DEFAULT_MODEL)
    endpoint = str(config.get("endpoint") or DEFAULT_ENDPOINT)
    timeout = float(config.get("timeout_seconds", 20))
    api_key = load_gateway_key(config)
    counts = {"seen": 0, "ready": 0, "skipped_no_event": 0, "reused": 0, "api_error": 0}

    with psycopg.connect(db_url, row_factory=dict_row, connect_timeout=15) as conn:
        for row in fetch_candidates(conn, config):
            counts["seen"] += 1
            signal = dict(row)
            macro = {
                "as_of": row.get("macro_as_of"),
                "coverage_confidence": row.get("coverage_confidence"),
                "features": row.get("macro_features") or {},
            }
            official_event = None
            official_available = row.get("official_available_at")
            signal_as_of = row.get("as_of")
            if row.get("official_title") and isinstance(official_available, datetime) and isinstance(signal_as_of, datetime):
                age_minutes = max(
                    0.0,
                    (signal_as_of.astimezone(UTC) - official_available.astimezone(UTC)).total_seconds() / 60.0,
                )
                official_event = {
                    "source": row.get("official_source"),
                    "title": row.get("official_title"),
                    "age_minutes": age_minutes,
                }
            state = build_state(macro, official_event)
            if not state["macro"]["event_informative"]:
                store(
                    conn,
                    signal=signal,
                    macro=macro,
                    state=state,
                    status="SKIPPED_NO_EVENT",
                )
                conn.commit()
                counts["skipped_no_event"] += 1
                continue

            prior = reusable_result(conn, state)
            if prior is not None:
                normalized = {
                    "model": prior.get("gateway_model") or model,
                    "entry_support": prior.get("entry_support"),
                    "entry_support_probabilities": prior.get("entry_support_probabilities") or {},
                    "regime": prior.get("regime"),
                    "regime_probabilities": prior.get("regime_probabilities") or {},
                    "conviction_score": prior.get("conviction_score"),
                    "conviction_probabilities": prior.get("conviction_probabilities") or {},
                    "usage": {},
                }
                store(
                    conn,
                    signal=signal,
                    macro=macro,
                    state=state,
                    status="READY_REUSED",
                    normalized=normalized,
                    raw=prior.get("answer_payload") or {},
                )
                conn.commit()
                counts["reused"] += 1
                continue

            try:
                raw = call_gateway(
                    state=state,
                    api_key=api_key,
                    model=model,
                    endpoint=endpoint,
                    timeout_seconds=timeout,
                )
                normalized = normalize(raw)
                store(
                    conn,
                    signal=signal,
                    macro=macro,
                    state=state,
                    status="READY",
                    normalized=normalized,
                    raw=raw,
                )
                conn.commit()
                counts["ready"] += 1
            except Exception as exc:
                store(
                    conn,
                    signal=signal,
                    macro=macro,
                    state=state,
                    status="API_ERROR",
                    normalized={"model": model},
                    error=str(exc)[:2000],
                )
                conn.commit()
                counts["api_error"] += 1

    return {
        "status": "READY",
        "evaluation_version": EVAL_VERSION,
        "model": model,
        **counts,
        "shadow_only": True,
        "live_authority": False,
    }


def status(config: dict[str, Any]) -> dict[str, Any]:
    import psycopg
    from psycopg.rows import dict_row

    db_url = os.environ.get("DATABASE_URL_WRITER") or os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL_WRITER/DATABASE_URL missing")
    with psycopg.connect(db_url, row_factory=dict_row, connect_timeout=15) as conn:
        rows = conn.execute(
            """
            SELECT evaluation_status,count(*) AS n,max(signal_as_of) AS latest_signal_as_of,
                   max(updated_at) AS latest_updated_at
            FROM public.jev_shadow_decision_v1
            WHERE evaluation_version=%s
            GROUP BY evaluation_status
            ORDER BY evaluation_status
            """,
            (EVAL_VERSION,),
        ).fetchall()
    return {
        "status": "READY",
        "evaluation_version": EVAL_VERSION,
        "rows_by_status": [dict(x) for x in rows],
        "shadow_only": True,
        "live_authority": False,
    }


def probe(config: dict[str, Any]) -> dict[str, Any]:
    macro = {
        "coverage_confidence": 0.95,
        "features": {
            "schema_version": "macro-event-feature-v1.synthetic-probe",
            "macro_event_family": "CPI",
            "macro_event_signal_ready": True,
            "macro_event_signal_quality": "SYNTHETIC_PROBE",
            "us_priority_surprise_index": 1.4,
            "latest_surprise_indicator": "CORE_CPI",
            "latest_surprise_actual": 0.4,
            "latest_surprise_consensus": 0.2,
            "us2y_event_reaction_bps": 12.0,
            "us2y_event_reaction_z": 1.8,
            "fed_policy_repricing_bps": 9.0,
            "fed_policy_repricing_quality": "SYNTHETIC_PROBE",
        },
    }
    state = build_state(macro)
    raw = call_gateway(
        state=state,
        api_key=load_gateway_key(config),
        model=str(config.get("model") or DEFAULT_MODEL),
        endpoint=str(config.get("endpoint") or DEFAULT_ENDPOINT),
        timeout_seconds=float(config.get("timeout_seconds", 20)),
    )
    normalized = normalize(raw)
    return {
        "status": "READY",
        "evaluation_version": EVAL_VERSION,
        "entry_support": normalized["entry_support"],
        "entry_support_probabilities": normalized["entry_support_probabilities"],
        "regime": normalized["regime"],
        "conviction_score": normalized["conviction_score"],
        "usage": normalized["usage"],
        "state_contract": state["contract"],
    }


def selftest() -> None:
    blocked = build_state({
        "coverage_confidence": 0.65,
        "features": {
            "macro_event_family": "OTHER",
            "macro_event_signal_ready": False,
            "macro_event_free_reaction_ready": False,
            "macro_event_signal_blockers": ["NO_US_EVENT_ANCHOR"],
            "us2y_change_bps_1d": 1.0,
        },
    })
    assert blocked["macro"]["event_informative"] is False

    ready = build_state({
        "coverage_confidence": 0.9,
        "features": {
            "macro_event_family": "CPI",
            "macro_event_signal_ready": True,
            "us_priority_surprise_index": 1.2,
            "us2y_event_reaction_bps": 10.0,
        },
    })
    encoded = _json(ready)
    assert ready["macro"]["event_informative"] is True
    assert "r5_score" not in encoded
    assert "position_weight" not in encoded
    assert "risk_gate" not in encoded
    assert "symbol" not in encoded
    assert "as_of" not in encoded
    assert ready["contract"]["live_execution_authority"] is False
    print("JEV_MACRO_EVENT_V1_3_SELFTEST_OK")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kalman JEV Macro/Event Challenger V1.3")
    parser.add_argument(
        "--config",
        default=os.environ.get(
            "KALMAN_JEV_MACRO_CONFIG",
            "/home/taehoon/.local/share/kalman-jev-shadow/config/jev-macro-event-v1.3.json",
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("selftest", "probe", "sync", "status"):
        sub.add_parser(name)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_env()
    if args.command == "selftest":
        selftest()
        return 0
    config = load_config(Path(args.config).expanduser())
    if args.command == "probe":
        print(json.dumps(probe(config), ensure_ascii=False, indent=2, default=str))
    elif args.command == "sync":
        print(json.dumps(sync(config), ensure_ascii=False, indent=2, default=str))
    elif args.command == "status":
        print(json.dumps(status(config), ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
