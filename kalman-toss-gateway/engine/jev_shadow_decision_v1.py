from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


UTC = timezone.utc
EVAL_VERSION = "jev-shadow-decision-v1"
DEFAULT_MODEL = "typesafe-ai/jev"
DEFAULT_ENDPOINT = "https://ai-gateway.vercel.sh/v1/evaluate"
DEFAULT_KEY_FILE = "/home/taehoon/.config/kalman/secure/jev_gateway_key_create.out"


def load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"), override=True)


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _scalar(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return None


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def load_gateway_key(config: dict[str, Any] | None = None) -> str:
    direct = os.environ.get("AI_GATEWAY_API_KEY", "").strip()
    if direct:
        return direct

    config = config or {}
    key_path = Path(
        os.environ.get("JEV_GATEWAY_KEY_FILE")
        or str(config.get("gateway_key_file") or DEFAULT_KEY_FILE)
    ).expanduser()
    text = key_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        candidate = line.strip()
        if re.fullmatch(r"vck_[A-Za-z0-9_-]+", candidate):
            return candidate
    raise RuntimeError(f"AI Gateway key not found in {key_path}")


SIGNAL_PAYLOAD_KEYS = (
    "probability_up",
    "probability_threshold",
    "score",
    "r5_score",
    "rank",
    "r5_rank",
    "top_rank",
    "top1_top2_gap",
    "position_weight",
    "raw_shadow_direction",
    "shadow_direction",
    "shadow_entry_this_signal",
    "model_quality",
    "selected_feature_count",
    "missing_feature_count",
    "missing_feature_ratio",
    "max_missing_feature_ratio",
    "data_quality",
    "horizon_observations",
    "is_forward_shadow",
)

MACRO_FEATURE_KEYS = (
    "us2y_change_bps_1d",
    "policy_proxy_change_bps_1d",
    "policy_proxy_spread_bps",
    "fed_policy_repricing_bps",
    "official_macro_decay",
    "broad_macro_decay",
    "macro_event_shadow_score",
    "macro_event_shadow_direction",
    "macro_event_free_reaction_score",
    "macro_event_free_reaction_direction",
    "macro_event_free_reaction_ready",
    "us_target_macro_event_score",
    "us_priority_surprise_index",
)


def build_state(
    signal: dict[str, Any],
    macro: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = signal.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    macro = macro or {}
    macro_features = macro.get("features")
    if not isinstance(macro_features, dict):
        macro_features = {}

    signal_features = {
        key: value
        for key in SIGNAL_PAYLOAD_KEYS
        if (value := _scalar(payload.get(key))) is not None
    }
    probability = _float(signal_features.get("probability_up"))
    threshold = _float(signal_features.get("probability_threshold"))
    if probability is not None and threshold is not None:
        signal_features["probability_margin"] = round(probability - threshold, 8)

    macro_features_safe = {
        key: value
        for key in MACRO_FEATURE_KEYS
        if (value := _scalar(macro_features.get(key))) is not None
    }

    return {
        "contract": {
            "strategy": str(signal.get("strategy_version") or "R5.1_BASE_HGB"),
            "market": str(signal.get("market") or "US"),
            "decision_role": "research_shadow_adjudicator",
            "candidate_identity_blinded": True,
            "absolute_time_blinded": True,
            "live_execution_authority": False,
            "instruction": (
                "Use only the supplied state. Do not infer asset-specific facts, news, "
                "or future outcomes from outside knowledge."
            ),
        },
        "signal": {
            "signal": str(signal.get("signal") or ""),
            "risk_gate": str(signal.get("risk_gate") or ""),
            "position_state": str(signal.get("position_state") or ""),
            "entry_allowed": bool(signal.get("entry_allowed")) if signal.get("entry_allowed") is not None else None,
            **signal_features,
        },
        "macro": {
            "coverage_confidence": _float(macro.get("coverage_confidence")),
            **macro_features_safe,
        },
    }


def evaluation_questions() -> dict[str, Any]:
    return {
        "entry_support": {
            "type": "choice",
            "instructions": (
                "Using only the supplied state, classify support for a long entry over "
                "the strategy's existing short holding horizon after ordinary trading costs."
            ),
            "criteria": {
                "SUPPORT": "The supplied evidence materially supports the long entry.",
                "NEUTRAL": "The supplied evidence is mixed, weak, or insufficient.",
                "VETO": "The supplied evidence materially argues against the long entry.",
            },
        },
        "positive_ev": {
            "type": "boolean",
            "instructions": (
                "Using only the supplied state, is the candidate more consistent with "
                "positive net expected value than non-positive net expected value?"
            ),
        },
        "regime": {
            "type": "choice",
            "instructions": "Classify the market state using only the supplied inputs.",
            "criteria": {
                "TREND_CONTINUATION": "Signals align with continuation of the current direction.",
                "RANGE_MIXED": "Signals are mixed or consistent with range-bound conditions.",
                "REVERSAL_RISK": "Signals indicate elevated reversal risk.",
                "EVENT_SHOCK": "Macro/event reaction dominates the state.",
                "INSUFFICIENT": "There is not enough supplied evidence for a reliable regime label.",
            },
        },
        "conviction": {
            "type": "score",
            "instructions": "Rate strength of evidence supporting the long entry.",
            "criteria": [
                "very weak",
                "weak",
                "mixed",
                "strong",
                "very strong",
            ],
        },
        "addon_support": {
            "type": "boolean",
            "instructions": (
                "If an existing small position were already open and this candidate remained "
                "the strategy's preferred asset, would the supplied state support one additional "
                "fixed-size tranche? Use only supplied evidence."
            ),
        },
    }


def call_gateway(
    *,
    state: dict[str, Any],
    api_key: str,
    model: str = DEFAULT_MODEL,
    endpoint: str = DEFAULT_ENDPOINT,
    timeout_seconds: float = 20.0,
) -> dict[str, Any]:
    payload = {
        "model": model,
        "state": state,
        "questions": evaluation_questions(),
        "providerOptions": {
            "gateway": {
                "zeroDataRetention": True,
            }
        },
    }
    request = urllib.request.Request(
        endpoint,
        data=_json(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
            result = json.loads(body)
            if not isinstance(result, dict):
                raise RuntimeError("JEV response is not a JSON object")
            return result
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body)
        except json.JSONDecodeError:
            detail = body[:1000]
        raise RuntimeError(f"JEV HTTP {exc.code}: {detail}") from exc


def _probabilities(answer: Any) -> dict[str, float]:
    if not isinstance(answer, dict):
        return {}
    for key in ("probabilities", "scores", "distribution"):
        raw = answer.get(key)
        if isinstance(raw, dict):
            out = {}
            for k, v in raw.items():
                fv = _float(v)
                if fv is not None:
                    out[str(k)] = fv
            return out
    raw = answer.get("probability")
    if isinstance(raw, dict):
        out = {}
        for k, v in raw.items():
            fv = _float(v)
            if fv is not None:
                out[str(k)] = fv
        return out
    return {}


def _choice(answer: Any) -> str | None:
    if not isinstance(answer, dict):
        return str(answer) if isinstance(answer, str) else None
    for key in ("choice", "value", "answer", "label"):
        value = answer.get(key)
        if isinstance(value, str):
            return value
    probs = _probabilities(answer)
    return max(probs, key=probs.get) if probs else None


def _boolean_probability(answer: Any) -> float | None:
    if isinstance(answer, bool):
        return 1.0 if answer else 0.0
    if isinstance(answer, (int, float)):
        return float(answer)
    if not isinstance(answer, dict):
        return None
    raw = answer.get("probability")
    if isinstance(raw, (int, float)):
        return float(raw)
    for key in ("trueProbability", "true_probability", "probabilityTrue"):
        value = _float(answer.get(key))
        if value is not None:
            return value
    probs = _probabilities(answer)
    for key in ("true", "TRUE", "yes", "YES"):
        if key in probs:
            return probs[key]
    value = answer.get("value")
    if isinstance(value, bool):
        confidence = _float(answer.get("confidence"))
        if confidence is None:
            return 1.0 if value else 0.0
        return confidence if value else 1.0 - confidence
    return None


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


def normalize_evaluation(result: dict[str, Any]) -> dict[str, Any]:
    answers = result.get("answers")
    if not isinstance(answers, dict):
        answers = {}
    entry = answers.get("entry_support")
    regime = answers.get("regime")
    conviction = answers.get("conviction")
    return {
        "model": str(result.get("model") or DEFAULT_MODEL),
        "entry_support": _choice(entry),
        "entry_support_probabilities": _probabilities(entry),
        "positive_ev_probability": _boolean_probability(answers.get("positive_ev")),
        "regime": _choice(regime),
        "regime_probabilities": _probabilities(regime),
        "conviction_score": _score(conviction),
        "conviction_probabilities": _probabilities(conviction),
        "addon_support_probability": _boolean_probability(answers.get("addon_support")),
        "usage": result.get("usage") if isinstance(result.get("usage"), dict) else {},
        "answers": answers,
    }


def deterministic_decision_id(
    run_id: str,
    symbol: str,
    strategy_version: str,
) -> str:
    material = f"{run_id}|{symbol}|{strategy_version}|{EVAL_VERSION}"
    return "jev-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:28]


def fetch_candidates(conn: Any, config: dict[str, Any]) -> list[dict[str, Any]]:
    market = str(config.get("market", "US")).upper()
    strategy_version = str(config.get("strategy_version", "R5.1_BASE_HGB"))
    feature_version = str(config.get("macro_feature_version", "macro-event-feature-v1"))
    max_age_hours = int(config.get("max_signal_age_hours", 72))
    limit = int(config.get("max_candidates_per_run", 12))

    rows = conn.execute(
        """
        SELECT
          s.run_id::text AS run_id,
          s.market,
          s.symbol,
          s.as_of,
          s.strategy_version,
          s.signal,
          s.entry_allowed,
          s.risk_gate,
          s.position_state,
          s.payload,
          m.as_of AS macro_as_of,
          m.coverage_confidence,
          m.features AS macro_features
        FROM public.strategy_signal s
        JOIN public.dashboard_snapshot d
          ON d.run_id=s.run_id AND d.market=s.market
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
        LEFT JOIN public.jev_shadow_decision_v1 j
          ON j.run_id=s.run_id::text
         AND j.symbol=s.symbol
         AND j.strategy_version=s.strategy_version
         AND j.evaluation_version=%s
        WHERE s.market=%s
          AND s.strategy_version=%s
          AND s.as_of >= now() - (%s * interval '1 hour')
          AND d.status='READY'
          AND d.stale_after > now()
          AND s.signal='SHADOW'
          AND lower(COALESCE(s.payload->>'allow_trade_shadow','false'))='true'
          AND j.decision_id IS NULL
        ORDER BY s.as_of,s.symbol
        LIMIT %s
        """,
        (
            feature_version,
            EVAL_VERSION,
            market,
            strategy_version,
            max_age_hours,
            limit,
        ),
    ).fetchall()
    return list(rows)


def store_decision(
    conn: Any,
    *,
    signal: dict[str, Any],
    macro: dict[str, Any],
    state: dict[str, Any],
    normalized: dict[str, Any] | None,
    raw_result: dict[str, Any] | None,
    error_message: str | None,
) -> None:
    decision_id = deterministic_decision_id(
        str(signal["run_id"]),
        str(signal["symbol"]),
        str(signal["strategy_version"]),
    )
    normalized = normalized or {}
    status = "READY" if error_message is None else "API_ERROR"

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
          %s,%s::jsonb,%s,
          %s,%s::jsonb,%s,%s::jsonb,
          %s,%s::jsonb,%s::jsonb,%s::jsonb,
          %s,%s,%s,
          true,false,false,now()
        )
        ON CONFLICT(decision_id) DO UPDATE SET
          evaluation_status=excluded.evaluation_status,
          entry_support=excluded.entry_support,
          entry_support_probabilities=excluded.entry_support_probabilities,
          positive_ev_probability=excluded.positive_ev_probability,
          regime=excluded.regime,
          regime_probabilities=excluded.regime_probabilities,
          conviction_score=excluded.conviction_score,
          conviction_probabilities=excluded.conviction_probabilities,
          addon_support_probability=excluded.addon_support_probability,
          state=excluded.state,
          answer_payload=excluded.answer_payload,
          usage=excluded.usage,
          macro_as_of=excluded.macro_as_of,
          macro_coverage_confidence=excluded.macro_coverage_confidence,
          error_message=excluded.error_message,
          shadow_only=true,
          can_veto_live=false,
          can_size_live=false,
          updated_at=now()
        """,
        (
            decision_id,
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
            normalized.get("positive_ev_probability"),
            normalized.get("regime"),
            _json(normalized.get("regime_probabilities") or {}),
            normalized.get("conviction_score"),
            _json(normalized.get("conviction_probabilities") or {}),
            normalized.get("addon_support_probability"),
            _json(state),
            _json(raw_result or {}),
            _json(normalized.get("usage") or {}),
            macro.get("as_of"),
            _float(macro.get("coverage_confidence")),
            error_message,
        ),
    )


def sync(config: dict[str, Any]) -> dict[str, Any]:
    if not env_bool("JEV_SHADOW_ENABLED", True):
        return {"status": "DISABLED", "evaluation_version": EVAL_VERSION}
    if not env_bool("JEV_SHADOW_ONLY", True):
        raise RuntimeError("JEV_SHADOW_ONLY must remain true")
    if env_bool("JEV_CAN_VETO_LIVE", False) or env_bool("JEV_CAN_SIZE_LIVE", False):
        raise RuntimeError("Live JEV authority is forbidden in v1")

    import psycopg
    from psycopg.rows import dict_row

    db_url = os.environ.get("DATABASE_URL_WRITER") or os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL_WRITER/DATABASE_URL missing")

    key = load_gateway_key(config)
    model = str(config.get("model") or DEFAULT_MODEL)
    endpoint = str(config.get("endpoint") or DEFAULT_ENDPOINT)
    timeout = float(config.get("timeout_seconds", 20))
    counts = {"seen": 0, "ready": 0, "api_error": 0}

    with psycopg.connect(db_url, row_factory=dict_row, connect_timeout=15) as conn:
        if conn.execute("SELECT to_regclass('public.jev_shadow_decision_v1')").fetchone()[0] is None:
            raise RuntimeError(
                "public.jev_shadow_decision_v1 is missing; apply research/quant_stack/jev_shadow_decision_v1.sql"
            )
        candidates = fetch_candidates(conn, config)
        for row in candidates:
            counts["seen"] += 1
            signal = dict(row)
            macro = {
                "as_of": row.get("macro_as_of"),
                "coverage_confidence": row.get("coverage_confidence"),
                "features": row.get("macro_features") or {},
            }
            state = build_state(signal, macro)
            try:
                raw = call_gateway(
                    state=state,
                    api_key=key,
                    model=model,
                    endpoint=endpoint,
                    timeout_seconds=timeout,
                )
                normalized = normalize_evaluation(raw)
                store_decision(
                    conn,
                    signal=signal,
                    macro=macro,
                    state=state,
                    normalized=normalized,
                    raw_result=raw,
                    error_message=None,
                )
                conn.commit()
                counts["ready"] += 1
            except Exception as exc:
                store_decision(
                    conn,
                    signal=signal,
                    macro=macro,
                    state=state,
                    normalized={"model": model},
                    raw_result=None,
                    error_message=str(exc)[:2000],
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
        exists = conn.execute(
            "SELECT to_regclass('public.jev_shadow_decision_v1') AS rel"
        ).fetchone()["rel"]
        if exists is None:
            return {"status": "SCHEMA_MISSING", "evaluation_version": EVAL_VERSION}
        row = conn.execute(
            """
            SELECT
              count(*) AS total,
              count(*) FILTER (WHERE evaluation_status='READY') AS ready,
              count(*) FILTER (WHERE evaluation_status='API_ERROR') AS api_error,
              max(signal_as_of) AS latest_signal_as_of,
              max(updated_at) AS latest_updated_at
            FROM public.jev_shadow_decision_v1
            WHERE evaluation_version=%s
            """,
            (EVAL_VERSION,),
        ).fetchone()
        return {
            "status": "READY",
            "evaluation_version": EVAL_VERSION,
            "model": str(config.get("model") or DEFAULT_MODEL),
            **dict(row),
            "shadow_only": True,
            "live_authority": False,
        }


def selftest() -> None:
    signal = {
        "run_id": "demo",
        "market": "US",
        "symbol": "AMD",
        "as_of": "2026-10-07T12:00:00+00:00",
        "strategy_version": "R5.1_BASE_HGB",
        "signal": "SHADOW",
        "entry_allowed": False,
        "risk_gate": "PASS",
        "position_state": "FLAT",
        "payload": {
            "probability_up": 0.82,
            "probability_threshold": 0.61,
            "r5_rank": 1,
            "unknown_secret_field": "must-not-leak",
        },
    }
    state = build_state(signal, {"coverage_confidence": 0.9, "features": {"us2y_change_bps_1d": 4.0}})
    encoded = _json(state)
    assert "AMD" not in encoded
    assert "2026-10-07" not in encoded
    assert "unknown_secret_field" not in encoded
    assert state["signal"]["probability_margin"] == 0.21

    sample = {
        "model": DEFAULT_MODEL,
        "answers": {
            "entry_support": {"choice": "SUPPORT", "probabilities": {"SUPPORT": 0.7, "NEUTRAL": 0.2, "VETO": 0.1}},
            "positive_ev": {"probability": 0.64},
            "regime": {"choice": "TREND_CONTINUATION", "probabilities": {"TREND_CONTINUATION": 0.6}},
            "conviction": {"score": 3.2},
            "addon_support": {"probability": 0.58},
        },
        "usage": {"inputTokens": 100},
    }
    normalized = normalize_evaluation(sample)
    assert normalized["entry_support"] == "SUPPORT"
    assert normalized["positive_ev_probability"] == 0.64
    assert normalized["conviction_score"] == 3.2
    print("JEV_SHADOW_DECISION_V1_SELFTEST_OK")


def probe(config: dict[str, Any]) -> dict[str, Any]:
    state = build_state(
        {
            "market": "US",
            "strategy_version": "R5.1_BASE_HGB",
            "signal": "SHADOW",
            "entry_allowed": False,
            "risk_gate": "PASS",
            "position_state": "FLAT",
            "payload": {
                "probability_up": 0.82,
                "probability_threshold": 0.61,
                "r5_rank": 1,
                "top1_top2_gap": 0.17,
            },
        },
        {
            "coverage_confidence": 0.9,
            "features": {
                "us2y_change_bps_1d": 4.0,
                "macro_event_free_reaction_score": -0.4,
                "macro_event_free_reaction_direction": "MIXED",
            },
        },
    )
    raw = call_gateway(
        state=state,
        api_key=load_gateway_key(config),
        model=str(config.get("model") or DEFAULT_MODEL),
        endpoint=str(config.get("endpoint") or DEFAULT_ENDPOINT),
        timeout_seconds=float(config.get("timeout_seconds", 20)),
    )
    normalized = normalize_evaluation(raw)
    return {
        "status": "READY",
        "model": normalized["model"],
        "entry_support": normalized["entry_support"],
        "entry_support_probabilities": normalized["entry_support_probabilities"],
        "positive_ev_probability": normalized["positive_ev_probability"],
        "regime": normalized["regime"],
        "conviction_score": normalized["conviction_score"],
        "addon_support_probability": normalized["addon_support_probability"],
        "usage": normalized["usage"],
        "shadow_only": True,
        "live_authority": False,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kalman JEV Shadow Decision V1")
    parser.add_argument(
        "--config",
        default=os.environ.get(
            "KALMAN_JEV_SHADOW_CONFIG",
            "/opt/kalman/app/config/jev-shadow-v1.json",
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("selftest")
    sub.add_parser("probe")
    sub.add_parser("sync")
    sub.add_parser("status")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_env()
    if args.command == "selftest":
        selftest()
        return 0

    config_path = Path(args.config).expanduser()
    config = load_config(config_path)
    if args.command == "probe":
        print(json.dumps(probe(config), ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "sync":
        print(json.dumps(sync(config), ensure_ascii=False, indent=2, default=str))
        return 0
    if args.command == "status":
        print(json.dumps(status(config), ensure_ascii=False, indent=2, default=str))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
