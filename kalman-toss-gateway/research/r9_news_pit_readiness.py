from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import httpx
import pandas as pd

SCHEMA="kalman-r9-news-pit-readiness-v1"
DEFAULT_EVENTS="/opt/kalman/state/r8_sec/events.json"
DEFAULT_R8_MANIFEST="/opt/kalman/state/r8_sec/manifest.json"
DEFAULT_OUT="/opt/kalman/state/r9_news_pit"
GDELT="https://api.gdeltproject.org/api/v2/doc/doc"

TRACKING_PREFIXES=("utm_","fbclid","gclid","mc_")
COMPANY_SUFFIX_RE=re.compile(
    r"\b(CORPORATION|CORP|INCORPORATED|INC|COMPANY|CO|PLC|LTD|LIMITED|HOLDINGS?)\b",
    re.I,
)
WS_RE=re.compile(r"\s+")

def clean_company_name(x):
    s=str(x or "").replace("&"," and ")
    s=re.sub(r"[^A-Za-z0-9. -]+"," ",s)
    s=WS_RE.sub(" ",s).strip(" .-")
    return s

ALIAS_OVERRIDES={
    "AMZN":"Amazon",
    "GOOG":"Alphabet",
    "GOOGL":"Alphabet",
    "JPM":"JPMorgan Chase",
    "XOM":"ExxonMobil",
    "META":"Meta Platforms",
    "UNH":"UnitedHealth Group",
    "WMT":"Walmart",
    "MSFT":"Microsoft",
    "NVDA":"NVIDIA",
    "AAPL":"Apple Inc",
}

def query_alias(company_name,symbol=None):
    if symbol and symbol in ALIAS_OVERRIDES:
        return ALIAS_OVERRIDES[symbol]
    s=clean_company_name(company_name)
    s=re.sub(
        r"\s+(CORPORATION|CORP|INCORPORATED|INC|COMPANY|CO|PLC|LTD|LIMITED)$",
        "",
        s,
        flags=re.I,
    ).strip()
    return s

def canonical_url(url):
    if not url:
        return None
    try:
        u=urlsplit(str(url).strip())
        q=[
            (k,v) for k,v in parse_qsl(u.query,keep_blank_values=True)
            if not k.lower().startswith(TRACKING_PREFIXES)
        ]
        return urlunsplit((u.scheme.lower(),u.netloc.lower(),u.path,urlencode(q),""))
    except Exception:
        return str(url).strip() or None

def parse_seen(x):
    if not x:
        return pd.NaT
    return pd.to_datetime(str(x),format="%Y%m%dT%H%M%SZ",utc=True,errors="coerce")

def article_id(symbol,url):
    return hashlib.sha256(f"{symbol}|{url}".encode()).hexdigest()

def load_registry(events_path):
    rows=json.loads(Path(events_path).read_text())
    by={}
    for e in rows:
        sym=str(e.get("symbol") or "").upper()
        name=str(e.get("company_name") or "").strip()
        if sym and name:
            by.setdefault(sym,[]).append(name)
    reg=[]
    for sym,names in sorted(by.items()):
        # mode-like deterministic choice: longest normalized name, then lexical.
        uniq=sorted(set(names),key=lambda x:(-len(clean_company_name(x)),clean_company_name(x)))
        name=uniq[0]
        reg.append({"symbol":sym,"company_name":name,"query_alias":query_alias(name,sym)})
    return pd.DataFrame(reg)

def month_windows(start,end):
    start=pd.Timestamp(start)
    end=pd.Timestamp(end)
    cur=start.floor("D")
    while cur<end:
        nxt=min(cur+pd.offsets.MonthBegin(1),end)
        if nxt<=cur:
            nxt=min(cur+pd.offsets.MonthEnd(1)+pd.Timedelta(days=1),end)
        yield cur,nxt
        cur=nxt

class GdeltClient:
    def __init__(self,min_interval=8.0,timeout=45,max_retries=4):
        self.client=httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent":"KalmanR9NewsResearch/1.0"},
        )
        self.min_interval=float(min_interval)
        self.max_retries=int(max_retries)
        self.last=0.0

    def _wait_interval(self):
        wait=self.min_interval-(time.monotonic()-self.last)
        if wait>0:
            time.sleep(wait)

    def search(self,alias,start,end,maxrecords=250):
        params={
            "query":f'\"{alias}\" sourcelang:english',
            "mode":"artlist",
            "format":"json",
            "maxrecords":str(maxrecords),
            "sort":"datedesc",
            "startdatetime":pd.Timestamp(start).strftime("%Y%m%d%H%M%S"),
            "enddatetime":pd.Timestamp(end).strftime("%Y%m%d%H%M%S"),
        }
        last_error=None
        for attempt in range(self.max_retries+1):
            self._wait_interval()
            r=self.client.get(GDELT,params=params)
            self.last=time.monotonic()
            if r.status_code==429:
                retry_after=r.headers.get("retry-after")
                try:
                    pause=float(retry_after) if retry_after else 10.0*(2**attempt)
                except Exception:
                    pause=10.0*(2**attempt)
                last_error=f"HTTP 429 retry_after={retry_after}"
                if attempt<self.max_retries:
                    time.sleep(max(pause,self.min_interval))
                    continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError(last_error or "GDELT retry exhaustion")

def extract_articles(payload):
    if not isinstance(payload,dict):
        return []
    rows=payload.get("articles")
    return rows if isinstance(rows,list) else []

def select_smoke_symbols(reg):
    preferred=["AAPL","MSFT","NVDA","AMZN","META","GOOG","JPM","XOM","WMT","UNH"]
    have=set(reg["symbol"])
    got=[x for x in preferred if x in have]
    if len(got)<10:
        got += [x for x in reg["symbol"] if x not in got][:10-len(got)]
    return got[:10]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--events",default=DEFAULT_EVENTS)
    ap.add_argument("--r8-manifest",default=DEFAULT_R8_MANIFEST)
    ap.add_argument("--output-dir",default=DEFAULT_OUT)
    ap.add_argument("--mode",choices=["smoke","recent"],default="smoke")
    ap.add_argument("--min-request-interval",type=float,default=8.0)
    args=ap.parse_args()

    r8=json.loads(Path(args.r8_manifest).read_text())
    if r8.get("schema")!="kalman-r8-sec-corporate-events-v2" or not r8.get("sec_event_ready"):
        raise RuntimeError("R8 SEC v2 registry is not ready")

    reg=load_registry(args.events)
    if len(reg)!=93:
        raise RuntimeError(f"expected 93-symbol registry, got {len(reg)}")

    if args.mode=="smoke":
        symbols=select_smoke_symbols(reg)
        start=pd.Timestamp("2026-08-01T00:00:00Z")
        end=pd.Timestamp("2026-09-01T00:00:00Z")
    else:
        symbols=reg["symbol"].tolist()
        # DOC 2.0 supports explicit START/END only within the recent ~3-month window.
        # This snapshot stays inside that bound on the preregistration date.
        start=pd.Timestamp("2026-06-23T00:00:00Z")
        end=pd.Timestamp("2026-09-02T13:30:00Z")

    client=GdeltClient(args.min_request_interval)
    rows=[]
    query_audit=[]

    for sym in symbols:
        rr=reg.loc[reg["symbol"]==sym].iloc[0]
        alias=rr["query_alias"]
        for ws,we in month_windows(start,end):
            status="OK"
            err=None
            arts=[]
            try:
                payload=client.search(alias,ws,we,250)
                arts=extract_articles(payload)
            except Exception as exc:
                status="ERROR"
                err=f"{type(exc).__name__}: {exc}"
            saturated=len(arts)>=250
            query_audit.append({
                "symbol":sym,
                "company_name":rr["company_name"],
                "query_alias":alias,
                "window_start":ws,
                "window_end":we,
                "status":status,
                "articles":len(arts),
                "saturated":saturated,
                "error":err,
            })
            for a in arts:
                url=canonical_url(a.get("url"))
                seen=parse_seen(a.get("seendate"))
                if not url:
                    continue
                rows.append({
                    "symbol":sym,
                    "company_name":rr["company_name"],
                    "query_alias":alias,
                    "canonical_url":url,
                    "title":a.get("title"),
                    "domain":a.get("domain"),
                    "language":a.get("language"),
                    "sourcecountry":a.get("sourcecountry"),
                    "available_at":seen,
                    "time_quality":"GDELT_SEENDATE_OBSERVED_PROXY",
                    "gdelt_raw_seendate":a.get("seendate"),
                    "query_window_start":ws,
                    "query_window_end":we,
                    "query_saturated":saturated,
                    "article_id":article_id(sym,url),
                })
            print(f"{sym} {ws.date()} status={status} articles={len(arts)} saturated={saturated}",flush=True)

    q=pd.DataFrame(query_audit)
    d=pd.DataFrame(rows)
    raw_rows=len(d)
    if not d.empty:
        d=d.sort_values(["symbol","available_at","canonical_url"],na_position="last")
        d=d.drop_duplicates(["symbol","canonical_url"],keep="first").reset_index(drop=True)

    out=Path(args.output_dir)
    out.mkdir(parents=True,exist_ok=True)
    reg.to_csv(out/"symbol_alias_registry.csv",index=False)
    q.to_csv(out/f"query_audit_{args.mode}.csv",index=False)
    d.to_parquet(out/f"articles_{args.mode}.parquet",index=False)

    successful=q["status"].eq("OK")
    http_success=float(successful.mean()) if len(q) else 0.0
    saturated_ratio=float(q.loc[successful,"saturated"].mean()) if successful.any() else 1.0
    seen_ratio=float(d["available_at"].notna().mean()) if len(d) else 0.0
    url_ratio=float(d["canonical_url"].notna().mean()) if len(d) else 0.0
    dup_ratio=float((raw_rows-len(d))/raw_rows) if raw_rows else 0.0
    counts=d.groupby("symbol").size() if len(d) else pd.Series(dtype=int)
    symbols_ge20=int((counts>=20).sum())
    times=pd.to_datetime(d["available_at"],utc=True,errors="coerce").dropna()
    span_months=((times.max()-times.min()).total_seconds()/86400/30.4375 if len(times)>=2 else 0.0)

    if args.mode=="smoke":
        symbols_with_any=int((counts>0).sum())
        smoke_pass=bool(http_success>=0.90 and symbols_with_any>=7 and seen_ratio>=0.90)
        gates={
            "http_success_ge_90pct":http_success>=0.90,
            "symbols_with_articles_ge_7_of_10":symbols_with_any>=7,
            "seendate_parse_ge_90pct":seen_ratio>=0.90,
        }
        ready=False
        next_action="RUN_FULL_READINESS" if smoke_pass else "FIX_NEWS_DATA_READINESS"
    else:
        gates={
            "universe_is_93":len(reg)==93,
            "symbols_ge10_articles_ge_80":symbols_ge20>=80,
            "usable_span_days_ge_60":span_months*30.4375>=60,
            "seendate_parse_ge_95pct":seen_ratio>=0.95,
            "canonical_url_ge_95pct":url_ratio>=0.95,
            "within_symbol_duplicate_ratio_le_5pct":dup_ratio<=0.05,
            "saturated_query_ratio_le_5pct":saturated_ratio<=0.05,
            "dedup_symbol_article_rows_ge_5000":len(d)>=5000,
        }
        smoke_pass=None
        ready=all(gates.values())
        next_action="START_PROSPECTIVE_R9_NEWS_LEDGER" if ready else "FIX_NEWS_DATA_READINESS"

    manifest={
        "schema":SCHEMA,
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "research_only":True,
        "production_changed":False,
        "model_fitting_allowed":False,
        "source":"GDELT_DOC_2",
        "mode":args.mode,
        "query_contract":"exact SEC company-name phrase; ticker-only query prohibited",
        "time_quality":"GDELT_SEENDATE_OBSERVED_PROXY",
        "universe_symbols":len(reg),
        "query_symbols":len(symbols),
        "query_windows":len(q),
        "http_success_ratio":http_success,
        "raw_symbol_article_rows":raw_rows,
        "dedup_symbol_article_rows":len(d),
        "within_symbol_duplicate_ratio":dup_ratio,
        "symbols_with_20plus_articles":symbols_ge20,
        "seendate_parse_ratio":seen_ratio,
        "canonical_url_ratio":url_ratio,
        "saturated_success_query_ratio":saturated_ratio,
        "usable_span_months":span_months,
        "smoke_quality_pass":smoke_pass,
        "gates":gates,
        "r9_news_ready":ready,\n        "historical_model_fitting_allowed":False,
        "next_action":next_action,
    }
    (out/f"manifest_{args.mode}.json").write_text(json.dumps(manifest,indent=2,default=str)+"\n")
    print(json.dumps(manifest,indent=2,default=str))
    print("ARTICLES=",out/f"articles_{args.mode}.parquet")
    print("AUDIT=",out/f"query_audit_{args.mode}.csv")
    print("MANIFEST=",out/f"manifest_{args.mode}.json")

if __name__=="__main__":
    main()
