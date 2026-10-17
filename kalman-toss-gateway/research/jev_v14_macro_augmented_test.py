from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import urllib.request
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

from engine.jev_shadow_decision_v1 import load_gateway_key
from research.jev_v14_three_arm_recent_test import (
    MODEL, ENDPOINT, candidate_rows, sensitivity, outcomes,
    call_jev, probs, choice, score, bool_prob, confidence_map,
)

TEST_VERSION = "jev-v1.4-macro-augmented-recent-test"
SHY_BP_PER_1PCT = -49.80568987492392
SHY_CAL_N = 2417
SHY_CAL_R2 = 0.8518366911673452
SHY_CAL_CORR = -0.9229499938606344

def fetch_calendar(start: dt.date, end: dt.date) -> list[dict[str, Any]]:
    url = (
        "https://xoomar.com/api/markets/calendar"
        f"?from={start.isoformat()}&to={end.isoformat()}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "KalmanResearch/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        payload = json.load(r)
    return list(payload.get("data") or [])

def match_calendar_event(family: str, signal_day: dt.date, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    cands = []
    for row in rows:
        when = row.get("scheduledAt")
        if not when:
            continue
        try:
            scheduled = dt.datetime.fromisoformat(str(when).replace("Z","+00:00"))
        except Exception:
            continue
        if scheduled.date() != signal_day:
            continue
        name = str(row.get("eventName") or "").lower()
        ok = (
            (family == "GDP" and name.startswith("gdp"))
            or (family == "NFP" and ("nonfarm payroll" in name or "employment situation" in name))
            or (family == "CPI" and "consumer price" in name)
            or (family == "PCE" and "personal income and outlays" in name)
            or (family == "JOLTS" and "jolts" in name)
        )
        if ok:
            cands.append((scheduled,row))
    return cands[0][1] if cands else None

def fetch_shy_5m(event_at: dt.datetime) -> list[tuple[dt.datetime,float]]:
    start = event_at - dt.timedelta(hours=1)
    end = event_at + dt.timedelta(hours=2)
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/SHY"
        f"?period1={int(start.timestamp())}&period2={int(end.timestamp())}"
        "&interval=5m&includePrePost=true"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 KalmanResearch/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    result = ((data.get("chart") or {}).get("result") or [None])[0]
    if not result:
        return []
    ts = result.get("timestamp") or []
    closes = (((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or [])
    out = []
    for t,c in zip(ts,closes):
        if c is None:
            continue
        out.append((dt.datetime.fromtimestamp(t,dt.timezone.utc),float(c)))
    return out

def rate_reaction(event_at: dt.datetime) -> dict[str, Any]:
    rows = fetch_shy_5m(event_at)
    pre = [x for x in rows if x[0] < event_at]
    if not pre:
        return {"available": False}
    pre_t, pre_p = pre[-1]
    out: dict[str,Any] = {
        "available": True,
        "proxy": "SHY_EXTENDED_5M",
        "pre_bar_at": pre_t.isoformat(),
        "calibration": {
            "target": "DGS2_CHG_1_BP",
            "sample_n": SHY_CAL_N,
            "r2": SHY_CAL_R2,
            "correlation": SHY_CAL_CORR,
            "bp_per_plus_1pct_shy_return": SHY_BP_PER_1PCT,
            "calibration_window": "2017-01-03_to_2026-09-10",
        },
    }
    for mins in (5,15,30,60):
        target = event_at + dt.timedelta(minutes=mins-5)
        candidates = [x for x in rows if event_at <= x[0] <= target]
        if not candidates:
            continue
        t,p = candidates[-1]
        ret = p/pre_p - 1.0
        out[f"shy_return_pct_{mins}m"] = ret*100.0
        out[f"implied_us2y_reaction_bps_{mins}m"] = SHY_BP_PER_1PCT*(ret*100.0)
        out[f"post_bar_at_{mins}m"] = t.isoformat()
    return out

def questions() -> dict[str, Any]:
    return {
        "event_risk": {
            "type": "choice",
            "instructions": (
                "Using only the supplied point-in-time macro state, classify incremental risk to an "
                "already-selected US long candidate over the next four canonical hourly bars. "
                "A missing consensus means actual-minus-previous must NOT be treated as a forecast surprise."
            ),
            "criteria": {
                "NORMAL": "No material incremental macro/event risk.",
                "CAUTION": "Moderate adverse macro/event risk or meaningful uncertainty; delay could help.",
                "SHOCK": "Strong adverse event/rates shock that could justify avoiding or materially delaying.",
            },
        },
        "execution_timing": {
            "type": "choice",
            "instructions": (
                "Choose execution posture using only macro/event and anonymized backward-looking sensitivity. "
                "Prefer NOW when evidence is insufficient; do not invent a forecast surprise."
            ),
            "criteria": {
                "NOW": "No sufficiently strong macro reason to delay.",
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
                "Is evidence sufficient for a non-neutral overlay? Consider whether consensus is missing, "
                "and the quality/persistence of the empirical intraday rates proxy."
            ),
        },
        "adverse_next_4h": {
            "type": "boolean",
            "instructions": "Is the macro/rates evidence more consistent with adverse than non-adverse conditions over four bars?",
        },
        "supportive_next_4h": {
            "type": "boolean",
            "instructions": "Is the macro/rates evidence more consistent with supportive than non-supportive conditions over four bars?",
        },
        "materiality": {
            "type": "score",
            "instructions": "Rate macro/event materiality for the four-bar decision.",
            "criteria": ["immaterial","low","moderate","high","very high"],
        },
    }

def call_augmented(state: dict[str, Any], api_key: str) -> dict[str, Any]:
    body = json.dumps({"model":MODEL,"state":state,"questions":questions()},separators=(",",":")).encode()
    req = urllib.request.Request(
        ENDPOINT,data=body,
        headers={"Authorization":"Bearer "+api_key,"Content-Type":"application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req,timeout=30) as r:
        return json.loads(r.read().decode())

def family_from_source(source: str, title: str) -> str:
    s=(source or "")
    t=(title or "").lower()
    if s=="bls_employment": return "NFP"
    if s=="bls_cpi": return "CPI"
    if s=="bls_jolts": return "JOLTS"
    if s=="fed_monetary": return "FOMC"
    if s=="bea_releases":
        if "personal income and outlays" in t: return "PCE"
        if "gdp" in t or "gross domestic product" in t: return "GDP"
        if "pce" in t: return "PCE"
    return "OTHER"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--limit",type=int,default=8)
    p.add_argument("--output",default="/home/taehoon/.local/share/kalman-jev-backtest/results/jev_v14_macro_augmented_recent.json")
    args=p.parse_args()

    load_dotenv(os.environ.get("KALMAN_ENV_FILE","/home/taehoon/.config/kalman/jev-shadow.env"),override=True)
    api_key=load_gateway_key({"gateway_key_file":os.environ.get("JEV_GATEWAY_KEY_FILE","/home/taehoon/.config/kalman/secure/jev_gateway_key_create.out")})
    db=os.environ["DATABASE_URL_WRITER"]

    with psycopg.connect(db,row_factory=dict_row,connect_timeout=15) as conn:
        recs=candidate_rows(conn)[:args.limit]
        if not recs:
            raise SystemExit("NO_CANDIDATES")
        dates=[r["as_of"].date() for r in recs]
        cal=fetch_calendar(min(dates)-dt.timedelta(days=1),max(dates)+dt.timedelta(days=1))
        event_cache={}
        out=[]
        for rec in recs:
            family=family_from_source(rec.get("source"),rec.get("title"))
            calrow=match_calendar_event(family,rec["as_of"].date(),cal)
            event_at=None
            if calrow and calrow.get("scheduledAt"):
                event_at=dt.datetime.fromisoformat(str(calrow["scheduledAt"]).replace("Z","+00:00"))
            cache_key=(family,event_at.isoformat() if event_at else None)
            if cache_key not in event_cache:
                event_cache[cache_key]=rate_reaction(event_at) if event_at else {"available":False}
            rate=event_cache[cache_key]

            sens=sensitivity(conn,rec["symbol"],rec["as_of"])
            macro=rec.get("macro_features") or {}
            state={
                "contract":{
                    "experiment":TEST_VERSION,
                    "input_mode":"STRUCTURED_ACTUAL_PLUS_RATE_PROXY",
                    "historical_headline_text_excluded":True,
                    "candidate_identity_blinded":True,
                    "absolute_signal_time_blinded":True,
                    "future_outcome_hidden":True,
                    "baseline_model_score_excluded":True,
                    "live_execution_authority":False,
                    "holding_horizon_bars":4,
                },
                "event":{
                    "family":family,
                    "age_minutes":float(rec["event_age_minutes"]),
                    "scheduled_release_at_known_to_system": event_at.isoformat() if event_at else None,
                    "actual": float(calrow["actual"]) if calrow and calrow.get("actual") is not None else None,
                    "previous": float(calrow["previous"]) if calrow and calrow.get("previous") is not None else None,
                    "unit": calrow.get("unit") if calrow else None,
                    "consensus": None,
                    "consensus_available": False,
                    "actual_minus_previous_is_not_consensus_surprise": True,
                    "actual_source":"XOOMAR_AGENCY_AGGREGATION_RESEARCH_ONLY" if calrow else None,
                    "actual_pit_first_print_audited": False,
                    "daily_us2y_change_bps": macro.get("us2y_change_bps_1d"),
                    "policy_proxy_change_bps_1d": macro.get("policy_proxy_change_bps_1d"),
                    "policy_proxy_spread_bps": macro.get("policy_proxy_spread_bps"),
                },
                "intraday_rates":rate,
                "asset_sensitivity":sens,
            }
            raw=call_augmented(state,api_key)
            ans=raw.get("answers") if isinstance(raw.get("answers"),dict) else {}
            oc=outcomes(conn,rec["symbol"],rec["as_of"])
            row={
                "run_id":rec["run_id"],
                "symbol":rec["symbol"],
                "signal_as_of":rec["as_of"].isoformat(),
                "event_family":family,
                "state":state,
                "event_risk":choice(ans.get("event_risk")),
                "event_risk_probabilities":probs(ans.get("event_risk")),
                "execution_timing":choice(ans.get("execution_timing")),
                "execution_timing_probabilities":probs(ans.get("execution_timing")),
                "exposure_impact":choice(ans.get("exposure_impact")),
                "exposure_impact_probabilities":probs(ans.get("exposure_impact")),
                "evidence_sufficient_probability":bool_prob(ans.get("evidence_sufficient")),
                "adverse_next_4h_probability":bool_prob(ans.get("adverse_next_4h")),
                "supportive_next_4h_probability":bool_prob(ans.get("supportive_next_4h")),
                "materiality_score":score(ans.get("materiality")),
                "confidence":confidence_map(raw),
                "provider_cost":(((raw.get("providerMetadata") or {}).get("gateway") or {}).get("cost")),
                **oc,
            }
            out.append(row)
            print(json.dumps({
                "symbol":row["symbol"],"family":family,
                "actual":state["event"]["actual"],"previous":state["event"]["previous"],
                "rate5":rate.get("implied_us2y_reaction_bps_5m"),
                "rate60":rate.get("implied_us2y_reaction_bps_60m"),
                "risk":row["event_risk"],"timing":row["execution_timing"],
                "evidence":row["evidence_sufficient_probability"],
                "timing_conf":row["confidence"].get("execution_timing"),
                "best":row["hindsight_best"],"qc":row["price_qc_flag"],
            },ensure_ascii=False))

    path=Path(args.output); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    print(json.dumps({"status":"DONE","n":len(out),"output":str(path)}))

if __name__=="__main__":
    main()
