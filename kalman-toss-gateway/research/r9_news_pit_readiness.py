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
DEFAULT_CACHE="/opt/kalman/state/r9_news_pit/cache"
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
    def __init__(self,cache_dir,min_interval=15.0,timeout=45,max_retries=5):
        self.client=httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent":"KalmanR9NewsResearch/1.0"},
        )
        self.cache_dir=Path(cache_dir)
        self.cache_dir.mkdir(parents=True,exist_ok=True)
        self.min_interval=float(min_interval)
        self.max_retries=int(max_retries)
        self.last=0.0

    def _wait_interval(self):
        wait=self.min_interval-(time.monotonic()-self.last)
        if wait>0:
            time.sleep(wait)

    def _cache_path(self,alias,start,end,maxrecords):
        key=json.dumps(
            {
                "alias":alias,
                "start":pd.Timestamp(start).isoformat(),
                "end":pd.Timestamp(end).isoformat(),
                "maxrecords":int(maxrecords),
            },
            sort_keys=True,
        )
        h=hashlib.sha256(key.encode()).hexdigest()
        return self.cache_dir/h[:2]/f"{h}.json"

    def search(self,alias,start,end,maxrecords=250):
        cp=self._cache_path(alias,start,end,maxrecords)
        if cp.exists():
            return json.loads(cp.read_text(encoding="utf-8")), {
                "cache_hit":True,
                "attempts":0,
            }

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
        attempts=0
        for attempt in range(self.max_retries+1):
            attempts=attempt+1
            self._wait_interval()
            r=self.client.get(GDELT,params=params)
            self.last=time.monotonic()

            if r.status_code==429 or r.status_code in {500,502,503,504}:
                retry_after=r.headers.get("retry-after")
                try:
                    pause=float(retry_after) if retry_after else 30.0*(2**attempt)
                except Exception:
                    pause=30.0*(2**attempt)
                last_error=f"HTTP {r.status_code} retry_after={retry_after}"
                if attempt<self.max_retries:
                    time.sleep(max(pause,self.min_interval))
                    continue

            r.raise_for_status()
            payload=r.json()
            cp.parent.mkdir(parents=True,exist_ok=True)
            tmp=cp.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8")
            tmp.replace(cp)
            return payload, {
                "cache_hit":False,
                "attempts":attempts,
            }

        raise RuntimeError(last_error or "GDELT retry exhaustion")


def collect_window(client,alias,start,end,maxrecords=250,min_window_hours=24.0,depth=0,split_saturated=True):
    start=pd.Timestamp(start)
    end=pd.Timestamp(end)

    try:
        payload,meta=client.search(alias,start,end,maxrecords)
        arts=extract_articles(payload)
        status="OK"
        err=None
    except Exception as exc:
        arts=[]
        meta={"cache_hit":False,"attempts":client.max_retries+1}
        status="ERROR"
        err=f"{type(exc).__name__}: {exc}"

    saturated=(len(arts)>=maxrecords)
    hours=(end-start).total_seconds()/3600.0

    base_audit={
        "window_start":start,
        "window_end":end,
        "status":status,
        "articles":len(arts),
        "saturated":saturated,
        "depth":int(depth),
        "duration_hours":hours,
        "cache_hit":bool(meta.get("cache_hit")),
        "attempts":int(meta.get("attempts") or 0),
        "error":err,
    }

    if status!="OK":
        base_audit["terminal"]=True
        base_audit["split_reason"]=None
        return [],[base_audit]

    if split_saturated and saturated and hours>min_window_hours:
        base_audit["terminal"]=False
        base_audit["split_reason"]="MAXRECORDS_250"
        mid=start+(end-start)/2
        # One-second overlap prevents a boundary article from falling between
        # GDELT's strict after/before timestamp semantics. Canonical URL dedupe
        # removes any overlap duplicate later.
        left_end=min(end,mid+pd.Timedelta(seconds=1))
        right_start=max(start,mid-pd.Timedelta(seconds=1))
        left_rows,left_audit=collect_window(
            client,alias,start,left_end,maxrecords,min_window_hours,depth+1,split_saturated
        )
        right_rows,right_audit=collect_window(
            client,alias,right_start,end,maxrecords,min_window_hours,depth+1,split_saturated
        )
        return left_rows+right_rows,[base_audit]+left_audit+right_audit

    base_audit["terminal"]=True
    base_audit["split_reason"]="MIN_WINDOW_REACHED" if saturated else None
    return arts,[base_audit]

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
    ap.add_argument("--mode",choices=["smoke","full"],default="smoke")
    ap.add_argument("--min-request-interval",type=float,default=15.0)
    ap.add_argument("--cache-dir",default=DEFAULT_CACHE)
    ap.add_argument("--min-window-hours",type=float,default=24.0)
    ap.add_argument("--max-retries",type=int,default=None)
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
        start=pd.Timestamp("2023-07-01T00:00:00Z")
        end=pd.Timestamp("2026-09-02T13:30:00Z")

    effective_retries=(1 if args.mode=="smoke" else 3) if args.max_retries is None else args.max_retries
    client=GdeltClient(args.cache_dir,args.min_request_interval,max_retries=effective_retries)
    rows=[]
    query_audit=[]

    for sym in symbols:
        rr=reg.loc[reg["symbol"]==sym].iloc[0]
        alias=rr["query_alias"]
        for ws,we in month_windows(start,end):
            arts,audits=collect_window(
                client,
                alias,
                ws,
                we,
                maxrecords=250,
                min_window_hours=args.min_window_hours,
                split_saturated=(args.mode!="smoke"),
            )
            for qa in audits:
                qa.update({
                    "symbol":sym,
                    "company_name":rr["company_name"],
                    "query_alias":alias,
                    "root_window_start":ws,
                    "root_window_end":we,
                })
                query_audit.append(qa)

            terminal=[
                x for x in audits
                if x.get("terminal")
            ]
            terminal_sat=any(x.get("saturated") for x in terminal)
            terminal_err=any(x.get("status")!="OK" for x in terminal)

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
                    "query_saturated":terminal_sat,
                    "article_id":article_id(sym,url),
                })
            print(
                f"{sym} {ws.date()} articles={len(arts)} "
                f"leaf_queries={len(terminal)} terminal_error={terminal_err} "
                f"terminal_saturated={terminal_sat}",
                flush=True,
            )

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

    q_terminal=q.loc[q["terminal"].fillna(False).astype(bool)].copy()
    successful=q_terminal["status"].eq("OK")
    http_success=float(successful.mean()) if len(q_terminal) else 0.0
    saturated_ratio=float(q_terminal.loc[successful,"saturated"].mean()) if successful.any() else 1.0
    seen_ratio=float(d["available_at"].notna().mean()) if len(d) else 0.0
    url_ratio=float(d["canonical_url"].notna().mean()) if len(d) else 0.0
    dup_ratio=float((raw_rows-len(d))/raw_rows) if raw_rows else 0.0
    counts=d.groupby("symbol").size() if len(d) else pd.Series(dtype=int)
    symbols_ge20=int((counts>=20).sum())
    symbols_ge10=int((counts>=10).sum())
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
        next_action="DESIGN_HISTORICAL_BULK_SOURCE" if smoke_pass else "FIX_NEWS_DATA_READINESS"
    else:
        gates={
            "universe_is_93":len(reg)==93,
            "symbols_ge20_articles_ge_80":symbols_ge20>=80,
            "usable_span_months_ge_24":span_months>=24,
            "seendate_parse_ge_95pct":seen_ratio>=0.95,
            "canonical_url_ge_95pct":url_ratio>=0.95,
            "within_symbol_duplicate_ratio_le_5pct":dup_ratio<=0.05,
            "terminal_saturated_query_ratio_le_5pct":saturated_ratio<=0.05,
            "dedup_symbol_article_rows_ge_10000":len(d)>=10000,
        }
        smoke_pass=None
        ready=all(gates.values())
        next_action="PREREGISTER_SINGLE_R9_NEWS_ABLATION" if ready else "FIX_NEWS_DATA_READINESS"

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
        "terminal_query_windows":len(q_terminal),
        "http_success_ratio":http_success,
        "raw_symbol_article_rows":raw_rows,
        "dedup_symbol_article_rows":len(d),
        "within_symbol_duplicate_ratio":dup_ratio,
        "symbols_with_20plus_articles":symbols_ge20,
        "symbols_with_10plus_articles":symbols_ge10,
        "seendate_parse_ratio":seen_ratio,
        "canonical_url_ratio":url_ratio,
        "saturated_success_query_ratio":saturated_ratio,
        "usable_span_months":span_months,
        "smoke_quality_pass":smoke_pass,
        "gates":gates,
        "r9_news_ready":ready,
        "historical_model_fitting_allowed":bool(ready),
        "cache_dir":str(Path(args.cache_dir)),
        "min_request_interval_seconds":args.min_request_interval,
        "min_window_hours":args.min_window_hours,
        "max_retries":effective_retries,
        "adaptive_split_enabled":bool(args.mode!="smoke"),
        "next_action":next_action,
    }
    (out/f"manifest_{args.mode}.json").write_text(json.dumps(manifest,indent=2,default=str)+"\n")
    print(json.dumps(manifest,indent=2,default=str))
    print("ARTICLES=",out/f"articles_{args.mode}.parquet")
    print("AUDIT=",out/f"query_audit_{args.mode}.csv")
    print("MANIFEST=",out/f"manifest_{args.mode}.json")

if __name__=="__main__":
    main()
