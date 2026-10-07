from __future__ import annotations

import argparse
import csv
import json
import math
import os
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

from engine.jev_shadow_decision_v1 import load_gateway_key
from engine.jev_macro_event_v1 import official_event_family

MODEL = "typesafe-ai/jev"
ENDPOINT = "https://ai-gateway.vercel.sh/v1/evaluate"
TEST_VERSION = "jev-v1.4-three-arm-recent-test"
COST = 0.001

MACRO_KEYS = (
    "macro_event_signal_ready",
    "macro_event_shadow_score",
    "macro_event_shadow_direction",
    "macro_event_free_reaction_ready",
    "macro_event_free_reaction_score",
    "macro_event_free_reaction_direction",
    "us2y_change_bps_1d",
    "us2y_event_reaction_bps",
    "us2y_event_reaction_z",
    "us2y_reaction_quality",
    "fed_policy_repricing_bps",
    "fed_policy_repricing_quality",
    "policy_proxy_change_bps_1d",
    "policy_proxy_spread_bps",
    "us_priority_surprise_index",
    "us_target_macro_event_score",
    "official_macro_count_6h",
)

def f(v):
    if v is None:
        return None
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None

def questions() -> dict[str, Any]:
    return {
        "event_risk": {
            "type": "choice",
            "instructions": (
                "Using only the supplied point-in-time macro/event state, classify incremental risk "
                "to an already-selected US long candidate over the next four canonical hourly bars."
            ),
            "criteria": {
                "NORMAL": "No material incremental macro/event risk.",
                "CAUTION": "Material uncertainty or moderate adverse macro/event risk; delaying entry may help.",
                "SHOCK": "Strong adverse macro/event shock that could justify avoiding or materially delaying entry.",
            },
        },
        "execution_timing": {
            "type": "choice",
            "instructions": (
                "Choose the best execution posture for an already-selected long candidate using only "
                "the supplied macro/event and anonymized backward-looking sensitivity state."
            ),
            "criteria": {
                "NOW": "No reason to delay the long entry.",
                "WAIT_1": "Wait one canonical hourly bar before entering.",
                "WAIT_2": "Wait two canonical hourly bars before entering.",
                "AVOID": "Avoid this entry because macro/event risk is materially adverse.",
            },
        },
        "exposure_impact": {
            "type": "choice",
            "instructions": (
                "Given the anonymized asset sensitivity profile, classify the incremental macro/event "
                "impact on this candidate over four bars."
            ),
            "criteria": {
                "FAVORABLE": "Macro/event state is favorable for this sensitivity profile.",
                "NEUTRAL": "No clear incremental directional impact.",
                "ADVERSE": "Macro/event state is adverse for this sensitivity profile.",
            },
        },
        "evidence_sufficient": {
            "type": "boolean",
            "instructions": "Is the supplied point-in-time evidence sufficient to make a non-neutral macro overlay decision?",
        },
        "adverse_next_4h": {
            "type": "boolean",
            "instructions": "Is macro/event evidence more consistent with adverse than non-adverse conditions for this long candidate over four bars?",
        },
        "supportive_next_4h": {
            "type": "boolean",
            "instructions": "Is macro/event evidence more consistent with supportive than non-supportive conditions for this long candidate over four bars?",
        },
        "materiality": {
            "type": "score",
            "instructions": "Rate the materiality of the macro/event information for this four-bar decision.",
            "criteria": ["immaterial", "low", "moderate", "high", "very high"],
        },
    }

def call_jev(state: dict[str, Any], api_key: str) -> dict[str, Any]:
    body = json.dumps({"model": MODEL, "state": state, "questions": questions()}, separators=(",", ":")).encode()
    req = urllib.request.Request(
        ENDPOINT, data=body,
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())

def probs(ans: Any) -> dict[str, float]:
    if not isinstance(ans, dict):
        return {}
    for k in ("probabilities", "scores", "distribution"):
        v = ans.get(k)
        if isinstance(v, dict):
            out = {}
            for kk, vv in v.items():
                fv = f(vv)
                if fv is not None:
                    out[str(kk)] = fv
            return out
    return {}

def choice(ans: Any) -> str | None:
    if isinstance(ans, str):
        return ans
    if not isinstance(ans, dict):
        return None
    for k in ("choice", "value", "answer", "label"):
        if isinstance(ans.get(k), str):
            return ans[k]
    p = probs(ans)
    return max(p, key=p.get) if p else None

def score(ans: Any) -> float | None:
    if isinstance(ans, (int, float)):
        return float(ans)
    if isinstance(ans, dict):
        for k in ("score", "value", "mean"):
            x = f(ans.get(k))
            if x is not None:
                return x
    return None

def bool_prob(ans: Any) -> float | None:
    if isinstance(ans, bool):
        return 1.0 if ans else 0.0
    if isinstance(ans, dict):
        for k in ("probability", "score", "value"):
            x = f(ans.get(k))
            if x is not None:
                return x
        p = probs(ans)
        for key in ("true", "TRUE", "True", "yes", "YES"):
            if key in p:
                return p[key]
    return None

def confidence_map(raw: dict[str, Any]) -> dict[str, float]:
    try:
        c = raw["providerMetadata"]["typesafe"]["confidence"]
    except Exception:
        return {}
    if not isinstance(c, dict):
        return {}
    return {str(k): float(v) for k, v in c.items() if f(v) is not None}

def candidate_rows(conn) -> list[dict[str, Any]]:
    return list(conn.execute(
        """
        SELECT s.run_id::text,s.symbol,s.as_of,
               o.source,o.title,o.safe_available_at,
               EXTRACT(EPOCH FROM (s.as_of-o.safe_available_at))/60.0 AS event_age_minutes,
               m.coverage_confidence,m.features AS macro_features
        FROM public.strategy_signal s
        JOIN LATERAL (
          SELECT a.source,a.title,GREATEST(a.available_at,a.first_seen_at) AS safe_available_at
          FROM public.news_article a
          JOIN public.news_event e ON e.article_id=a.article_id
          WHERE e.event_type='MACRO'
            AND a.source = ANY(ARRAY['fed_monetary','bls_cpi','bls_employment','bls_jolts','bea_releases'])
            AND GREATEST(a.available_at,a.first_seen_at) <= s.as_of
            AND GREATEST(a.available_at,a.first_seen_at) >= s.as_of-interval '6 hours'
          ORDER BY GREATEST(a.available_at,a.first_seen_at) DESC
          LIMIT 1
        ) o ON true
        LEFT JOIN LATERAL (
          SELECT coverage_confidence,features
          FROM public.news_feature_snapshot n
          WHERE n.market='GLOBAL' AND n.symbol='GLOBAL'
            AND n.feature_version='macro-event-feature-v1'
            AND n.as_of<=s.as_of
          ORDER BY n.as_of DESC LIMIT 1
        ) m ON true
        WHERE s.market='US' AND s.strategy_version='R5.1_BASE_HGB'
        ORDER BY s.as_of
        """
    ).fetchall())

def sensitivity(conn, symbol: str, as_of: datetime) -> dict[str, Any]:
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
        "market_beta_eqw_20d": f(row["beta_eqw"]),
        "realized_vol_bar_20d": f(row["rv_bar"]),
        "prior_return_4b": f(row["prior_ret_4b"]),
        "sensitivity_observations": int(row["nobs"] or 0),
    }

def outcomes(conn, symbol: str, as_of: datetime) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT ts,close::double precision AS close
        FROM public.market_price
        WHERE market='US' AND timeframe='60m' AND symbol=%s AND ts>=%s
        ORDER BY ts LIMIT 7
        """,
        (symbol, as_of),
    ).fetchall()
    closes = [float(r["close"]) for r in rows]
    def ret(i, j):
        return closes[j]/closes[i]-1.0-COST if len(closes)>j else None
    steps = [abs(closes[i]/closes[i-1]-1.0) for i in range(1,len(closes))]
    is_friday = as_of.astimezone(ZoneInfo("America/New_York")).weekday() == 4
    vals = {"NOW": ret(0,4), "WAIT_1": ret(1,5), "WAIT_2": ret(2,6)}
    valid = {k:v for k,v in vals.items() if v is not None}
    best = max(valid,key=valid.get) if valid else None
    if valid and max(valid.values()) <= 0:
        best = "AVOID"
    return {
        "now_net_4b": vals["NOW"],
        "wait1_net_4b": vals["WAIT_1"],
        "wait2_net_4b": vals["WAIT_2"],
        "hindsight_best": best,
        "max_step_abs_return": max(steps) if steps else None,
        "price_qc_flag": bool(steps and max(steps)>0.15),
        "friday_signal_utc": is_friday,
    }

def state_for(rec: dict[str, Any], sens: dict[str, Any]) -> dict[str, Any]:
    feats = rec.get("macro_features") or {}
    event = {
        "family": official_event_family(rec.get("source"), rec.get("title")),
        "age_minutes": f(rec.get("event_age_minutes")),
        "coverage_confidence": f(rec.get("coverage_confidence")),
    }
    for k in MACRO_KEYS:
        v = feats.get(k)
        if isinstance(v, (str,int,float,bool)) or v is None:
            if v is not None:
                event[k] = v
    return {
        "contract": {
            "experiment": TEST_VERSION,
            "input_mode": "STRUCTURED_ONLY",
            "historical_headline_text_excluded": True,
            "candidate_identity_blinded": True,
            "absolute_signal_time_blinded": True,
            "future_outcome_hidden": True,
            "baseline_model_score_excluded": True,
            "live_execution_authority": False,
            "holding_horizon_bars": 4,
        },
        "event": event,
        "asset_sensitivity": sens,
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=8)
    p.add_argument("--output", default="/home/taehoon/.local/share/kalman-jev-backtest/results/jev_v14_three_arm_recent.json")
    args = p.parse_args()

    load_dotenv(os.environ.get("KALMAN_ENV_FILE","/home/taehoon/.config/kalman/jev-shadow.env"), override=True)
    db = os.environ["DATABASE_URL_WRITER"]
    api_key = load_gateway_key({"gateway_key_file": os.environ.get(
        "JEV_GATEWAY_KEY_FILE","/home/taehoon/.config/kalman/secure/jev_gateway_key_create.out"
    )})

    out = []
    with psycopg.connect(db,row_factory=dict_row,connect_timeout=15) as conn:
        rows = candidate_rows(conn)[:args.limit]
        for rec in rows:
            sens = sensitivity(conn,rec["symbol"],rec["as_of"])
            state = state_for(rec,sens)
            raw = call_jev(state,api_key)
            ans = raw.get("answers") if isinstance(raw.get("answers"),dict) else {}
            conf = confidence_map(raw)
            oc = outcomes(conn,rec["symbol"],rec["as_of"])
            result = {
                "run_id": rec["run_id"],
                "symbol": rec["symbol"],
                "signal_as_of": rec["as_of"].isoformat(),
                "event_family": state["event"]["family"],
                "event_age_minutes": state["event"]["age_minutes"],
                "state": state,
                "event_risk": choice(ans.get("event_risk")),
                "event_risk_probabilities": probs(ans.get("event_risk")),
                "execution_timing": choice(ans.get("execution_timing")),
                "execution_timing_probabilities": probs(ans.get("execution_timing")),
                "exposure_impact": choice(ans.get("exposure_impact")),
                "exposure_impact_probabilities": probs(ans.get("exposure_impact")),
                "evidence_sufficient_probability": bool_prob(ans.get("evidence_sufficient")),
                "adverse_next_4h_probability": bool_prob(ans.get("adverse_next_4h")),
                "supportive_next_4h_probability": bool_prob(ans.get("supportive_next_4h")),
                "materiality_score": score(ans.get("materiality")),
                "confidence": conf,
                "usage": raw.get("usage") or {},
                "provider_cost": (((raw.get("providerMetadata") or {}).get("gateway") or {}).get("cost")),
                **oc,
            }
            out.append(result)
            print(json.dumps({
                "symbol": result["symbol"],
                "family": result["event_family"],
                "risk": result["event_risk"],
                "timing": result["execution_timing"],
                "impact": result["exposure_impact"],
                "evidence_p": result["evidence_sufficient_probability"],
                "adverse_p": result["adverse_next_4h_probability"],
                "materiality": result["materiality_score"],
                "confidence": result["confidence"],
                "best_realized": result["hindsight_best"],
                "qc": result["price_qc_flag"],
            }, ensure_ascii=False))

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True,exist_ok=True)
    out_path.write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    csv_path = out_path.with_suffix(".csv")
    keys = [
        "symbol","signal_as_of","event_family","event_age_minutes","event_risk","execution_timing",
        "exposure_impact","evidence_sufficient_probability","adverse_next_4h_probability",
        "supportive_next_4h_probability","materiality_score","now_net_4b","wait1_net_4b",
        "wait2_net_4b","hindsight_best","max_step_abs_return","price_qc_flag","provider_cost"
    ]
    with csv_path.open("w",newline="",encoding="utf-8") as fh:
        w=csv.DictWriter(fh,fieldnames=keys)
        w.writeheader()
        for row in out:
            w.writerow({k:row.get(k) for k in keys})
    print(json.dumps({"status":"DONE","n":len(out),"json":str(out_path),"csv":str(csv_path)}))

if __name__ == "__main__":
    main()
