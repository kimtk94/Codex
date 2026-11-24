#!/usr/bin/env python3
"""Read-only P0 evidence inventory; not prospective activation.

Archived source evidence is not new independent exchange certification.
Native schedule metadata counts are not authenticated cron-role/first-seal
proof. No credentials for market data, Drive, broker, or writes.
"""
import argparse
from collections import Counter
from datetime import date, datetime, time, timezone
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import zipfile

DATA_SHA="6b5cec11a98fd160496d476ff7f773a3be8ecdaf49867cadadef9d20da6d36cf"
RESEARCH_SHA="c6e711b7db3f91d5081947f95b320fe3cbbddfeb671df97edf9a24a4ff5f2d6f"
SESSION="2026-11-23"
DAYS=("2026-11-24","2026-11-25")
WORKFLOWS={"daily20":("kalman-daily20.yml",((2,40),(4,40))),
           "watchdog":("kalman-daily20-slot-watchdog.yml",((6,25),(7,25)))}


def check(ok,code):
    if not ok:
        raise ValueError("P0_"+code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pinned(path,digest,members):
    raw=Path(path).read_bytes()
    check(sha(raw)==digest,"PIN")
    z=zipfile.ZipFile(io.BytesIO(raw))
    check(len(z.namelist())==len(set(z.namelist()))==members and z.testzip() is None,"ZIP")
    return z


def unique(rows):
    d={r["symbol"]:r for r in rows}
    check(len(d)==len(rows),"DUPLICATE_SYMBOL")
    return d


def number(x):
    return type(x) in (int,float) and math.isfinite(x) and x>0


def source_inventory(data,research):
    with pinned(data,DATA_SHA,52) as dz, pinned(research,RESEARCH_SHA,135) as rz:
        read=lambda p:json.loads(rz.read(p))
        s=read("research/source_finality/report.json")
        i=read("research/source_finality/independent_feed.json")
        v=read("research/source_finality/venue_identity.json")
        o=read("research/official_price_proof_obligations/report.json")
        a=read("research/official_close_access/report.json")
        t=read("research/two_pass/report.json")
        for d in (s,i,v,o,a,t):
            check(d["session"]==SESSION and d["research_only"] is True and
                  d["live_execution"] is False and d["production_writes"] is False,
                  "REPORT_SCOPE")
        check(s["required"]==s["examined"]==s["reference_coverage"]==26
              and s["verified"]==v["finality_verified"]==o["official_close_certified"]==
              a["official_close_certified"]==o["independent_factor_certified"]==0,
              "FINALITY_SCOPE")
        symbols=unique(s["symbols"])
        venue=unique(v["rows"])
        obligations=unique(o["rows"])
        access=unique(a["rows"])
        check(len(symbols)==len(obligations)==len(access)==26
              and set(symbols)==set(obligations)==set(access)==set(venue)|{"^VIX"}
              and len(venue)==25,"INVENTORY")
        raw_diffs=[]
        for sym,r in symbols.items():
            path="market/raw/yfinance/yf_"+sym.lower().replace("^","")+".parquet"
            check(sha(dz.read(path))==r["source_parquet_sha256"]==
                  obligations[sym]["model_parquet_sha256"],"PARQUET_LINK")
            check(r["finality_verified"] is False and obligations[sym]["close_certified"] is False,
                  "FALSE_CERTIFICATION")
            check(number(r["yahoo_close"]) and number(r["reference_price"]),"PRICE")
            if sym=="^VIX":
                check(r["yahoo_is_adjusted"] is False,"VIX_BASIS")
                continue
            w=venue[sym]
            p=w["selected_primary_raw_M_price"]
            check(number(p) and p==r["reference_price"] and r["yahoo_is_adjusted"] is True
                  and r["reference_adjustment"]=="RAW"
                  and w["session_primary_listing_certified"] is False
                  and obligations[sym]["factor_certified"] is False,"VENUE_BASIS")
            q=i["alpaca"]["symbols"][sym]["quotes"]
            check(any(x["price"]==p and x["exchange"]==w["selected_primary_venue_code"]
                      and x["timestamp_utc"]==w["selected_primary_timestamp_utc"]
                      and x["condition"]=="M" for x in q),"M_REFERENCE_LINK")
            raw_diffs.append(abs(r["yahoo_close"]-p))
        raw=rz.read("research/official_close_access/cboe_vix_public_source.csv.gz")
        cboe=a["cboe_publisher_recheck"]
        check(sha(raw)==a["raw_publication_gzip_sha256"] and
              sha(gzip.decompress(raw))==cboe["recheck_raw_sha256"]==
              i["cboe"]["body_sha256"],"CBOE_BODY_HASH")
        rows=[x for x in gzip.decompress(raw).decode("utf-8-sig").splitlines()
              if x.startswith("11/23/2026,")]
        check(len(rows)==1 and float(rows[0].split(",")[-1])==
              cboe["original_close"]==cboe["recheck_close"]==symbols["^VIX"]["reference_price"]
              and cboe["same_session_value_unchanged"] is True
              and cboe["official_16_et_clock_certified"] is False,"CBOE_VALUE")
        check(t["bull_new"]==t["bear_new"]==0 and
              t["journal_prefix_byte_identical"] is True and
              t["all_prior_snapshots_byte_identical"] is True and
              t["original_signal_events_rewritten"] is False,"REPLAY_PREFIX")
        return dict(session=SESSION,parquet_hash_links_verified=26,
                    numerically_within_half_cent=sum(x<=.005 for x in raw_diffs)+
                        int(abs(symbols["^VIX"]["yahoo_close"]-symbols["^VIX"]["reference_price"])<=.005),
                    max_equity_etf_numeric_abs_difference_usd=max(raw_diffs),
                    adjusted_vs_raw_basis_unresolved=25,
                    sip_m_venue_conflicts=sum(len({q["price"] for q in r["quotes"]})>1
                                              for r in i["alpaca"]["symbols"].values()),
                    current_listing_venue_counts=dict(Counter(r["primary_canonical"] for r in venue.values())),
                    issuer_cash_gap_count=sum(bool(r.get("issuer_cash_gap")) for r in obligations.values()),
                    cboe_archived_two_captures_match=True,cboe_body_hash_verified=True,
                    independent_official_close_certified=0,independent_factor_certified=0,
                    replay_new_events=0,replay_frozen_prefix_identical=True,
                    replay_status=t["status"],new_market_data_collected=False)


def schedule_record(meta,pages,role,day,now):
    filename,slots=WORKFLOWS[role]
    due=sum(datetime.combine(date.fromisoformat(day),time(h,m),timezone.utc)<=now for h,m in slots)
    result=dict(workflow=filename,utc_day=day,expected_slots=2,due_slots=due,
                native_run_count=None,workflow_state=None,slot_role_certified=False)
    if meta is None or pages is None:
        return dict(result,status="API_UNAVAILABLE_HOLD")
    check(meta["path"]==".github/workflows/"+filename and type(meta["id"]) is int,
          "WORKFLOW_IDENTITY")
    check(isinstance(pages,list) and bool(pages),"RUN_PAGES")
    runs=[r for page in pages for r in page["workflow_runs"]]
    check(len(runs)==len({r["id"] for r in runs}) and
          all(page["total_count"]==len(runs) for page in pages),"RUN_PAGE_COMPLETENESS")
    for r in runs:
        check(r["workflow_id"]==meta["id"] and r["head_branch"]=="main"
              and r["event"]=="schedule" and r["created_at"][:10]==day,"RUN_FILTER")
    result.update(workflow_state=meta["state"],native_run_count=len(runs),
                  run_ids=[r["id"] for r in runs],
                  successful_runs=sum(r["conclusion"]=="success" and r["status"]=="completed" for r in runs))
    if meta["state"]!="active":
        status="WORKFLOW_NOT_ACTIVE_HOLD"
    elif due<2:
        status="NOT_ALL_SLOTS_DUE"
    elif len(runs)<2:
        status="NATIVE_DELIVERY_COUNT_INCOMPLETE_HOLD"
    else:
        status="RUN_COUNT_OBSERVED_CRON_ROLE_AND_LOG_PROOF_REQUIRED"
    return dict(result,status=status)


def load_optional(path):
    p=Path(path)
    return json.loads(p.read_text()) if p.is_file() and p.stat().st_size else None


def self_test():
    m=dict(path=".github/workflows/kalman-daily20.yml",id=1,state="active")
    now=datetime(2026,11,24,8,tzinfo=timezone.utc)
    empty=[dict(total_count=0,workflow_runs=[])]
    check(schedule_record(m,empty,"daily20",DAYS[0],now)["status"]==
          "NATIVE_DELIVERY_COUNT_INCOMPLETE_HOLD","TEST_MISSING")
    check(schedule_record(m,empty,"daily20",DAYS[1],now)["status"]==
          "NOT_ALL_SLOTS_DUE","TEST_FUTURE")
    check(schedule_record(None,empty,"daily20",DAYS[0],now)["native_run_count"] is None,
          "TEST_UNAVAILABLE")
    run=dict(id=2,workflow_id=1,head_branch="main",event="push",
             created_at="2026-11-24T02:40:00Z",status="completed",conclusion="success")
    try:
        schedule_record(m,[dict(total_count=1,workflow_runs=[run])],"daily20",DAYS[0],now)
    except ValueError as ex:
        check(str(ex)=="P0_RUN_FILTER","TEST_WRONG_REJECTION")
    else:
        raise AssertionError("P0_TEST_PUSH_NOT_REJECTED")
    print("CHALLENGER_P0_READINESS_SYNTHETIC_PASS")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--self-test",action="store_true")
    for k in ("data","research","schedule-dir","out"):
        p.add_argument("--"+k)
    a=p.parse_args()
    if a.self_test:
        self_test()
        return
    check(all([a.data,a.research,a.schedule_dir,a.out]),"ARGUMENTS")
    now=datetime.now(timezone.utc)
    records=[]
    for role in WORKFLOWS:
        meta=load_optional(Path(a.schedule_dir)/(role+"_meta.json"))
        for day in DAYS:
            pages=load_optional(Path(a.schedule_dir)/(role+"_"+day+".json"))
            records.append(schedule_record(meta,pages,role,day,now))
    result=dict(version="kalman-challenger-p0-readiness-v1",
        status="RESEARCH_HOLD",research_only=True,approved_live=False,activation_authorized=False,
        source_finality_certified=False,forward_signals_created=0,
        observed_at_utc=now.isoformat(),source=source_inventory(a.data,a.research),
        native_schedule=records,native_cron_role_and_first_seal_verified=False,
        limitations=["Archived numeric agreement is not independently certified price or historical factor proof.",
            "GitHub workflow state is current, not past state. Run counts are not cron-role or log verification.",
            "No missing-run dispatch, schedule edit, activation or Drive/broker write."])
    out=Path(a.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("x") as f:
        json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(result,allow_nan=False))

if __name__=="__main__":
    main()
