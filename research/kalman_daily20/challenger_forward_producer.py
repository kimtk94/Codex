#!/usr/bin/env python3
"""K1/K3 daily data producer and cash-ledger replay, RESEARCH ONLY.

Rehearse immutable historical archives without creating events. Stage current
prospective event proposals only after a separately anchored ACTIVATE and a
complete prior journal/evidence prefix. Never publish/anchor, overwrite prior
files, schedule, use broker credentials or send orders. OHLC-open fills are
historical feasibility proxies, not executable quotes.
"""
import argparse
from datetime import datetime, timedelta, timezone
import io
import json
import subprocess
import tempfile
from unittest.mock import patch
from pathlib import Path
import zipfile

import exchange_calendars as xc
import numpy as np
import pandas as pd

from challenger_prequential import (
    ROOT, SCENARIOS, PRIMARY, CONTROL, audit, canonical, digest_ok,
    event_hash, load_protocol, metrics, parse, plans, require, sha, utc,
)

VERSION = "kalman-challenger-producer-v1"
RAW_CONTEXT = ("SMH", "^VIX", "HYG", "LQD", "TLT", "GLD")
OHLC = ["open", "high", "low", "close"]
SEED_START = "2024-01-02"


def pinned(path, expected):
    raw = Path(path).read_bytes()
    require(digest_ok(expected) and sha(raw) == expected, "PRODUCER_PIN_MISMATCH")
    return raw


def safe_zip(raw):
    z = zipfile.ZipFile(io.BytesIO(raw))
    names = z.namelist()
    require(len(set(names)) == len(names)
            and all(not n.startswith("/") and "\\" not in n
                    and ".." not in Path(n).parts for n in names)
            and z.testzip() is None, "PRODUCER_ZIP_INTEGRITY")
    return z


def archive_frames(p, data, research):
    with safe_zip(research) as z:
        q = parse(z.read("qc.json"))
    require(q.get("status")=="READY" and q.get("required")==q.get("ready")==26
            and q.get("research_only") is True, "PRODUCER_QC_26_REQUIRED")
    session=q["expected_session"]
    symbols=p["universe"]+list(RAW_CONTEXT)
    require(len(set(symbols))==26, "PRODUCER_UNIVERSE_26")
    frames={}
    with safe_zip(data) as z:
        slug=lambda s:s.lstrip("^").lower()
        expected={f"market/raw/yfinance/yf_{slug(s)}.parquet" for s in symbols}
        expected|={f"features/talib/{slug(s)}.parquet" for s in symbols}
        require(set(z.namelist())==expected, "PRODUCER_ARCHIVE_SCHEMA")
        for s in p["universe"]+["^VIX"]:
            path=f"market/raw/yfinance/yf_{slug(s)}.parquet"
            f=pd.read_parquet(io.BytesIO(z.read(path)))
            require(set(["timestamp",*OHLC]).issubset(f.columns),
                    "PRODUCER_OHLC_SCHEMA")
            idx=pd.to_datetime(f["timestamp"],utc=True,errors="raise").dt.tz_localize(None).dt.normalize()
            f=f[OHLC].apply(pd.to_numeric,errors="raise")
            f.index=idx
            f=f.sort_index()
            require(not f.index.has_duplicates and not f.index.isna().any()
                    and str(f.index[-1].date())==session, "PRODUCER_PRICE_CALENDAR")
            frames[s]=f
    return session,frames


def calendar_names(start,end):
    cal=xc.get_calendar("XNYS")
    days=cal.sessions_in_range(start,end)
    return cal,days,[str(d.date()) for d in days]


def bars_window(frames,s,days):
    f=frames[s].reindex(pd.to_datetime(days))[OHLC]
    v=f.to_numpy(float)
    require(np.isfinite(v).all() and (v>0).all()
            and (v[:,2]<=np.minimum(v[:,0],v[:,3])).all()
            and (v[:,1]>=np.maximum(v[:,0],v[:,3])).all(),
            "PRODUCER_MISSING_OR_INVALID_OHLC:"+s)
    return v


def daily_inputs(p,frames,names,i):
    require(i>=200 and i+4<len(names),"PRODUCER_WARMUP_OR_CALENDAR")
    bars,mom,atr,windows={},{},{},{}
    for s in p["universe"]:
        dates=names[i-20:i+1]
        v=bars_window(frames,s,dates)
        bars[s]=dict(zip(OHLC,map(float,v[-1])))
        mom[s]=float(v[-1,3]/v[0,3]-1)
        tr=np.maximum(v[1:,1]-v[1:,2],
                      np.maximum(abs(v[1:,1]-v[:-1,3]),abs(v[1:,2]-v[:-1,3])))
        atr[s]=float(tr[-14:].mean())
        windows[s]=sha(canonical({"dates":dates,"ohlc":v.tolist()}))
    sd=names[i-200:i]
    spy=bars_window(frames,"SPY",sd)[:,3]
    vix=float(bars_window(frames,"^VIX",[names[i-1]])[0,3])
    market={"spy_above_sma200":bool(spy[-1]>spy.mean()),
            "spy_ret20":float(spy[-1]/spy[-21]-1),
            "spy_ret5":float(spy[-1]/spy[-6]-1),"vix":vix}
    windows["SPY_context"]=sha(canonical({"dates":sd,"closes":spy.tolist()}))
    windows["VIX_context"]=sha(canonical({"date":names[i-1],"close":vix}))
    return {"session":names[i],"context_session":names[i-1],"market":market,
            "mom20":mom,"atr14":atr,"bars":bars,"input_window_sha256":windows}


def rr_plan(open_price,atr,cost_bps):
    risk=.75*atr/open_price
    reward=2.25*atr/open_price
    h=cost_bps/20000
    cost=cost_bps/10000
    linear=(reward-cost)/(risk+cost)
    win=(1+reward)*(1-h)/(1+h)-1
    loss=1-(1-risk)*(1-h)/(1+h)
    exact=win/loss
    if linear<2 or exact<2:
        return None,"RR_BELOW_2"
    if risk<.005:
        return None,"STOP_TOO_TIGHT"
    if risk>.03:
        return None,"STOP_TOO_WIDE"
    if reward>.08:
        return None,"TARGET_TOO_FAR"
    return (open_price*(1-risk),open_price*(1+reward)),"PASS"


class Book:
    def __init__(self,name,names,capital=100000.):
        cohort,cost,family=name.split("_")
        self.name=name
        self.cohort=int(cohort)
        self.cost=int(cost)
        self.families=family.split("+")
        self.names=names
        self.free=float(capital)
        self.slots=[]
        self.counts={}
        self.pnl=0.
        self.trades=0
        self.exits={}

    def marked(self,bars,key):
        return self.free+sum(s["proceeds"] if s["closed"] else
                             s["qty"]*bars[s["symbol"]][key] for s in self.slots)

    def step(self,i,current,previous):
        bars=current["bars"]
        half=self.cost/20000
        marked_open=self.marked(bars,"open")
        trace={"entries":[],"exits":[],"rejections":[]}
        if previous is not None:
            candidates=[]
            for fam in self.families:
                candidates.extend(previous["plans"][f"{self.cohort}_{fam}"])
            # Families are mutually exclusive by regime; keep score order deterministic.
            candidates=sorted(set(candidates),key=lambda s:(-previous["mom20"][s],s))
            sig=previous["session"]
            self.counts[sig]=0
            for symbol in candidates:
                op=bars[symbol]["open"]
                plan,reason=rr_plan(op,previous["atr14"][symbol],self.cost)
                if plan is None or len(self.slots)>=5 or any(
                        s["symbol"]==symbol for s in self.slots):
                    reason=(reason if plan is None else "CAPACITY_OR_DUPLICATE")
                    trace["rejections"].append({"symbol":symbol,"reason":reason})
                    continue
                spend=min(self.free,.2*marked_open)
                if spend<=.001:
                    trace["rejections"].append({"symbol":symbol,"reason":"NO_FREE_CASH"})
                    continue
                self.free-=spend
                slot=dict(symbol=symbol,signal=sig,due=i+3,qty=spend/(op*(1+half)),
                          stop=plan[0],target=plan[1],spend=spend,
                          closed=False,proceeds=0.)
                self.slots.append(slot)
                self.counts[sig]+=1
                self.trades+=1
                trace["entries"].append(dict(symbol=symbol,signal=sig,open=op,**{
                    k:slot[k] for k in ("qty","stop","target","spend","due")}))
        for s in self.slots:
            if s["closed"]:
                continue
            b=bars[s["symbol"]]
            px,reason=None,None
            if b["open"]<=s["stop"]:
                px,reason=b["open"],"STOP_GAP"
            elif b["open"]>=s["target"]:
                px,reason=s["target"],"TARGET_GAP_CAPPED"
            elif b["low"]<=s["stop"] and b["high"]>=s["target"]:
                px,reason=s["stop"],"BOTH_TOUCH_STOP_FIRST"
            elif b["low"]<=s["stop"]:
                px,reason=s["stop"],"STOP"
            elif b["high"]>=s["target"]:
                px,reason=s["target"],"TARGET"
            elif i==s["due"]:
                px,reason=b["close"],"TIME_CLOSE"
            if px is not None:
                s["closed"]=True
                s["proceeds"]=px*(1-half)*s["qty"]
                gain=s["proceeds"]-s["spend"]
                self.pnl+=gain
                self.exits[reason]=self.exits.get(reason,0)+1
                trace["exits"].append(dict(symbol=s["symbol"],signal=s["signal"],
                                           price=px,reason=reason,net_pnl=gain))
        for s in self.slots:
            require(i<=s["due"],"PRODUCER_OVERDUE_SLOT")
            if i==s["due"]:
                require(s["closed"],"PRODUCER_UNCLOSED_SLOT")
                self.free+=s["proceeds"]
        self.slots=[s for s in self.slots if i<s["due"]]
        eq=self.marked(bars,"close")
        require(self.free>=-1e-8 and eq>0 and len(self.slots)<=5,
                "PRODUCER_CASH_OR_CAPACITY")
        trace.update(equity=eq,free_cash=self.free,reserved_slots=len(self.slots))
        return trace


def advance(p,books,clocks,names,i,inputs,previous):
    regime,ranked=plans(p,inputs["market"],inputs["mom20"],inputs["atr14"],i,clocks)
    current=dict(inputs,regime=regime,plans=ranked)
    traces={s:b.step(i,current,previous) for s,b in books.items()}
    return current,traces


def outcomes(books,session):
    return {k:books[k].counts.get(session,0) for k in (PRIMARY,CONTROL)}


def rehearse(p,frames,last_session):
    _,_,names=calendar_names("2022-01-03",
        (pd.Timestamp(last_session)+pd.Timedelta(days=35)).date().isoformat())
    begin=names.index(SEED_START)
    end=names.index(last_session)
    books={s:Book(s,names) for s in SCENARIOS}
    clocks,previous={},None
    curves={s:[] for s in books}
    counts={"K1":0,"K3":0}
    for i in range(begin,end+1):
        current,traces=advance(p,books,clocks,names,i,daily_inputs(p,frames,names,i),previous)
        for f in counts:
            counts[f]+=bool(current["plans"]["20_"+f])
        for s in books:
            curves[s].append(traces[s]["equity"])
        previous=current
    rows={}
    for s,b in books.items():
        _,stats=metrics(curves[s])
        rows[s]=dict(stats,trades=b.trades,pending_slots=len(b.slots),exits=b.exits)
    return dict(version=VERSION,status="HISTORICAL_REHEARSAL_NOT_FORWARD",
                research_only=True,approved_live=False,source_finality_certified=False,
                forward_signals_created=0,first_session=names[begin],last_session=last_session,
                sessions=end-begin+1,cycles=counts,scenarios=rows,
                limitations=["Current adjusted daily OHLC, not independent official prices.",
                             "No entry quote, actual fill or intraday drawdown certification.",
                             "Historical rehearsal only; no anchors or journal events."])


def make_event(events,kind,session,stamp,h,code,**payload):
    e=dict(seq=len(events)+1,prev_hash=events[-1]["hash"] if events else ROOT,
           kind=kind,session=session,recorded_at_utc=stamp,protocol_sha256=h,
           code_sha=code,research_only=True,approved_live=False,**payload)
    e["hash"]=event_hash(e)
    events.append(e)
    return e


def stage(p,h,frames,last_session,events,anchors,evidence_dir,data_sha,research_sha,source_id,code_sha):
    now=utc(datetime.now(timezone.utc))
    old=audit(p,h,events,anchors,now)
    require(code_sha==events[0]["code_sha"],"PRODUCER_ACTIVATED_CODE_SHA_MISMATCH")
    require(not any(old[k] for k in ("missing_signals","missing_marks","missing_settlements",
                                     "missing_data_outcomes","explicit_gaps")),
            "PRODUCER_PRIOR_EPOCH_GAP")
    first=events[0]["session"]
    cal,days,names=calendar_names((pd.Timestamp(first)-pd.Timedelta(days=400)).date().isoformat(),
        (now+pd.Timedelta(days=35)).date().isoformat())
    require(last_session in names,"PRODUCER_NOT_XNYS")
    i=names.index(last_session)
    require(utc(cal.session_close(days[i]))+pd.Timedelta(minutes=45)<=now
            <utc(cal.session_open(days[i+1])),"PRODUCER_CURRENT_SLOT_CLOSED")
    require(i==names.index(first)+old["sealed_sessions"],"PRODUCER_NO_RESEAL_OR_SKIP")
    books={s:Book(s,names) for s in SCENARIOS}
    clocks,previous={},None
    marks={e["session"]:e for e in events if e["kind"]=="MARK"}
    seals={e["session"]:e for e in events if e["kind"]=="SIGNAL"}
    prior_docs={}
    # Replay exactly the archived daily inputs, not today's revised historical
    # features. A revised already-frozen price blocks the epoch rather than
    # silently rewriting a mark or corporate-action-adjusted position.
    for j in range(names.index(first),i):
        day=names[j]
        seal,mark=seals[day],marks[day]
        body=(Path(evidence_dir)/(day+".json")).read_bytes()
        require(sha(body)==seal["evidence_sha256"]==mark["evidence_sha256"],
                "PRODUCER_PRIOR_EVIDENCE_HASH")
        doc=parse(body)
        require(doc["version"]==VERSION and doc["protocol_sha256"]==h
                and doc["session"]==day,"PRODUCER_PRIOR_EVIDENCE_SCOPE")
        frozen=doc["inputs"]
        for s in p["universe"]:
            current=bars_window(frames,s,[day])[0]
            require(np.array_equal(current,np.array([frozen["bars"][s][k] for k in OHLC])),
                    "PRODUCER_FROZEN_PRICE_REVISION:"+s+":"+day)
        for k in ("context_session","market","mom20","atr14"):
            require(frozen[k]==seal[k],"PRODUCER_SEALED_FEATURE_MISMATCH")
        current,traces=advance(p,books,clocks,names,j,frozen,previous)
        require(current["regime"]==seal["regime"] and current["plans"]==seal["plans"]
                and traces==doc["traces"] and
                {s:v["equity"] for s,v in traces.items()}==mark["equity"],
                "PRODUCER_PRIOR_LEDGER_REPLAY_MISMATCH")
        prior_docs[day]=doc
        previous=current
    for e in events:
        if e["kind"]=="SETTLED":
            mature=e["fourth_session"]
            require(mature in prior_docs and
                    sha((Path(evidence_dir)/(mature+".json")).read_bytes())==e["evidence_sha256"]
                    and e["primary_executed_slots"]==outcomes(books,e["session"]),
                    "PRODUCER_PRIOR_SETTLEMENT_MISMATCH")
    current,traces=advance(p,books,clocks,names,i,daily_inputs(p,frames,names,i),previous)
    doc=dict(version=VERSION,protocol_sha256=h,session=last_session,source_id=source_id,
             source_data_sha256=data_sha,source_research_sha256=research_sha,
             inputs=current,traces=traces,research_only=True,approved_live=False)
    raw=canonical(doc)
    d=sha(raw)
    stamp=utc(datetime.now(timezone.utc))
    require(stamp<utc(cal.session_open(days[i+1])),"PRODUCER_SLOT_EXPIRED")
    stamp=stamp.isoformat()
    proposed=list(events)
    code=events[0]["code_sha"]
    seal=make_event(proposed,"SIGNAL",last_session,stamp,h,code,evidence_sha256=d,
                   **{k:current[k] for k in ("context_session","market","mom20","atr14",
                                              "regime","plans")})
    make_event(proposed,"MARK",last_session,stamp,h,code,evidence_sha256=d,
               signal_hash=seal["hash"],equity={s:t["equity"] for s,t in traces.items()})
    if i-4>=names.index(first):
        matured=names[i-4]
        make_event(proposed,"SETTLED",matured,stamp,h,code,evidence_sha256=d,
                   signal_hash=seals[matured]["hash"],entry_session=names[i-3],
                   fourth_session=last_session,status="COMPLETE",
                   primary_executed_slots=outcomes(books,matured))
    return raw,proposed[len(events):]


def checkout_sha():
    cwd=Path(__file__).resolve().parent
    head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=cwd,text=True).strip()
    require(digest_ok(head,40),"PRODUCER_CHECKOUT_SHA")
    paths=["challenger_forward_producer.py","challenger_prequential.py",
           "challenger_prequential_protocol.json"]
    require(subprocess.run(["git","diff","--quiet","HEAD","--",*paths],cwd=cwd).returncode==0,
            "PRODUCER_DIRTY_FROZEN_CODE")
    return head


def self_test():
    p,h=load_protocol()
    names=["2026-11-24","2026-11-25","2026-11-27","2026-11-30","2026-12-01","2026-12-02"]
    b=Book(PRIMARY,names)
    sym=p["universe"][0]
    bars={s:dict(open=100.,high=100.,low=100.,close=100.) for s in p["universe"]}
    previous=dict(session=names[0],plans={"20_K1":[sym],"20_K3":[]},
                  mom20={s:0. for s in p["universe"]},atr14={s:3. for s in p["universe"]})
    now=dict(bars=bars)
    tr=b.step(1,now,previous)
    require(len(tr["entries"])==1 and b.free==80000 and len(b.slots)==1,"PRODUCER_ENTRY_TEST")
    # Stop gap must use actual opening proxy; slot remains reserved.
    now["bars"][sym]=dict(open=94.,high=95.,low=93.,close=94.)
    tr=b.step(2,now,None)
    require(tr["exits"][0]["reason"]=="STOP_GAP" and len(b.slots)==1
            and b.free==80000,"PRODUCER_GAP_RESERVE_TEST")
    b.step(3,now,None)
    b.step(4,now,None)
    require(not b.slots and abs(b.free-100000-b.pnl)<1e-8,"PRODUCER_LEDGER_TEST")
    require(rr_plan(100,10,30)[0] is None and rr_plan(100,3,100)[0] is None,
            "PRODUCER_RR_VETO_TEST")
    # Stage and replay with synthetic anchors only; no actual journal publication.
    _,_,timeline=calendar_names("2025-10-01","2026-12-04")
    frames={}
    for symbol in p["universe"]+["^VIX"]:
        v=24. if symbol=="^VIX" else 100.
        frames[symbol]=pd.DataFrame({"open":v,"high":v+1,"low":v-1,"close":v},
                                    index=pd.to_datetime(timeline))
    events=[]
    code="a"*40
    activate=make_event(events,"ACTIVATE",names[0],"2026-11-24T12:00:00Z",h,code,
                        review_evidence_sha256="b"*64)
    anchors={activate["hash"]:dict(kind="PROTECTED_ACTIONS_ARTIFACT",
                    anchor_id="SYNTHETIC_TEST_ONLY",published_at_utc=activate["recorded_at_utc"])}
    class Clock:
        stamp="2026-11-24T22:00:00Z"
        @classmethod
        def now(cls,tz):
            return pd.Timestamp(cls.stamp).to_pydatetime()
    def staged(day,folder):
        return stage(p,h,frames,day,events,anchors,folder,"c"*64,"d"*64,
                     "SYNTHETIC_TEST_ONLY",code)
    with tempfile.TemporaryDirectory() as tmp, patch(__name__+".datetime",Clock):
        raw,batch=staged(names[0],tmp)
        require([e["kind"] for e in batch]==["SIGNAL","MARK"] and
                batch[0]["evidence_sha256"]==sha(raw),"PRODUCER_STAGE_TEST")
        (Path(tmp)/(names[0]+".json")).write_bytes(raw)
        for e in batch:
            events.append(e)
            anchors[e["hash"]]=dict(kind="PROTECTED_ACTIONS_ARTIFACT",
                  anchor_id="SYNTHETIC_TEST_ONLY",published_at_utc=e["recorded_at_utc"])
        Clock.stamp="2026-11-25T22:00:00Z"
        _,batch=staged(names[1],tmp)
        require(len(batch)==2 and batch[0]["prev_hash"]==events[-1]["hash"],
                "PRODUCER_STAGE_REPLAY_TEST")
        frames[sym].loc[pd.Timestamp(names[0]),"close"]=100.1
        try:
            staged(names[1],tmp)
        except ValueError as exc:
            require(str(exc).startswith("PREQUENTIAL_PRODUCER_FROZEN_PRICE_REVISION"),
                    "PRODUCER_REVISION_WRONG_ERROR")
        else:
            raise AssertionError("PRODUCER_FROZEN_PRICE_REVISION_NOT_BLOCKED")
    print("CHALLENGER_PRODUCER_SYNTHETIC_SELF_TEST_PASS")


def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument("--self-test",action="store_true")
    a.add_argument("--mode",choices=("rehearse","stage"))
    for k in ("data","data-sha256","research","research-sha256","source-id","out",
              "journal","journal-sha256","anchors","anchors-sha256","evidence-dir"):
        a.add_argument("--"+k)
    args=a.parse_args()
    if args.self_test:
        self_test()
        return
    require(all([args.mode,args.data,args.data_sha256,args.research,args.research_sha256,
                 args.source_id,args.out]),"PRODUCER_ARGUMENTS")
    p,h=load_protocol()
    data=pinned(args.data,args.data_sha256)
    research=pinned(args.research,args.research_sha256)
    last,frames=archive_frames(p,data,research)
    out=Path(args.out)
    require(not out.exists(),"PRODUCER_OUTPUT_MUST_BE_NEW")
    if args.mode=="rehearse":
        report=rehearse(p,frames,last)
        report.update(protocol_sha256=h,source_id=args.source_id,
                      source_data_sha256=args.data_sha256,source_research_sha256=args.research_sha256)
        out.mkdir(parents=True)
        (out/"historical_rehearsal.json").write_bytes(canonical(report))
        print(json.dumps(report))
    else:
        require(all([args.journal,args.journal_sha256,args.anchors,args.anchors_sha256,
                     args.evidence_dir]),"PRODUCER_ACTIVATED_JOURNAL_REQUIRED")
        journal=pinned(args.journal,args.journal_sha256)
        anchors=pinned(args.anchors,args.anchors_sha256)
        raw,events=stage(p,h,frames,last,[parse(x) for x in journal.splitlines() if x.strip()],
                         parse(anchors),args.evidence_dir,args.data_sha256,args.research_sha256,
                         args.source_id,checkout_sha())
        out.mkdir(parents=True)
        (out/(last+".json")).write_bytes(raw)
        (out/"proposed_events.jsonl").write_bytes(b"".join(canonical(e)+b"\n" for e in events))
        print(json.dumps(dict(status="UNANCHORED_PROPOSALS_NOT_FORWARD_EVIDENCE",
                              session=last,proposed_events=len(events),
                              evidence_sha256=sha(raw),research_only=True,approved_live=False)))


if __name__=="__main__":
    main()
