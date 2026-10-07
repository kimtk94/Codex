from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

from engine.jev_shadow_decision_v1 import load_gateway_key
from research.jev_v14_three_arm_recent_test import (
    candidate_rows, sensitivity, outcomes, probs, choice, score, bool_prob, confidence_map,
)
from research.jev_v14_macro_augmented_test import (
    rate_reaction, call_augmented, family_from_source,
)

TEST_VERSION="jev-v1.4-consensus-bundle-recovered-test"

BUNDLES={
    ("GDP","2026-09-30"):{
        "bundle_name":"GDP_PLUS_PCE_SIMULTANEOUS_0830ET",
        "consensus_status":"HISTORICAL_PRE_RELEASE_CONSENSUS_RECOVERED_POST_EVENT_RESEARCH_ONLY",
        "items":[
            {
                "indicator":"GDP_QOQ_FINAL",
                "tier":"CONTEXTUAL",
                "actual":2.2,"consensus":1.5,"unit":"pct_annualized",
                "policy_pressure_surprise":1.4,
                "interpretation":"growth_upside"
            },
            {
                "indicator":"PCE_HEADLINE_YOY",
                "tier":"HIGH",
                "actual":3.4,"consensus":3.7,"unit":"pct_yoy",
                "policy_pressure_surprise":-3.0,
                "interpretation":"inflation_downside"
            },
            {
                "indicator":"CORE_PCE_YOY",
                "tier":"HIGH",
                "actual":3.0,"consensus":3.3,"unit":"pct_yoy",
                "policy_pressure_surprise":-3.0,
                "interpretation":"core_inflation_downside"
            }
        ],
        "bundle_policy_pressure_mean":-1.5333333333333334
    },
    ("NFP","2026-10-02"):{
        "bundle_name":"EMPLOYMENT_SITUATION_0830ET",
        "consensus_status":"HISTORICAL_PRE_RELEASE_CONSENSUS_RECOVERED_POST_EVENT_RESEARCH_ONLY",
        "items":[
            {
                "indicator":"NFP",
                "tier":"HIGH",
                "actual":29.0,"consensus":90.0,"unit":"thousands",
                "policy_pressure_surprise":-1.22,
                "interpretation":"labor_downside"
            },
            {
                "indicator":"UNEMPLOYMENT_RATE",
                "tier":"HIGH",
                "actual":4.2,"consensus":4.1,"unit":"pct",
                "policy_pressure_surprise":-1.0,
                "interpretation":"labor_downside"
            },
            {
                "indicator":"AVERAGE_HOURLY_EARNINGS_MOM",
                "tier":"HIGH",
                "actual":0.1,"consensus":0.3,"unit":"pct_mom",
                "policy_pressure_surprise":-2.0,
                "interpretation":"wage_inflation_downside"
            }
        ],
        "bundle_policy_pressure_mean":-1.4066666666666667
    }
}

EVENT_AT={
    ("GDP","2026-09-30"):"2026-09-30T12:30:00+00:00",
    ("NFP","2026-10-02"):"2026-10-02T12:30:00+00:00",
}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--limit",type=int,default=8)
    p.add_argument("--output",default="/home/taehoon/.local/share/kalman-jev-backtest/results/jev_v14_consensus_bundle_recent.json")
    args=p.parse_args()
    load_dotenv(os.environ.get("KALMAN_ENV_FILE","/home/taehoon/.config/kalman/jev-shadow.env"),override=True)
    api_key=load_gateway_key({"gateway_key_file":os.environ.get("JEV_GATEWAY_KEY_FILE","/home/taehoon/.config/kalman/secure/jev_gateway_key_create.out")})
    db=os.environ["DATABASE_URL_WRITER"]
    import datetime as dt
    cache={}
    out=[]
    with psycopg.connect(db,row_factory=dict_row,connect_timeout=15) as conn:
        for rec in candidate_rows(conn)[:args.limit]:
            fam=family_from_source(rec.get("source"),rec.get("title"))
            key=(fam,rec["as_of"].date().isoformat())
            bundle=BUNDLES.get(key)
            event_at=dt.datetime.fromisoformat(EVENT_AT[key]) if key in EVENT_AT else None
            if key not in cache:
                cache[key]=rate_reaction(event_at) if event_at else {"available":False}
            rate=cache[key]
            sens=sensitivity(conn,rec["symbol"],rec["as_of"])
            macro=rec.get("macro_features") or {}
            state={
                "contract":{
                    "experiment":TEST_VERSION,
                    "input_mode":"RECOVERED_CONSENSUS_BUNDLE_PLUS_RATE_PROXY",
                    "historical_headline_text_excluded":True,
                    "candidate_identity_blinded":True,
                    "absolute_signal_time_blinded":True,
                    "future_outcome_hidden":True,
                    "baseline_model_score_excluded":True,
                    "live_execution_authority":False,
                    "holding_horizon_bars":4,
                    "historical_consensus_recovered_post_event":True,
                    "not_eligible_for_live_or_canonical_backtest":True,
                },
                "event":{
                    "family":fam,
                    "age_minutes":float(rec["event_age_minutes"]),
                    "bundle":bundle,
                    "daily_us2y_change_bps":macro.get("us2y_change_bps_1d"),
                    "policy_proxy_change_bps_1d":macro.get("policy_proxy_change_bps_1d"),
                    "policy_proxy_spread_bps":macro.get("policy_proxy_spread_bps"),
                },
                "intraday_rates":rate,
                "asset_sensitivity":sens,
            }
            raw=call_augmented(state,api_key)
            ans=raw.get("answers") if isinstance(raw.get("answers"),dict) else {}
            oc=outcomes(conn,rec["symbol"],rec["as_of"])
            row={
                "run_id":rec["run_id"],"symbol":rec["symbol"],"signal_as_of":rec["as_of"].isoformat(),
                "event_family":fam,"state":state,
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
                "symbol":row["symbol"],"family":fam,
                "bundle_pressure":bundle.get("bundle_policy_pressure_mean") if bundle else None,
                "rate5":rate.get("implied_us2y_reaction_bps_5m"),
                "rate60":rate.get("implied_us2y_reaction_bps_60m"),
                "risk":row["event_risk"],"timing":row["execution_timing"],
                "impact":row["exposure_impact"],
                "evidence":row["evidence_sufficient_probability"],
                "timing_conf":row["confidence"].get("execution_timing"),
                "risk_conf":row["confidence"].get("event_risk"),
                "best":row["hindsight_best"],"qc":row["price_qc_flag"],
                "friday":row["friday_signal_utc"],
            },ensure_ascii=False))
    path=Path(args.output); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
    print(json.dumps({"status":"DONE","n":len(out),"output":str(path)}))

if __name__=="__main__":
    main()
