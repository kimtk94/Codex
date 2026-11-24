#!/usr/bin/env python3
"""Read-only prospective challenger protocol and evidence verifier.

No forecast publication, credentials, provider authentication, execution engine,
or historic backfill. Independent source retrieval and cash-ledger verification
are still mandatory. A hash chain alone cannot prove a historical timestamp.
"""
import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re

import exchange_calendars as xc
import numpy as np
import pandas as pd

ROOT = "0"*64
PROTOCOL_PATH = Path(__file__).with_name("challenger_prequential_protocol.json")
CUTOFF = "2026-11-23"
LOOKS = (126, 252, 504)
ALPHA = {126: 0, 252: .02, 504: .03}
REPS = 10000
SEED = 2601121
BLOCK = 20
ANCHOR_KINDS = {"PROTECTED_ACTIONS_ARTIFACT", "DRIVE_REVISION"}
SCENARIOS = tuple(f"{c}_{b}_{f}" for c in (20,16) for b in (30,50)
                  for f in ("K1", "K3", "K1+K3"))
PRIMARY = "20_30_K1+K3"
CONTROL = "20_30_K1"


def require(ok, code):
    if not ok:
        raise ValueError("PREQUENTIAL_"+code)


def unique_object(items):
    d = {}
    for k, v in items:
        require(k not in d, "DUPLICATE_JSON_KEY")
        d[k] = v
    return d


def parse(text):
    return json.loads(text, object_pairs_hook=unique_object,
                      parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest_ok(v, length=64):
    return isinstance(v, str) and re.fullmatch("[0-9a-f]{%d}" % length, v) is not None


def event_hash(event):
    return sha(canonical({k:v for k,v in event.items() if k!="hash"}))


def utc(v):
    t = pd.Timestamp(v)
    require(pd.notna(t) and t.tzinfo is not None, "UTC_TIMESTAMP_REQUIRED")
    return t.tz_convert("UTC")


def number(v):
    return type(v) in (int,float) and math.isfinite(v)


def session_text(v):
    require(isinstance(v, str), "SESSION_TYPE")
    d = date.fromisoformat(v)
    require(d.isoformat()==v, "SESSION_FORMAT")
    return d


def load_protocol(path=PROTOCOL_PATH):
    raw = Path(path).read_bytes()
    p = parse(raw)
    require(p["version"]=="kalman-challenger-prequential-v1"
            and p["research_only"] is True and p["approved_live"] is False
            and p["source_finality_certified"] is False
            and p["retrospective_cutoff_session"]==CUTOFF
            and len(p["universe"])==len(set(p["universe"]))==20
            and len(p["excluded_16"])==4
            and set(p["excluded_16"]).issubset(p["universe"])
            and p["families"]==["K1","K3","K1+K3"]
            and p["cohorts"]==[20,16] and p["cost_bps"]==[30,50]
            and p["initial_equity"]==100000
            and p["primary"]["candidate"]==PRIMARY
            and p["primary"]["comparator"]==CONTROL
            and p["primary"]["looks"]==list(LOOKS)
            and p["primary"]["alpha_by_look"]=={str(k):v for k,v in ALPHA.items()}
            and p["primary"]["min_active_nonoverlap_four_session_groups"]==20
            and p["primary"]["min_active_calendar_months"]==8
            and p["primary"]["formal_promotion"] is False,
            "PROTOCOL_MISMATCH")
    ex=p["execution"]
    require((ex["stop_atr"],ex["target_atr"],ex["min_net_rr"],ex["min_stop"],
             ex["max_stop"],ex["max_target"],ex["max_hold_sessions"],
             ex["max_reserved_slots"],ex["allocation_per_slot"])==
            (.75,2.25,2,.005,.03,.08,4,5,.2), "RISK_PROTOCOL_MISMATCH")
    return p,sha(raw)


def classify(m):
    require(set(m)=={"spy_above_sma200","spy_ret20","spy_ret5","vix"}
            and type(m["spy_above_sma200"]) is bool
            and all(number(m[k]) for k in ("spy_ret20","spy_ret5","vix"))
            and m["vix"]>0, "MISSING_OR_INVALID_MARKET_CONTEXT")
    above=m["spy_above_sma200"]
    if above and m["spy_ret20"]>.02:
        return "UP_TREND" if m["spy_ret5"]>0 else "UP_PULLBACK"
    if not above and m["spy_ret20"]<-.02:
        return "DOWN_REBOUND" if m["spy_ret5"]>0 else "DOWN_TREND"
    return "SIDE_LOW" if m["vix"]<20 else "SIDE_HIGH"


def plans(p, m, mom, atr, idx, last):
    require(set(mom)==set(atr)==set(p["universe"])
            and all(number(v) for v in mom.values())
            and all(number(v) and v>0 for v in atr.values()),
            "INCOMPLETE_FROZEN_FEATURES")
    regime=classify(m)
    eligible={"K1":regime=="UP_PULLBACK",
              "K3":regime=="SIDE_HIGH" and m["spy_above_sma200"]}
    result={}
    for f in ("K1","K3"):
        cycle=eligible[f] and (f not in last or idx-last[f]>=4)
        if cycle:
            last[f]=idx
        for n in (20,16):
            names=[s for s in p["universe"] if n==20 or s not in p["excluded_16"]]
            result[f"{n}_{f}"]=(sorted(names,key=lambda s:(-mom[s],s))[:5]
                                if cycle else [])
    return regime,result


def metrics(equity):
    values=np.asarray([100000.,*equity],float)
    returns=values[1:]/values[:-1]-1
    peak=np.maximum.accumulate(values)
    sd=returns.std(ddof=1) if len(returns)>1 else 0
    return returns,dict(total_return=float(values[-1]/values[0]-1),
                         eod_mdd=float((values/peak-1).min()),
                         annualized_sharpe_zero_rate=(float(returns.mean()/sd*np.sqrt(252))
                                                     if sd>1e-14 else None))


def paired_p(d):
    mean=float(d.mean())
    if d.std(ddof=1)<=1e-14:
        return 1.0 if mean==0 else None
    rng=np.random.default_rng(SEED+len(d))
    x=d-mean
    hits=0
    for i in range(0,REPS,128):
        n=min(128,REPS-i)
        starts=rng.integers(0,len(d),size=(n,(len(d)+BLOCK-1)//BLOCK))
        ix=((starts[:,:,None]+np.arange(BLOCK))%len(d)).reshape(n,-1)[:,:len(d)]
        hits+=int((np.abs(x[ix].mean(axis=1))>=abs(mean)).sum())
    return (hits+1)/(REPS+1)


def audit(p, protocol_hash, events, anchors, asof):
    asof=utc(asof)
    require(isinstance(events,list) and events and isinstance(anchors,dict),
            "ACTIVATION_EVIDENCE_REQUIRED")
    require(all(isinstance(e,dict) for e in events), "EVENT_TYPE")
    require(len({e.get("hash") for e in events})==len(events)
            and set(anchors)=={e.get("hash") for e in events}, "ANCHOR_SET_MISMATCH")
    calendar=xc.get_calendar("XNYS")
    first_event=events[0]
    require(first_event.get("kind")=="ACTIVATE", "ACTIVATION_FIRST")
    start=session_text(first_event["session"])
    require(str(start)>CUTOFF, "RETROACTIVE_START")
    # Include the preceding session and enough future sessions for maturity.
    lo=start-timedelta(days=35)
    hi=max(start+timedelta(days=35),asof.date()+timedelta(days=35))
    sessions=calendar.sessions_in_range(lo.isoformat(),hi.isoformat())
    names=[str(s.date()) for s in sessions]
    lookup={s:i for i,s in enumerate(names)}
    require(str(start) in lookup, "START_NOT_XNYS")
    begin=lookup[str(start)]
    def opening(i):
        return utc(calendar.session_open(sessions[i]))
    def closed(i):
        return utc(calendar.session_close(sessions[i]))+pd.Timedelta(minutes=45)
    # Anchor timestamps must come from a separately retrieved immutable index.
    # This reader checks consistency but cannot authenticate the index's origin.
    last_anchor=None
    parent=ROOT
    signals,marks,settled,gaps,last={},{},{},{},{}
    code_sha=first_event.get("code_sha")
    require(digest_ok(code_sha,40), "ACTIVATION_CODE_SHA")
    for seq,e in enumerate(events,1):
        require(type(e.get("seq")) is int and e["seq"]==seq
                and e.get("prev_hash")==parent and e.get("hash")==event_hash(e)
                and e.get("protocol_sha256")==protocol_hash
                and e.get("research_only") is True
                and e.get("approved_live") is False
                and e.get("code_sha")==code_sha, "CHAIN_OR_PROTOCOL_BROKEN")
        parent=e["hash"]
        a=anchors[parent]
        require(isinstance(a,dict) and set(a)=={"kind","anchor_id","published_at_utc"}
                and a["kind"] in ANCHOR_KINDS
                and isinstance(a["anchor_id"],str) and bool(a["anchor_id"].strip()),
                "EXTERNAL_ANCHOR_FIELDS")
        recorded, published=utc(e["recorded_at_utc"]),utc(a["published_at_utc"])
        require(recorded<=published<=asof
                and (last_anchor is None or last_anchor<=published),
                "ANCHOR_TIME_ORDER")
        last_anchor=published
        s=e["session"]
        session_text(s)
        require(s in lookup and lookup[s]>=begin, "NOT_PROSPECTIVE_XNYS")
        i=lookup[s]
        kind=e["kind"]
        if kind=="ACTIVATE":
            require(seq==1 and i==begin and opening(i-1)<=published<opening(i)
                    and recorded>=opening(i-1), "ACTIVATION_NOT_BEFORE_FIRST_OPEN")
            require(digest_ok(e.get("review_evidence_sha256")), "REVIEW_EVIDENCE_ABSENT")
            continue
        require(seq>1 and digest_ok(e.get("evidence_sha256")),
                "EVIDENCE_HASH_ABSENT")
        if kind=="SIGNAL":
            require(s not in signals and not gaps
                    and i==begin+len(signals), "SIGNAL_MISSING_OR_REPLAY")
            require(closed(i)<=recorded<=published<opening(i+1),
                    "SIGNAL_NOT_ANCHORED_BEFORE_ENTRY")
            require(e.get("context_session")==names[i-1],
                    "CONTEXT_NOT_PRIOR_SESSION")
            r,expected=plans(p,e["market"],e["mom20"],e["atr14"],i,last)
            require(e.get("regime")==r and e.get("plans")==expected,
                    "FROZEN_RANKING_OR_CYCLE_CHANGED")
            signals[s]=e
        elif kind=="GAP":
            require(s not in signals and not gaps and i==begin+len(signals)
                    and recorded>=opening(i+1)
                    and isinstance(e.get("reason"),str) and e["reason"].strip(),
                    "GAP_INVALID")
            gaps[s]=e
        elif kind=="MARK":
            require(s in signals and s not in marks and i==begin+len(marks),
                    "MARK_MISSING_OR_DUPLICATE")
            require(e.get("signal_hash")==signals[s]["hash"]
                    and closed(i)<=recorded<=published<opening(i+1),
                    "MARK_TIMING_OR_LINK")
            eq=e["equity"]
            require(set(eq)==set(SCENARIOS) and all(number(v) and v>0 for v in eq.values()),
                    "MARK_EQUITY_INVALID")
            if i==begin:
                require(all(v==p["initial_equity"] for v in eq.values()),
                        "UNDECLARED_STARTING_POSITIONS")
            marks[s]=e
        elif kind=="SETTLED":
            require(s in signals and s not in settled
                    and e.get("signal_hash")==signals[s]["hash"], "SETTLEMENT_LINK")
            require(e.get("entry_session")==names[i+1]
                    and e.get("fourth_session")==names[i+4]
                    and closed(i+4)<=recorded<=published<opening(i+5),
                    "SETTLEMENT_PREMATURE_OR_LATE")
            status=e["status"]
            counts=e.get("primary_executed_slots")
            if status=="COMPLETE":
                require(isinstance(counts,dict) and set(counts)=={PRIMARY,CONTROL}
                        and all(type(v) is int and 0<=v<=5 for v in counts.values()),
                        "SETTLEMENT_COUNTS")
                plan=signals[s]["plans"]
                require(counts[CONTROL]<=len(plan["20_K1"])
                        and counts[PRIMARY]<=len(plan["20_K1"])+len(plan["20_K3"]),
                        "EXECUTION_WITHOUT_FROZEN_PLAN")
            else:
                require(status=="MISSING_DATA" and counts is None,
                        "MISSING_DATA_MUST_NOT_BECOME_ZERO")
            settled[s]=e
        else:
            raise ValueError("PREQUENTIAL_UNKNOWN_EVENT_KIND")
    due_signals=[s for s in names[begin:] if lookup[s]+1<len(names)
                 and opening(lookup[s]+1)<=asof]
    due_settled=[s for s in signals if lookup[s]+5<len(names)
                 and opening(lookup[s]+5)<=asof]
    missing_signals=[s for s in due_signals if s not in signals]
    missing_marks=[s for s in due_signals if s not in marks]
    missing_settlements=[s for s in due_settled if s not in settled]
    invalid_outcomes=[s for s,e in settled.items() if e["status"]!="COMPLETE"]
    # Evaluate only the contiguous complete prefix; missing is not zero return.
    prefix=[]
    for s in names[begin:]:
        if s not in signals or s not in marks or s not in settled or settled[s]["status"]!="COMPLETE":
            break
        prefix.append(s)
    results=[]
    for look in LOOKS:
        result=dict(look_sessions=look,alpha=ALPHA[look],
                    complete_prefix_sessions=len(prefix),
                    formal_status="HOLD_EXTERNAL_SOURCE_LEDGER_AND_ANCHOR_VERIFICATION")
        if len(prefix)<look:
            result.update(status="NOT_MATURED_OR_INCOMPLETE",diagnostic_p=None)
        else:
            sample=prefix[:look]
            stats={}
            series={}
            for name in SCENARIOS:
                series[name],stats[name]=metrics([marks[s]["equity"][name] for s in sample])
            d=series[PRIMARY]-series[CONTROL]
            groups=[]
            for s in sample:
                if max(settled[s]["primary_executed_slots"].values())>0 and (
                    not groups or lookup[s]-lookup[groups[-1]]>=4):
                    groups.append(s)
            months=len({s[:7] for s in groups})
            eligible=look!=126 and len(groups)>=20 and months>=8
            prob=paired_p(d) if eligible else None
            result.update(status=("CONDITIONAL_DIAGNOSTIC_ONLY" if eligible
                                  else "DESCRIPTIVE_ONLY"),stats=stats,
                          mean_paired_difference_bp_day=float(d.mean()*10000),
                          active_nonoverlap_groups=len(groups),active_months=months,
                          diagnostic_p=prob,
                          conditional_threshold_pass=bool(prob is not None and
                                                          prob<=ALPHA[look] and d.mean()>0))
        results.append(result)
    return dict(version=p["version"],protocol_sha256=protocol_hash,
                status="RESEARCH_HOLD",research_only=True,approved_live=False,
                independently_authenticated_anchors=False,source_finality_certified=False,
                ledger_reexecuted=False,forward_validated=False,
                first_session=str(start),sealed_sessions=len(signals),marks=len(marks),
                settled_sessions=len(settled),complete_prefix_sessions=len(prefix),
                missing_signals=missing_signals,missing_marks=missing_marks,
                missing_settlements=missing_settlements,missing_data_outcomes=invalid_outcomes,
                explicit_gaps=list(gaps),fixed_looks=results,
                limitations=["External anchor index origin and input evidence require independent verification.",
                             "Marks and settlement counts are externally supplied; no fill or ledger re-execution.",
                             "No matched-exposure benchmark yet; conditional p-values are not approval.",
                             "K2 needs a separate frozen protocol; not evaluated here."])


def self_test():
    p,h=load_protocol()
    cal=xc.get_calendar("XNYS")
    dates=cal.sessions_in_range("2026-11-23","2026-12-04")
    ss=[str(x.date()) for x in dates]
    require("2026-11-26" not in ss and ss[1:6]==
            ["2026-11-24","2026-11-25","2026-11-27","2026-11-30","2026-12-01"],
            "HOLIDAY_FIXTURE")
    require(utc(cal.session_close(dates[3])).hour==18,"EARLY_CLOSE_FIXTURE")
    mom={s:float(i)/100 for i,s in enumerate(p["universe"])}
    atr={s:1.0 for s in p["universe"]}
    market=dict(spy_above_sma200=True,spy_ret20=.03,spy_ret5=-.01,vix=24.)
    clocks={}
    regime,selected=plans(p,market,mom,atr,1,clocks)
    require(regime=="UP_PULLBACK" and len(selected["20_K1"])==5
            and not selected["20_K3"],"RANK_FIXTURE")
    require(not plans(p,market,mom,atr,2,clocks)[1]["20_K1"],"COOLDOWN_FIXTURE")
    require(len(plans(p,market,mom,atr,5,clocks)[1]["20_K1"])==5,"FOURTH_CLOSE_FIXTURE")
    side=dict(market,spy_ret20=.01)
    require(plans(p,side,mom,atr,5,{})[1]["20_K3"]!=[],"K3_FIXTURE")
    events,anchors=[],{}
    def append(kind,s,stamp,**kw):
        e=dict(seq=len(events)+1,prev_hash=events[-1]["hash"] if events else ROOT,
               kind=kind,session=s,recorded_at_utc=stamp,protocol_sha256=h,
               research_only=True,approved_live=False,code_sha="a"*40,**kw)
        e["hash"]=event_hash(e)
        events.append(e)
        anchors[e["hash"]]=dict(kind="PROTECTED_ACTIONS_ARTIFACT",
                                  anchor_id="SYNTHETIC_TEST_ONLY",published_at_utc=stamp)
        return e
    append("ACTIVATE","2026-11-24","2026-11-24T12:00:00Z",
           review_evidence_sha256="b"*64)
    signal=append("SIGNAL","2026-11-24","2026-11-24T22:00:00Z",
                  context_session="2026-11-23",market=market,mom20=mom,atr14=atr,
                  regime=regime,plans=selected,evidence_sha256="c"*64)
    append("MARK","2026-11-24","2026-11-24T22:01:00Z",
           signal_hash=signal["hash"],equity={x:100000 for x in SCENARIOS},
           evidence_sha256="d"*64)
    report=audit(p,h,events,anchors,"2026-11-25T12:00:00Z")
    require(report["complete_prefix_sessions"]==0 and report["sealed_sessions"]==1
            and all(r["diagnostic_p"] is None for r in report["fixed_looks"]),
            "PENDING_MUST_NOT_SCORE")
    append("SETTLED","2026-11-24","2026-11-27T19:00:00Z",
           signal_hash=signal["hash"],entry_session="2026-11-25",
           fourth_session="2026-12-01",status="COMPLETE",
           primary_executed_slots={PRIMARY:1,CONTROL:1},evidence_sha256="e"*64)
    def reject(code,fn):
        try:
            fn()
        except ValueError as ex:
            require(str(ex)=="PREQUENTIAL_"+code,"WRONG_REJECTION:"+str(ex))
        else:
            raise AssertionError("EXPECTED_REJECTION:"+code)
    reject("SETTLEMENT_PREMATURE_OR_LATE",
           lambda:audit(p,h,events,anchors,"2026-11-27T20:00:00Z"))
    a=events.pop()
    anchors.pop(a["hash"])
    append("SETTLED","2026-11-24","2026-12-01T22:00:00Z",
           signal_hash=signal["hash"],entry_session="2026-11-25",
           fourth_session="2026-12-01",status="COMPLETE",
           primary_executed_slots={PRIMARY:1,CONTROL:1},evidence_sha256="e"*64)
    report=audit(p,h,events,anchors,"2026-12-02T12:00:00Z")
    require(report["complete_prefix_sessions"]==1 and report["missing_signals"]
            and report["approved_live"] is False,"GAP_NOT_ZERO")
    copy=json.loads(json.dumps(anchors))
    copy[signal["hash"]]["published_at_utc"]="2026-11-25T15:00:00Z"
    reject("SIGNAL_NOT_ANCHORED_BEFORE_ENTRY",
           lambda:audit(p,h,events,copy,"2026-12-02T12:00:00Z"))
    events[1]["mom20"]["SPY"]=999
    reject("CHAIN_OR_PROTOCOL_BROKEN",
           lambda:audit(p,h,events,anchors,"2026-12-02T12:00:00Z"))
    require(paired_p(np.zeros(252))==1.0,"NULL_P_TEST")
    print("CHALLENGER_PREQUENTIAL_SYNTHETIC_SELF_TEST_PASS")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--journal")
    parser.add_argument("--journal-sha256")
    parser.add_argument("--anchors")
    parser.add_argument("--anchors-sha256")
    parser.add_argument("--out")
    args=parser.parse_args()
    if args.self_test:
        self_test()
        return
    require(all([args.journal,args.journal_sha256,args.anchors,args.anchors_sha256,args.out]),
            "ARGUMENTS_REQUIRED")
    jr,ar=Path(args.journal).read_bytes(),Path(args.anchors).read_bytes()
    require(sha(jr)==args.journal_sha256 and sha(ar)==args.anchors_sha256,
            "PINNED_INPUT_HASH_MISMATCH")
    p,h=load_protocol()
    result=audit(p,h,[parse(x) for x in jr.splitlines() if x.strip()],
                 parse(ar),datetime.now(timezone.utc).isoformat())
    result.update(journal_sha256=sha(jr),anchors_sha256=sha(ar))
    out=Path(args.out)
    require(not out.exists(),"OUTPUT_MUST_BE_NEW")
    out.mkdir(parents=True)
    (out/"prequential_report.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps({k:result[k] for k in ("status","sealed_sessions",
                                           "settled_sessions","complete_prefix_sessions")}))


if __name__=="__main__":
    main()
