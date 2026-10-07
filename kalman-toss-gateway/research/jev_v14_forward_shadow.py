from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from engine.jev_shadow_decision_v1 import load_gateway_key

UTC = timezone.utc
EVAL_VERSION = "jev-v1.4-forward-shadow-v1"


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        out = value
    else:
        out = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if out.tzinfo is None:
        out = out.replace(tzinfo=UTC)
    return out.astimezone(UTC)


def f(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
        return out if math.isfinite(out) else None
    except (TypeError, ValueError):
        return None


def jdump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_runtime_env() -> None:
    env_file = os.environ.get(
        "KALMAN_ENV_FILE", "/home/taehoon/.config/kalman/jev-shadow.env"
    )
    load_dotenv(env_file, override=True)


def db_url() -> str:
    value = os.environ.get("DATABASE_URL_WRITER") or os.environ.get("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL_WRITER/DATABASE_URL missing")
    return value


def event_family(name: str | None) -> str:
    text = str(name or "").lower()
    if "nonfarm payroll" in text or "non farm payroll" in text or "employment situation" in text:
        return "NFP"
    if "consumer price index" in text or "inflation rate" in text:
        return "CPI"
    if "personal income and outlays" in text or "pce price" in text:
        return "PCE"
    if "jolts" in text or "job openings and labor turnover" in text:
        return "JOLTS"
    if text.startswith("gdp") or "gross domestic product" in text:
        return "GDP"
    if "producer price" in text or "ppi" in text:
        return "PPI"
    if "retail sales" in text:
        return "RETAIL_SALES"
    if "initial jobless claims" in text or "jobless claims" in text:
        return "JOBLESS_CLAIMS"
    return "OTHER"


def stable_id(prefix: str, *values: Any) -> str:
    material = "|".join(str(v or "") for v in values)
    return prefix + hashlib.sha256(material.encode("utf-8")).hexdigest()[:28]


def fetch_json(url: str, *, user_agent: str, timeout: float = 20.0) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body[:600]}") from exc


def calendar_rows(config: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    lookback = float(config.get("collection_lookback_hours", 8.0))
    start = (now - timedelta(hours=lookback + 2)).date().isoformat()
    end = now.date().isoformat()
    params = urllib.parse.urlencode({"from": start, "to": end})
    url = str(config["calendar_url"]).rstrip("?") + "?" + params
    payload = fetch_json(
        url,
        user_agent=str(config.get("calendar_user_agent") or "KalmanResearch/1.0"),
    )
    if not isinstance(payload, dict):
        return []
    rows = payload.get("data")
    return list(rows) if isinstance(rows, list) else []


def collect_events(conn: Any, config: dict[str, Any], now: datetime) -> dict[str, int]:
    allowed = set(str(x) for x in config.get("supported_event_families") or [])
    lookback = float(config.get("collection_lookback_hours", 8.0))
    inserted = 0
    seen = 0
    for row in calendar_rows(config, now):
        scheduled = parse_dt(row.get("scheduledAt"))
        actual = f(row.get("actual"))
        if scheduled is None or actual is None:
            continue
        if scheduled > now or scheduled < now - timedelta(hours=lookback):
            continue
        family = event_family(row.get("eventName"))
        if family == "OTHER" or (allowed and family not in allowed):
            continue
        seen += 1
        name = str(row.get("eventName") or family)
        eid = stable_id("jmf-", "xoomar", name, scheduled.isoformat())
        payload = {
            "provider": "xoomar",
            "provider_source": row.get("source"),
            "importance": row.get("importance"),
            "period_label": row.get("periodLabel"),
            "forecast_raw": row.get("forecast"),
            "license_semantics": "research_input_first_seen_only",
        }
        result = conn.execute(
            """
            INSERT INTO public.jev_macro_forward_event_v1(
              event_id,source,event_family,event_name,scheduled_at,first_observed_at,
              actual,previous,consensus,unit,source_payload,research_only
            ) VALUES(%s,'xoomar_agency_aggregation',%s,%s,%s,%s,%s,%s,NULL,%s,%s::jsonb,true)
            ON CONFLICT(event_id) DO NOTHING
            RETURNING event_id
            """,
            (
                eid,
                family,
                name,
                scheduled,
                now,
                actual,
                f(row.get("previous")),
                str(row.get("unit") or "") or None,
                jdump(payload),
            ),
        ).fetchone()
        if result:
            inserted += 1
    return {"calendar_rows_eligible": seen, "events_inserted": inserted}


def yahoo_proxy_bars(
    config: dict[str, Any],
    event_at: datetime,
) -> list[tuple[datetime, float]]:
    rate = config.get("rate_proxy") or {}
    symbol = str(rate.get("symbol") or "SHY")
    interval = str(rate.get("interval") or "5m")
    start = event_at - timedelta(minutes=45)
    end = event_at + timedelta(minutes=90)
    params = urllib.parse.urlencode(
        {
            "period1": int(start.timestamp()),
            "period2": int(end.timestamp()),
            "interval": interval,
            "includePrePost": "true" if rate.get("include_prepost", True) else "false",
        }
    )
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + urllib.parse.quote(symbol, safe="")
        + "?"
        + params
    )
    payload = fetch_json(url, user_agent="Mozilla/5.0 KalmanResearch/1.0")
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        return []
    timestamps = result.get("timestamp") or []
    quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quotes.get("close") or []
    out: list[tuple[datetime, float]] = []
    for ts, close in zip(timestamps, closes):
        value = f(close)
        if value is None:
            continue
        out.append((datetime.fromtimestamp(int(ts), UTC), value))
    return out


def calibration_payload(config: dict[str, Any]) -> dict[str, Any]:
    rate = config.get("rate_proxy") or {}
    return {
        "target": rate.get("calibration_target"),
        "sample_n": rate.get("calibration_sample_n"),
        "r2": rate.get("calibration_r2"),
        "correlation": rate.get("calibration_correlation"),
        "bp_per_plus_1pct_proxy_return": rate.get("bp_per_plus_1pct_proxy_return"),
        "window": rate.get("calibration_window"),
        "quality": rate.get("quality"),
    }


def collect_rates(conn: Any, config: dict[str, Any], now: datetime) -> dict[str, int]:
    rate = config.get("rate_proxy") or {}
    horizons = [int(x) for x in rate.get("horizons_minutes") or [5, 15, 30, 60]]
    lookback = float(config.get("collection_lookback_hours", 8.0))
    coeff = float(rate["bp_per_plus_1pct_proxy_return"])
    rows = conn.execute(
        """
        SELECT event_id,event_family,scheduled_at
        FROM public.jev_macro_forward_event_v1
        WHERE scheduled_at BETWEEN %s AND %s
        ORDER BY scheduled_at
        """,
        (now - timedelta(hours=lookback), now),
    ).fetchall()
    inserted = 0
    eligible = 0
    for row in rows:
        event_at = row["scheduled_at"]
        due = [h for h in horizons if now >= event_at + timedelta(minutes=h)]
        if not due:
            continue
        existing_rows = conn.execute(
            """
            SELECT horizon_minutes
            FROM public.jev_macro_rate_proxy_v1
            WHERE event_id=%s
            """,
            (row["event_id"],),
        ).fetchall()
        existing = {int(x["horizon_minutes"]) for x in existing_rows}
        missing = [h for h in due if h not in existing]
        if not missing:
            continue
        eligible += 1
        bars = yahoo_proxy_bars(config, event_at)
        pre = [x for x in bars if event_at - timedelta(minutes=30) <= x[0] < event_at]
        if not pre:
            continue
        pre_at, pre_price = pre[-1]
        for horizon in missing:
            target_label = event_at + timedelta(minutes=horizon - 5)
            post = [x for x in bars if event_at <= x[0] <= target_label]
            if not post:
                continue
            post_at, post_price = post[-1]
            ret_pct = (post_price / pre_price - 1.0) * 100.0
            implied = coeff * ret_pct
            oid = stable_id(
                "jmr-",
                row["event_id"],
                rate.get("symbol", "SHY"),
                horizon,
                post_at.isoformat(),
            )
            result = conn.execute(
                """
                INSERT INTO public.jev_macro_rate_proxy_v1(
                  observation_id,event_id,proxy_symbol,horizon_minutes,
                  pre_bar_at,post_bar_at,observed_at,shy_return_pct,
                  implied_us2y_reaction_bps,calibration,research_only
                ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,true)
                ON CONFLICT(event_id,horizon_minutes) DO NOTHING
                RETURNING observation_id
                """,
                (
                    oid,
                    row["event_id"],
                    str(rate.get("symbol") or "SHY"),
                    horizon,
                    pre_at,
                    post_at,
                    now,
                    ret_pct,
                    implied,
                    jdump(calibration_payload(config)),
                ),
            ).fetchone()
            if result:
                inserted += 1
    return {"rate_events_eligible": eligible, "rate_rows_inserted": inserted}


def collect(config: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    with psycopg.connect(db_url(), row_factory=dict_row, connect_timeout=15) as conn:
        ev = collect_events(conn, config, now)
        conn.commit()
        rates = collect_rates(conn, config, now)
        conn.commit()
    return {
        "status": "READY",
        "version": EVAL_VERSION,
        "observed_at": now.isoformat(),
        **ev,
        **rates,
        "research_only": True,
    }


def probabilities(answer: Any) -> dict[str, float]:
    if not isinstance(answer, dict):
        return {}
    for key in ("probabilities", "scores", "distribution"):
        raw = answer.get(key)
        if isinstance(raw, dict):
            out: dict[str, float] = {}
            for k, v in raw.items():
                value = f(v)
                if value is not None:
                    out[str(k)] = value
            return out
    return {}


def choice(answer: Any) -> str | None:
    if isinstance(answer, str):
        return answer
    if not isinstance(answer, dict):
        return None
    for key in ("choice", "value", "answer", "label"):
        value = answer.get(key)
        if isinstance(value, str):
            return value
    dist = probabilities(answer)
    return max(dist, key=dist.get) if dist else None


def score(answer: Any) -> float | None:
    if isinstance(answer, (int, float)):
        return float(answer)
    if isinstance(answer, dict):
        for key in ("score", "value", "mean"):
            value = f(answer.get(key))
            if value is not None:
                return value
    return None


def boolean_probability(answer: Any) -> float | None:
    if isinstance(answer, bool):
        return 1.0 if answer else 0.0
    if not isinstance(answer, dict):
        return None
    raw = answer.get("probability")
    if isinstance(raw, dict):
        for key in ("true", "True", "TRUE"):
            if key in raw:
                return f(raw[key])
    value = f(raw)
    if value is not None:
        return value
    dist = probabilities(answer)
    for key in ("true", "True", "TRUE", "yes", "YES"):
        if key in dist:
            return dist[key]
    return None


def confidence_map(raw: dict[str, Any]) -> dict[str, float]:
    try:
        meta = raw["providerMetadata"]["typesafe"]["confidence"]
    except Exception:
        return {}
    if not isinstance(meta, dict):
        return {}
    out: dict[str, float] = {}
    for key, value in meta.items():
        parsed = f(value)
        if parsed is not None:
            out[str(key)] = parsed
    return out


def jev_questions() -> dict[str, Any]:
    return {
        "event_risk": {
            "type": "choice",
            "instructions": (
                "Using only the supplied first-seen-safe macro actuals and empirical intraday rate proxy, "
                "classify incremental risk to an already-selected US long candidate over four canonical hourly bars. "
                "A missing consensus means actual-minus-previous is not a forecast surprise."
            ),
            "criteria": {
                "NORMAL": "No material incremental macro/event risk.",
                "CAUTION": "Moderate adverse risk or meaningful uncertainty.",
                "SHOCK": "Strong adverse event/rates shock.",
            },
        },
        "execution_timing": {
            "type": "choice",
            "instructions": (
                "Choose execution posture using only macro/event and anonymized backward-looking sensitivity. "
                "Prefer NOW when evidence is insufficient. Do not invent a consensus surprise."
            ),
            "criteria": {
                "NOW": "No sufficiently strong reason to delay.",
                "WAIT_1": "Delay one canonical hourly bar.",
                "WAIT_2": "Delay two canonical hourly bars.",
                "AVOID": "Avoid because evidence is strongly adverse.",
            },
        },
        "exposure_impact": {
            "type": "choice",
            "instructions": "Classify incremental event impact for the anonymized sensitivity profile.",
            "criteria": {
                "FAVORABLE": "Macro/rates state is favorable for this profile.",
                "NEUTRAL": "No reliable directional impact.",
                "ADVERSE": "Macro/rates state is adverse for this profile.",
            },
        },
        "evidence_sufficient": {
            "type": "boolean",
            "instructions": (
                "Is the first-seen-safe evidence sufficient for a non-neutral overlay decision? "
                "Treat missing consensus as a material limitation."
            ),
        },
        "adverse_next_4h": {
            "type": "boolean",
            "instructions": "Is the evidence more consistent with adverse than non-adverse conditions over four bars?",
        },
        "supportive_next_4h": {
            "type": "boolean",
            "instructions": "Is the evidence more consistent with supportive than non-supportive conditions over four bars?",
        },
        "materiality": {
            "type": "score",
            "instructions": "Rate macro/event materiality for the four-bar decision.",
            "criteria": ["immaterial", "low", "moderate", "high", "very high"],
        },
    }


def call_jev(config: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    jev = config.get("jev") or {}
    api_key = load_gateway_key(
        {"gateway_key_file": str(jev.get("gateway_key_file") or "")}
    )
    body = jdump(
        {
            "model": str(jev.get("model") or "typesafe-ai/jev"),
            "state": state,
            "questions": jev_questions(),
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        str(jev.get("endpoint") or "https://ai-gateway.vercel.sh/v1/evaluate"),
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=float(jev.get("timeout_seconds", 30))) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"JEV HTTP {exc.code}: {body_text[:1000]}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("JEV response is not an object")
    return result


def sensitivity(conn: Any, symbol: str, as_of: datetime) -> dict[str, Any]:
    row = conn.execute(
        """
        WITH px AS (
          SELECT symbol,ts,close::double precision AS close,
                 lag(close::double precision) OVER (PARTITION BY symbol ORDER BY ts) AS prev
          FROM public.market_price
          WHERE market='US' AND timeframe='60m'
            AND ts BETWEEN %s-interval '20 days' AND %s
        ),
        r AS (
          SELECT symbol,ts,close/prev-1.0 AS ret
          FROM px
          WHERE prev IS NOT NULL AND abs(close/prev-1.0)<0.20
        ),
        m AS (
          SELECT ts,avg(ret) AS mret
          FROM r GROUP BY ts
        ),
        sr AS (
          SELECT ts,ret FROM r WHERE symbol=%s
        ),
        hist AS (
          SELECT ts,close::double precision AS close,
                 row_number() OVER (ORDER BY ts DESC) AS rn
          FROM public.market_price
          WHERE market='US' AND timeframe='60m' AND symbol=%s AND ts<=%s
        )
        SELECT covar_samp(sr.ret,m.mret)/NULLIF(var_samp(m.mret),0) AS beta_eqw,
               stddev_samp(sr.ret) AS rv_bar,
               count(*) AS nobs,
               (SELECT h1.close/h5.close-1.0
                FROM hist h1 CROSS JOIN hist h5
                WHERE h1.rn=1 AND h5.rn=5) AS prior_ret_4b
        FROM sr JOIN m USING(ts)
        """,
        (as_of, as_of, symbol, symbol, as_of),
    ).fetchone()
    return {
        "market_beta_eqw_20d": f(row["beta_eqw"]) if row else None,
        "realized_vol_bar_20d": f(row["rv_bar"]) if row else None,
        "prior_return_4b": f(row["prior_ret_4b"]) if row else None,
        "sensitivity_observations": int(row["nobs"] or 0) if row else 0,
    }


def candidate_signals(conn: Any, config: dict[str, Any]) -> list[dict[str, Any]]:
    start_at = parse_dt(config.get("forward_start_at_utc"))
    if start_at is None:
        raise RuntimeError("forward_start_at_utc missing")
    minutes = int(config.get("signal_bar_minutes", 60))
    limit = int(config.get("max_candidates_per_run", 24))
    return list(
        conn.execute(
            """
            SELECT s.run_id::text AS run_id,s.market,s.symbol,s.as_of,s.strategy_version,
                   s.as_of + (%s * interval '1 minute') AS decision_as_of
            FROM public.strategy_signal s
            LEFT JOIN public.jev_macro_overlay_forward_v1 j
              ON j.run_id=s.run_id::text
             AND j.symbol=s.symbol
             AND j.strategy_version=s.strategy_version
             AND j.evaluation_version=%s
            WHERE s.market=%s
              AND s.strategy_version=%s
              AND s.as_of >= %s
              AND s.signal='SHADOW'
              AND lower(COALESCE(s.payload->>'allow_trade_shadow','false'))='true'
              AND s.as_of + (%s * interval '1 minute') <= now()
              AND j.decision_id IS NULL
            ORDER BY s.as_of,s.symbol
            LIMIT %s
            """,
            (
                minutes,
                EVAL_VERSION,
                str(config.get("market") or "US"),
                str(config.get("strategy_version") or "R5.1_BASE_HGB"),
                start_at,
                minutes,
                limit,
            ),
        ).fetchall()
    )


def event_bundle(
    conn: Any,
    config: dict[str, Any],
    decision_as_of: datetime,
) -> list[dict[str, Any]]:
    max_age = float(config.get("event_max_age_hours", 6.0))
    latest = conn.execute(
        """
        SELECT scheduled_at
        FROM public.jev_macro_forward_event_v1
        WHERE scheduled_at <= %s
          AND scheduled_at >= %s
          AND first_observed_at <= %s
        ORDER BY scheduled_at DESC
        LIMIT 1
        """,
        (decision_as_of, decision_as_of - timedelta(hours=max_age), decision_as_of),
    ).fetchone()
    if not latest:
        return []
    center = latest["scheduled_at"]
    window = float(config.get("bundle_window_minutes", 10.0))
    return list(
        conn.execute(
            """
            SELECT *
            FROM public.jev_macro_forward_event_v1
            WHERE scheduled_at BETWEEN %s AND %s
              AND first_observed_at <= %s
            ORDER BY event_family,event_id
            """,
            (
                center - timedelta(minutes=window),
                center + timedelta(minutes=window),
                decision_as_of,
            ),
        ).fetchall()
    )


def rate_bundle(
    conn: Any,
    events: list[dict[str, Any]],
    decision_as_of: datetime,
) -> dict[str, Any]:
    if not events:
        return {}
    ids = [str(x["event_id"]) for x in events]
    rows = conn.execute(
        """
        SELECT r.*
        FROM public.jev_macro_rate_proxy_v1 r
        WHERE r.event_id = ANY(%s)
          AND r.observed_at <= %s
        ORDER BY r.horizon_minutes,r.observed_at
        """,
        (ids, decision_as_of),
    ).fetchall()
    out: dict[str, Any] = {}
    for row in rows:
        key = f"{int(row['horizon_minutes'])}m"
        if key in out:
            continue
        out[key] = {
            "shy_return_pct": f(row["shy_return_pct"]),
            "implied_us2y_reaction_bps": f(row["implied_us2y_reaction_bps"]),
            "proxy": str(row["proxy_symbol"]),
        }
    return out


def build_state(
    config: dict[str, Any],
    events: list[dict[str, Any]],
    rates: dict[str, Any],
    asset_sensitivity: dict[str, Any],
    decision_as_of: datetime,
) -> dict[str, Any]:
    event_items = []
    for row in events:
        first_delay = (
            (row["first_observed_at"] - row["scheduled_at"]).total_seconds() / 60.0
        )
        actual = f(row["actual"])
        previous = f(row["previous"])
        event_items.append(
            {
                "family": str(row["event_family"]),
                "actual": actual,
                "previous": previous,
                "actual_minus_previous": (
                    actual - previous
                    if actual is not None and previous is not None
                    else None
                ),
                "unit": row["unit"],
                "consensus": None,
                "consensus_available": False,
                "actual_minus_previous_is_not_consensus_surprise": True,
                "first_observed_delay_minutes": max(0.0, first_delay),
                "source_quality": "FIRST_SEEN_AGENCY_AGGREGATION_RESEARCH_ONLY",
            }
        )
    scheduled = max(x["scheduled_at"] for x in events)
    age_minutes = max(
        0.0, (decision_as_of - scheduled).total_seconds() / 60.0
    )
    return {
        "contract": {
            "experiment": EVAL_VERSION,
            "input_mode": "FIRST_SEEN_ACTUAL_PLUS_SHY_RATE_PROXY",
            "historical_headline_text_excluded": True,
            "candidate_identity_blinded": True,
            "absolute_signal_time_blinded": True,
            "future_outcome_hidden": True,
            "baseline_model_score_excluded": True,
            "consensus_missing_is_explicit": True,
            "live_execution_authority": False,
            "holding_horizon_bars": 4,
            "information_cutoff": "R5.1_BAR_COMPLETION",
        },
        "event": {
            "age_minutes": age_minutes,
            "bundle": event_items,
        },
        "intraday_rates": {
            "horizons": rates,
            "calibration": calibration_payload(config),
        },
        "asset_sensitivity": asset_sensitivity,
    }


def overlay_decision_id(run_id: str, symbol: str, strategy_version: str) -> str:
    return stable_id("jvf-", run_id, symbol, strategy_version, EVAL_VERSION)


def store_overlay(
    conn: Any,
    *,
    signal: dict[str, Any],
    status: str,
    events: list[dict[str, Any]] | None = None,
    rates: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
    normalized: dict[str, Any] | None = None,
    raw: dict[str, Any] | None = None,
    gate_pass: bool = False,
    gated_timing: str = "NOW",
    error: str | None = None,
) -> None:
    events = events or []
    rates = rates or {}
    state = state or {}
    normalized = normalized or {}
    event = events[0] if events else None
    event_age = None
    if events:
        latest_sched = max(x["scheduled_at"] for x in events)
        event_age = max(
            0.0,
            (signal["decision_as_of"] - latest_sched).total_seconds() / 60.0,
        )
    conn.execute(
        """
        INSERT INTO public.jev_macro_overlay_forward_v1(
          decision_id,run_id,market,symbol,strategy_version,signal_as_of,decision_as_of,
          evaluation_version,evaluation_status,event_id,event_family,event_age_minutes,
          rate_horizons,state,event_risk,event_risk_probabilities,event_risk_confidence,
          execution_timing,execution_timing_probabilities,execution_timing_confidence,
          exposure_impact,exposure_impact_probabilities,exposure_impact_confidence,
          evidence_sufficient_probability,adverse_next_4h_probability,
          supportive_next_4h_probability,materiality_score,materiality_confidence,
          gate_pass,gated_execution_timing,answer_payload,usage,provider_cost_usd,
          error_message,shadow_only,can_veto_live,can_size_live,updated_at
        ) VALUES(
          %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
          %s::jsonb,%s::jsonb,%s,%s::jsonb,%s,
          %s,%s::jsonb,%s,%s,%s::jsonb,%s,
          %s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,
          true,false,false,now()
        )
        ON CONFLICT(decision_id) DO UPDATE SET
          evaluation_status=excluded.evaluation_status,
          rate_horizons=excluded.rate_horizons,
          state=excluded.state,
          event_risk=excluded.event_risk,
          event_risk_probabilities=excluded.event_risk_probabilities,
          event_risk_confidence=excluded.event_risk_confidence,
          execution_timing=excluded.execution_timing,
          execution_timing_probabilities=excluded.execution_timing_probabilities,
          execution_timing_confidence=excluded.execution_timing_confidence,
          exposure_impact=excluded.exposure_impact,
          exposure_impact_probabilities=excluded.exposure_impact_probabilities,
          exposure_impact_confidence=excluded.exposure_impact_confidence,
          evidence_sufficient_probability=excluded.evidence_sufficient_probability,
          adverse_next_4h_probability=excluded.adverse_next_4h_probability,
          supportive_next_4h_probability=excluded.supportive_next_4h_probability,
          materiality_score=excluded.materiality_score,
          materiality_confidence=excluded.materiality_confidence,
          gate_pass=excluded.gate_pass,
          gated_execution_timing=excluded.gated_execution_timing,
          answer_payload=excluded.answer_payload,
          usage=excluded.usage,
          provider_cost_usd=excluded.provider_cost_usd,
          error_message=excluded.error_message,
          shadow_only=true,can_veto_live=false,can_size_live=false,updated_at=now()
        """,
        (
            overlay_decision_id(
                str(signal["run_id"]),
                str(signal["symbol"]),
                str(signal["strategy_version"]),
            ),
            str(signal["run_id"]),
            str(signal["market"]),
            str(signal["symbol"]),
            str(signal["strategy_version"]),
            signal["as_of"],
            signal["decision_as_of"],
            EVAL_VERSION,
            status,
            event["event_id"] if event else None,
            event["event_family"] if event else None,
            event_age,
            jdump(rates),
            jdump(state),
            normalized.get("event_risk"),
            jdump(normalized.get("event_risk_probabilities") or {}),
            normalized.get("event_risk_confidence"),
            normalized.get("execution_timing"),
            jdump(normalized.get("execution_timing_probabilities") or {}),
            normalized.get("execution_timing_confidence"),
            normalized.get("exposure_impact"),
            jdump(normalized.get("exposure_impact_probabilities") or {}),
            normalized.get("exposure_impact_confidence"),
            normalized.get("evidence_sufficient_probability"),
            normalized.get("adverse_next_4h_probability"),
            normalized.get("supportive_next_4h_probability"),
            normalized.get("materiality_score"),
            normalized.get("materiality_confidence"),
            gate_pass,
            gated_timing,
            jdump(raw or {}),
            jdump(normalized.get("usage") or {}),
            normalized.get("provider_cost_usd"),
            error,
        ),
    )


def normalize_jev(raw: dict[str, Any]) -> dict[str, Any]:
    answers = raw.get("answers") if isinstance(raw.get("answers"), dict) else {}
    confidence = confidence_map(raw)
    gateway = (raw.get("providerMetadata") or {}).get("gateway") or {}
    return {
        "event_risk": choice(answers.get("event_risk")),
        "event_risk_probabilities": probabilities(answers.get("event_risk")),
        "event_risk_confidence": confidence.get("event_risk"),
        "execution_timing": choice(answers.get("execution_timing")),
        "execution_timing_probabilities": probabilities(answers.get("execution_timing")),
        "execution_timing_confidence": confidence.get("execution_timing"),
        "exposure_impact": choice(answers.get("exposure_impact")),
        "exposure_impact_probabilities": probabilities(answers.get("exposure_impact")),
        "exposure_impact_confidence": confidence.get("exposure_impact"),
        "evidence_sufficient_probability": boolean_probability(
            answers.get("evidence_sufficient")
        ),
        "adverse_next_4h_probability": boolean_probability(
            answers.get("adverse_next_4h")
        ),
        "supportive_next_4h_probability": boolean_probability(
            answers.get("supportive_next_4h")
        ),
        "materiality_score": score(answers.get("materiality")),
        "materiality_confidence": confidence.get("materiality"),
        "usage": raw.get("usage") if isinstance(raw.get("usage"), dict) else {},
        "provider_cost_usd": f(gateway.get("cost")),
    }


def apply_gate(config: dict[str, Any], normalized: dict[str, Any]) -> tuple[bool, str]:
    gate = config.get("decision_gate") or {}
    evidence_threshold = float(gate.get("min_evidence_probability", 0.70))
    confidence_threshold = float(
        gate.get("min_execution_timing_confidence", 0.65)
    )
    fallback = str(gate.get("fallback_action") or "NOW")
    evidence = f(normalized.get("evidence_sufficient_probability")) or 0.0
    confidence = f(normalized.get("execution_timing_confidence")) or 0.0
    passed = evidence >= evidence_threshold and confidence >= confidence_threshold
    timing = str(normalized.get("execution_timing") or fallback) if passed else fallback
    return passed, timing


def sync(config: dict[str, Any]) -> dict[str, Any]:
    counts = {
        "seen": 0,
        "ready": 0,
        "skipped_no_event": 0,
        "skipped_rate_not_ready": 0,
        "api_error": 0,
        "gate_pass": 0,
    }
    with psycopg.connect(db_url(), row_factory=dict_row, connect_timeout=15) as conn:
        for signal in candidate_signals(conn, config):
            signal = dict(signal)
            counts["seen"] += 1
            events = event_bundle(conn, config, signal["decision_as_of"])
            if not events:
                store_overlay(conn, signal=signal, status="SKIPPED_NO_EVENT")
                conn.commit()
                counts["skipped_no_event"] += 1
                continue
            rates = rate_bundle(conn, events, signal["decision_as_of"])
            if "5m" not in rates:
                store_overlay(
                    conn,
                    signal=signal,
                    status="SKIPPED_RATE_NOT_READY",
                    events=events,
                    rates=rates,
                )
                conn.commit()
                counts["skipped_rate_not_ready"] += 1
                continue
            asset = sensitivity(conn, signal["symbol"], signal["as_of"])
            state = build_state(
                config,
                events,
                rates,
                asset,
                signal["decision_as_of"],
            )
            encoded = jdump(state)
            if str(signal["symbol"]) in encoded or str(signal["run_id"]) in encoded:
                raise RuntimeError("candidate identity leaked into JEV state")
            try:
                raw = call_jev(config, state)
                normalized = normalize_jev(raw)
                passed, gated = apply_gate(config, normalized)
                store_overlay(
                    conn,
                    signal=signal,
                    status="READY",
                    events=events,
                    rates=rates,
                    state=state,
                    normalized=normalized,
                    raw=raw,
                    gate_pass=passed,
                    gated_timing=gated,
                )
                conn.commit()
                counts["ready"] += 1
                counts["gate_pass"] += int(passed)
            except Exception as exc:
                store_overlay(
                    conn,
                    signal=signal,
                    status="API_ERROR",
                    events=events,
                    rates=rates,
                    state=state,
                    error=str(exc)[:1800],
                )
                conn.commit()
                counts["api_error"] += 1
    return {
        "status": "READY",
        "evaluation_version": EVAL_VERSION,
        **counts,
        "shadow_only": True,
        "live_authority": False,
    }


def status(config: dict[str, Any]) -> dict[str, Any]:
    with psycopg.connect(db_url(), row_factory=dict_row, connect_timeout=15) as conn:
        event = conn.execute(
            """
            SELECT count(*) AS n,max(scheduled_at) AS latest_scheduled_at,
                   max(first_observed_at) AS latest_first_observed_at
            FROM public.jev_macro_forward_event_v1
            """
        ).fetchone()
        rate = conn.execute(
            """
            SELECT count(*) AS n,max(observed_at) AS latest_observed_at
            FROM public.jev_macro_rate_proxy_v1
            """
        ).fetchone()
        decisions = conn.execute(
            """
            SELECT evaluation_status,count(*) AS n,
                   max(signal_as_of) AS latest_signal_as_of,
                   count(*) FILTER (WHERE gate_pass) AS gate_pass_n
            FROM public.jev_macro_overlay_forward_v1
            WHERE evaluation_version=%s
            GROUP BY evaluation_status
            ORDER BY evaluation_status
            """,
            (EVAL_VERSION,),
        ).fetchall()
    return {
        "status": "READY",
        "evaluation_version": EVAL_VERSION,
        "events": dict(event) if event else {},
        "rates": dict(rate) if rate else {},
        "decisions": [dict(x) for x in decisions],
        "gate": config.get("decision_gate") or {},
        "shadow_only": True,
        "live_authority": False,
    }


def selftest(config: dict[str, Any]) -> None:
    assert event_family("Nonfarm Payrolls (Employment Situation)") == "NFP"
    assert event_family("Personal Income and Outlays (PCE)") == "PCE"
    assert event_family("GDP (Third Estimate), State PCE") == "GDP"
    assert event_family("Initial Jobless Claims") == "JOBLESS_CLAIMS"
    normalized = {
        "evidence_sufficient_probability": 0.69,
        "execution_timing_confidence": 0.99,
        "execution_timing": "WAIT_2",
    }
    passed, timing = apply_gate(config, normalized)
    assert passed is False and timing == "NOW"
    normalized["evidence_sufficient_probability"] = 0.90
    normalized["execution_timing_confidence"] = 0.80
    passed, timing = apply_gate(config, normalized)
    assert passed is True and timing == "WAIT_2"
    fake_event = {
        "event_family": "NFP",
        "actual": 29.0,
        "previous": 133.0,
        "unit": "thousands",
        "scheduled_at": datetime(2026, 10, 2, 12, 30, tzinfo=UTC),
        "first_observed_at": datetime(2026, 10, 2, 12, 34, tzinfo=UTC),
    }
    state = build_state(
        config,
        [fake_event],
        {"5m": {"implied_us2y_reaction_bps": -6.1, "proxy": "SHY"}},
        {"market_beta_eqw_20d": 1.1, "realized_vol_bar_20d": 0.01},
        datetime(2026, 10, 2, 13, 30, tzinfo=UTC),
    )
    encoded = jdump(state)
    assert "NFP" in encoded
    assert "29.0" in encoded
    assert "consensus_available" in encoded
    assert "symbol" not in encoded
    assert "run_id" not in encoded
    assert "2026-10-02" not in encoded
    assert state["contract"]["live_execution_authority"] is False
    print("JEV_V14_FORWARD_SHADOW_SELFTEST_OK")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kalman JEV V1.4 Forward Shadow")
    parser.add_argument(
        "--config",
        default=os.environ.get(
            "KALMAN_JEV_V14_CONFIG",
            "/home/taehoon/.local/share/kalman-jev-shadow/config/jev-macro-forward-v1.4.json",
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("collect", "sync", "status", "selftest"):
        sub.add_parser(name)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_runtime_env()
    config = load_config(Path(args.config).expanduser())
    if args.command == "selftest":
        selftest(config)
        return 0
    if args.command == "collect":
        result = collect(config)
    elif args.command == "sync":
        result = sync(config)
    else:
        result = status(config)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
