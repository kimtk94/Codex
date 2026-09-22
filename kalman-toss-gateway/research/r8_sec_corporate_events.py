from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

SCHEMA="kalman-r8-sec-corporate-events-v1"
SEC_TICKERS="https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS="https://data.sec.gov/submissions"
DEFAULT_R5_SCORED="/mnt/gdrive/US_ETF/model_lab_v1/results/r5_0_1_research_sandbox_all_data/r5_0_1_scored_rows.parquet"
DEFAULT_OUT="/opt/kalman/state/r8_sec"

ITEM_BUCKETS={
    "1.01":"MATERIAL_AGREEMENT",
    "2.01":"ACQUISITION_DISPOSITION",
    "2.02":"EARNINGS_RESULTS",
    "2.03":"FINANCING_OBLIGATION",
    "2.05":"RESTRUCTURING_IMPAIRMENT",
    "2.06":"RESTRUCTURING_IMPAIRMENT",
    "3.01":"DELISTING_COMPLIANCE",
    "3.02":"FINANCING_OBLIGATION",
    "5.02":"MANAGEMENT_BOARD",
    "7.01":"REG_FD",
    "8.01":"OTHER_EVENT",
    "9.01":"FINANCIAL_EXHIBITS",
}

def norm_symbol(x):
    return re.sub(r"[^A-Z0-9]","",str(x or "").upper())

class SecClient:
    def __init__(self,user_agent,min_interval=0.22,timeout=30):
        self.client=httpx.Client(
            timeout=timeout,
            headers={
                "User-Agent":user_agent,
                "Accept-Encoding":"gzip, deflate",
            },
            follow_redirects=True,
        )
        self.min_interval=float(min_interval)
        self.last=0.0

    def get_json(self,url):
        wait=self.min_interval-(time.monotonic()-self.last)
        if wait>0:
            time.sleep(wait)
        r=self.client.get(url)
        self.last=time.monotonic()
        r.raise_for_status()
        return r.json()

def load_universe(path):
    q=pd.read_parquet(path,columns=["symbol"])
    syms=sorted(q["symbol"].dropna().astype(str).str.upper().unique())
    if len(syms)!=93:
        raise RuntimeError(f"expected frozen R5 universe=93, got {len(syms)}")
    return syms

def load_ticker_map(client):
    raw=client.get_json(SEC_TICKERS)
    out={}
    for _,row in raw.items():
        ticker=str(row.get("ticker") or "").upper()
        cik=str(row.get("cik_str") or "").zfill(10)
        if ticker and cik:
            out.setdefault(norm_symbol(ticker),[]).append({
                "ticker":ticker,
                "cik":cik,
                "title":row.get("title"),
            })
    return out

def pick_mapping(symbol,candidates):
    if not candidates:
        return None
    exact=[x for x in candidates if x["ticker"]==symbol]
    if len(exact)==1:
        return exact[0]
    if len(candidates)==1:
        return candidates[0]
    return None

def rows_from_columnar(obj):
    if not isinstance(obj,dict) or not obj:
        return []
    lengths=[len(v) for v in obj.values() if isinstance(v,list)]
    n=max(lengths) if lengths else 0
    rows=[]
    for i in range(n):
        row={}
        for k,v in obj.items():
            if isinstance(v,list):
                row[k]=v[i] if i<len(v) else None
        rows.append(row)
    return rows

def filing_rows_from_submission(payload):
    filings=payload.get("filings") or {}
    recent=filings.get("recent") or {}
    return rows_from_columnar(recent)

def historical_file_rows(payload):
    if "filings" in payload:
        return filing_rows_from_submission(payload)
    return rows_from_columnar(payload)

def overlap_file(meta,start_year,end_year):
    a=str(meta.get("filingFrom") or "")
    b=str(meta.get("filingTo") or "")
    try:
        ay=int(a[:4]); by=int(b[:4])
    except Exception:
        return True
    return by>=start_year and ay<=end_year

def parse_acceptance(x):
    if not x:
        return None
    t=pd.to_datetime(x,utc=True,errors="coerce")
    return None if pd.isna(t) else t.isoformat()

def split_items(x):
    if not x:
        return []
    return sorted(set(re.findall(r"\b\d\.\d{2}\b",str(x))))

def event_buckets(items):
    return sorted(set(ITEM_BUCKETS[i] for i in items if i in ITEM_BUCKETS))

def archive_primary_url(cik,accession,primary):
    if not cik or not accession or not primary:
        return None
    return (
        "https://www.sec.gov/Archives/edgar/data/"
        f"{int(cik)}/{str(accession).replace('-','')}/{primary}"
    )

def collect_symbol(client,symbol,mapping,start_year,end_year):
    cik=mapping["cik"]
    base=client.get_json(f"{SEC_SUBMISSIONS}/CIK{cik}.json")
    rows=filing_rows_from_submission(base)

    for meta in (base.get("filings") or {}).get("files") or []:
        if not overlap_file(meta,start_year,end_year):
            continue
        name=meta.get("name")
        if not name:
            continue
        hist=client.get_json(f"{SEC_SUBMISSIONS}/{name}")
        rows.extend(historical_file_rows(hist))

    out=[]
    seen=set()
    for r in rows:
        form=str(r.get("form") or "").upper().strip()
        if form not in {"8-K","8-K/A"}:
            continue
        filing_date=str(r.get("filingDate") or "")
        try:
            year=int(filing_date[:4])
        except Exception:
            continue
        if year<start_year or year>end_year:
            continue
        acc=str(r.get("accessionNumber") or "")
        if not acc or acc in seen:
            continue
        seen.add(acc)
        items=split_items(r.get("items"))
        buckets=event_buckets(items)
        out.append({
            "symbol":symbol,
            "cik":cik,
            "company_name":mapping.get("title"),
            "accession_number":acc,
            "form":form,
            "filing_date":filing_date or None,
            "report_date":r.get("reportDate") or None,
            "acceptance_at":parse_acceptance(r.get("acceptanceDateTime")),
            "timestamp_quality":"EDGAR_ACCEPTANCE_TIME" if r.get("acceptanceDateTime") else "MISSING",
            "items":items,
            "event_buckets":buckets,
            "recognized_item":bool(buckets),
            "primary_document":r.get("primaryDocument"),
            "primary_url":archive_primary_url(cik,acc,r.get("primaryDocument")),
            "source":"SEC_EDGAR_SUBMISSIONS",
            "research_only":True,
        })
    return out

def sha256_file(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--r5-scored",default=DEFAULT_R5_SCORED)
    ap.add_argument("--output-dir",default=DEFAULT_OUT)
    ap.add_argument("--start-year",type=int,default=2020)
    ap.add_argument("--end-year",type=int,default=2026)
    ap.add_argument("--min-request-interval",type=float,default=0.22)
    args=ap.parse_args()

    user_agent=os.environ.get(
        "SEC_USER_AGENT",
        "KalmanR8Research/1.0 (noncommercial research; contact repository owner)"
    )
    client=SecClient(user_agent,args.min_request_interval)

    universe=load_universe(args.r5_scored)
    ticker_map=load_ticker_map(client)

    mappings={}
    ambiguous=[]
    unmapped=[]
    for sym in universe:
        candidates=ticker_map.get(norm_symbol(sym),[])
        picked=pick_mapping(sym,candidates)
        if picked:
            mappings[sym]=picked
        elif candidates:
            ambiguous.append({"symbol":sym,"candidates":candidates})
        else:
            unmapped.append(sym)

    events=[]
    errors=[]
    for i,sym in enumerate(universe,1):
        m=mappings.get(sym)
        if not m:
            continue
        try:
            rows=collect_symbol(client,sym,m,args.start_year,args.end_year)
            events.extend(rows)
            print(f"[{i:02d}/{len(universe)}] {sym} CIK={m['cik']} events={len(rows)}",flush=True)
        except Exception as exc:
            errors.append({"symbol":sym,"cik":m["cik"],"error":f"{type(exc).__name__}: {exc}"})
            print(f"[WARN] {sym} {type(exc).__name__}: {exc}",flush=True)

    events.sort(key=lambda x:(x.get("acceptance_at") or "9999",x["symbol"],x["accession_number"]))

    mapped_count=len(mappings)
    event_symbols=len(set(x["symbol"] for x in events))
    n=len(events)
    acceptance_n=sum(bool(x.get("acceptance_at")) for x in events)
    recognized_n=sum(bool(x.get("recognized_item")) for x in events)
    semantic_n=sum(
        any(b!="FINANCIAL_EXHIBITS" for b in x.get("event_buckets") or [])
        for x in events
    )
    accessions=[x["accession_number"] for x in events]
    duplicate_ratio=(len(accessions)-len(set(accessions)))/len(accessions) if accessions else 0.0

    times=pd.to_datetime([x["acceptance_at"] for x in events if x.get("acceptance_at")],utc=True,errors="coerce")
    first=(times.min().isoformat() if len(times) else None)
    last=(times.max().isoformat() if len(times) else None)
    span_months=((times.max()-times.min()).total_seconds()/86400/30.4375 if len(times)>=2 else 0.0)

    item_counts={}
    for x in events:
        for b in x["event_buckets"]:
            item_counts[b]=item_counts.get(b,0)+1

    gates={
        "universe_is_93":len(universe)==93,
        "mapped_symbols_ge_90":mapped_count>=90,
        "span_months_ge_24":span_months>=24,
        "event_symbols_ge_70":event_symbols>=70,
        "event_rows_ge_500":n>=500,
        "acceptance_timestamp_ratio_ge_95pct":(acceptance_n/n if n else 0)>=0.95,
        "accession_duplicate_ratio_le_1pct":duplicate_ratio<=0.01,
        "semantic_item_ratio_ge_80pct":(semantic_n/n if n else 0)>=0.80,
    }
    ready=all(gates.values())

    out=Path(args.output_dir)
    out.mkdir(parents=True,exist_ok=True)
    (out/"events.json").write_text(json.dumps(events,indent=2)+"\n")
    (out/"symbol_cik_map.json").write_text(json.dumps(mappings,indent=2)+"\n")
    (out/"mapping_issues.json").write_text(json.dumps({"ambiguous":ambiguous,"unmapped":unmapped},indent=2)+"\n")

    manifest={
        "schema":SCHEMA,
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "research_only":True,
        "production_changed":False,
        "api_key_required":False,
        "sec_user_agent":user_agent,
        "request_interval_seconds":args.min_request_interval,
        "start_year":args.start_year,
        "end_year":args.end_year,
        "frozen_universe_symbols":len(universe),
        "mapped_symbols":mapped_count,
        "ambiguous_symbols":len(ambiguous),
        "unmapped_symbols":len(unmapped),
        "symbols_with_events":event_symbols,
        "event_rows":n,
        "acceptance_timestamp_rows":acceptance_n,
        "acceptance_timestamp_ratio":acceptance_n/n if n else 0.0,
        "recognized_item_rows":recognized_n,
        "recognized_item_ratio":recognized_n/n if n else 0.0,
        "semantic_item_rows_excluding_9_01_only":semantic_n,
        "semantic_item_ratio_excluding_9_01_only":semantic_n/n if n else 0.0,
        "accession_duplicate_ratio":duplicate_ratio,
        "first_acceptance_at":first,
        "last_acceptance_at":last,
        "span_months":span_months,
        "event_bucket_counts":item_counts,
        "collection_errors":errors,
        "gates":gates,
        "sec_event_ready":ready,
        "model_fitting_allowed":False,
        "next_action":"PREREGISTER_SINGLE_SEC_ABLATION" if ready else "FIX_DATA_READINESS_ONLY",
        "r5_scored_sha256":sha256_file(args.r5_scored),
    }
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print(json.dumps(manifest,indent=2))
    print("EVENTS_FILE=",out/"events.json")
    print("MANIFEST=",out/"manifest.json")

if __name__=="__main__":
    main()
