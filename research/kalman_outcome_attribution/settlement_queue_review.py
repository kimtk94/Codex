"""Read-only independent reconciliation of paired frozen market and result ZIPs.

No evidence is promoted. Verify journal ancestry, timing, original price/cost
arithmetic, current vendor marks, and exact agreement with the published queue.
A changed price is a HOLD, never an instruction to replace a settlement.
"""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import io
import json
import math
from pathlib import Path

import pandas as pd

from prospective_gate_readiness import (
    CORE, FAMILIES, JOURNALS, ANCHOR_SHA, PROTOCOL, sha, require, verified_zip,
    verify_ancestry, journal_index, sessions, verify_timing,
)

PREFIX = "research/forward_settlement_integrity/"
COLS = (
    "signal_date","symbol","family","candidate_at_signal_time","entry_date","exit_date",
    "state","original_signal_hash","original_settlement_hash","recorded_at_utc",
    "cost_20bp_net_return","price_revision_detected","price_revision_issues",
)
CLEAN = "SETTLED_ARITHMETIC_VERIFIED_RESEARCH_ONLY"
REVISED = "SETTLED_VENDOR_HISTORY_REVISED_HOLD"
PENDING = "PENDING_UNMATURED_4_XNYS_SESSIONS"


def pair_manifest(data, results):
    require({k:v for k,v in data.items() if k!="payload_hashes_sha256"} ==
            {k:v for k,v in results.items() if k!="payload_hashes_sha256"},
            "MARKET_RESULTS_CAPTURE_MISMATCH")


def frame_reader(payload, symbol):
    require(symbol in CORE,"UNKNOWN_PRICE_SYMBOL")
    name="market/raw/yfinance/yf_"+symbol.lower()+".parquet"
    p=pd.read_parquet(io.BytesIO(payload[name]),engine="pyarrow",
                      columns=["timestamp","open","high","low","close"])
    p["date"]=pd.to_datetime(p.timestamp,utc=True,errors="raise").dt.tz_localize(None).dt.normalize()
    require(p.date.notna().all() and not p.date.duplicated().any(),"MARKET_DATE_INVALID")
    return p.set_index("date").sort_index()


def price_revision_issues(event, bars, calendar_window):
    d=pd.DatetimeIndex([pd.Timestamp(s.date()) for s in calendar_window])
    require(d.isin(bars.index).all(),"CURRENT_MARKET_WINDOW_INCOMPLETE")
    w=bars.loc[d,["open","high","low","close"]]
    require(all(math.isfinite(float(v)) and float(v)>0 for v in w.to_numpy().ravel())
            and w.high.ge(w[["open","close","low"]].max(axis=1)-1e-7).all()
            and w.low.le(w[["open","close","high"]].min(axis=1)+1e-7).all(),
            "CURRENT_MARKET_WINDOW_INVALID")
    entry=float(w.open.iloc[1]);exit_=float(w.close.iloc[4])
    current={"entry_open":entry,"exit_close":exit_,"gross_return":exit_/entry-1,
             "next_open_gap_return":entry/float(w.close.iloc[0])-1,
             "worst_four_session_low_vs_entry":float(w.low.iloc[1:].min())/entry-1}
    issues=[]
    for name,v in current.items():
        old=event.get(name)
        require(type(old) in (int,float) and math.isfinite(old),"ORIGINAL_MARK_INVALID:"+name)
        if not math.isclose(old,v,rel_tol=0,abs_tol=1e-7 if name in ("entry_open","exit_close") else 1e-9):
            issues.append(name)
    return issues


def queue_row(key,signal,settled,asof,calendar,read_prices):
    day,symbol,family=key
    require(signal.get("horizon_us_sessions")==4,"ORIGINAL_HORIZON_CHANGED")
    timing=verify_timing(calendar,day,asof,signal,settled)
    require(timing!="OVERDUE_MISSING_SETTLEMENT","MATURED_SIGNAL_WITHOUT_SETTLEMENT")
    window=sessions(calendar,day)
    issues=[]
    if settled is not None:
        require(settled.get("model_positive_probability_frozen")==signal.get("probability"),
                "ORIGINAL_SCORE_LINK_CHANGED")
        issues=price_revision_issues(settled,read_prices(symbol),window)
    return {"signal_date":day,"symbol":symbol,"family":family,
            "candidate_at_signal_time":signal["candidate"],
            "entry_date":str(window[1].date()),"exit_date":str(window[4].date()),
            "state":(REVISED if issues else CLEAN) if settled is not None else PENDING,
            "original_signal_hash":signal["hash"],
            "original_settlement_hash":settled["hash"] if settled is not None else None,
            "recorded_at_utc":settled["recorded_at_utc"] if settled is not None else None,
            "cost_20bp_net_return":settled["net_return_by_cost_bp"]["20"] if settled is not None else None,
            "price_revision_detected":bool(issues),"price_revision_issues":issues}


def compare_queue(rows,report,table):
    require(report.get("observations")==rows,"RECOMPUTED_JSON_QUEUE_MISMATCH")
    require(report.get("settlement_queue_csv_sha256")==sha(table),"QUEUE_CSV_DIGEST_MISMATCH")
    reader=csv.DictReader(io.StringIO(table.decode("utf-8"),newline=""))
    require(tuple(reader.fieldnames or ())==COLS,"QUEUE_CSV_SCHEMA_MISMATCH")
    actual=list(reader)
    expected=[{c:json.dumps(r[c]) if c=="price_revision_issues" else
                 "" if r[c] is None else str(r[c]) for c in COLS} for r in rows]
    require(actual==expected,"RECOMPUTED_CSV_QUEUE_MISMATCH")
    settled=[r for r in rows if r["state"]!=PENDING]
    counts={"signal_count":len(rows),
            "bull_signals":sum(r["family"]=="BULL_LOGISTIC" for r in rows),
            "bear_signals":sum(r["family"]!="BULL_LOGISTIC" for r in rows),
            "settled_events":len(settled),"pending_unmatured":len(rows)-len(settled),
            "settled_arithmetic_verified":sum(r["state"]==CLEAN for r in rows),
            "settled_vendor_price_revisions":sum(r["state"]==REVISED for r in rows),
            "candidate_settlements":sum(r["candidate_at_signal_time"] for r in settled),
            "first_unsettled_exit_date":min((r["exit_date"] for r in rows if r["state"]==PENDING),default=None)}
    require(all(report.get(k)==v for k,v in counts.items()),"PUBLISHED_QUEUE_COUNTS_MISMATCH")
    return counts


def review(data_path,data_sha,result_path,result_sha,anchor_path):
    import exchange_calendars as xc
    calendar=xc.get_calendar("XNYS",start="2026-01-01",end="2028-02-01")
    _,dm,data=verified_zip(data_path,data_sha)
    _,rm,result=verified_zip(result_path,result_sha)
    pair_manifest(dm,rm)
    _,_,anchor=verified_zip(anchor_path,ANCHOR_SHA)
    verify_ancestry(anchor,result)
    day=rm["data_expected_last_closed_xnys"]
    qc=json.loads(result["qc.json"])
    require(qc.get("status")=="READY" and qc.get("expected_session")==day
            and qc.get("ready")==qc.get("required")==26,"MARKET_QC_INCOMPLETE")
    report=json.loads(result[PREFIX+"report.json"])
    require(report.get("session")==day and report.get("research_only") is True
            and report.get("production_writes") is False
            and report.get("live_execution") is False
            and report.get("settlement_is_observation_not_executed_trade") is True
            and report.get("actual_forward_outcomes_approved_for_attribution") is False
            and report.get("round_trip_cost_grid_bps")==[20,40,80]
            and report.get("holding_period_subsequent_xnys_sessions")==4,
            "SETTLEMENT_REPORT_SCOPE_INVALID")
    require(report.get("source_digests")=={
        "bull_journal_sha256":sha(result[JOURNALS["BULL"]]),
        "bear_journal_sha256":sha(result[JOURNALS["BEAR"]]),
        "qc_sha256":sha(result["qc.json"])},
        "PUBLISHED_SOURCE_DIGEST_MISMATCH")
    finality=result["research/source_finality/report.json"]
    require(sha(finality)==rm["source_finality_evidence_sha256"],"SOURCE_REPORT_DIGEST_MISMATCH")
    sf=json.loads(finality)
    require(sf.get("session")==day and sf.get("required")==26
            and sf.get("verified")==rm.get("source_finality_verified_assets")
            and sf.get("status")==rm.get("source_finality_status"),
            "SOURCE_REPORT_SCOPE_MISMATCH")
    signals,settled,days=journal_index(result,day)
    cache={}
    def read_prices(symbol):
        if symbol not in cache:
            cache[symbol]=frame_reader(data,symbol)
        return cache[symbol]
    keys=sorted(signals,key=lambda k:(k[0],k[1],FAMILIES.index(k[2])))
    rows=[queue_row(k,signals[k],settled.get(k),day,calendar,read_prices) for k in keys]
    counts=compare_queue(rows,report,result[PREFIX+"settlement_queue.csv"])
    maturity=Counter((r["signal_date"],r["exit_date"],r["state"]) for r in rows)
    return {"schema":"kalman-settlement-reconciliation-v1","protocol":PROTOCOL,
            "asof":day,"source_run":rm["source_actions_run_id"],"data_sha256":data_sha,
            "results_sha256":result_sha,"data_members":len(data),"results_members":len(result),
            "anchor_preserved":True,"paired_capture_verified":True,"json_csv_journal_reconciled":True,
            **counts,"settled_price_frames_read":len(cache),
            "maturity":[{"signal_date":d,"exit_date":e,"state":s,"count":n}
                        for (d,e,s),n in sorted(maturity.items())],
            "reported_source_verified_assets":sf["verified"],"independent_price_certification":False,
            "primary_study_admitted_outcomes":0,"research_only":True,
            "approved_live":False,"production_writes":False,
            "limitations":["No price-window comparison if no settled observations exist.",
                "Original and current archive marks may share the same vendor; agreement is not independent certification.",
                "No inference, model promotion, order execution or replacement of original settlements."]}


if __name__=="__main__":
    p=argparse.ArgumentParser()
    for n in ("data","data-sha256","results","results-sha256","anchor","out"):
        p.add_argument("--"+n,required=True)
    a=p.parse_args()
    report=review(a.data,a.data_sha256,a.results,a.results_sha256,a.anchor)
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print("SETTLEMENT_RECONCILIATION_RESEARCH_ONLY",report["signal_count"],report["settled_events"],
          report["settled_vendor_price_revisions"])
