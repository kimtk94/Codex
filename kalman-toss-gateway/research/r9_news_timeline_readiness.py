from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

SCHEMA="kalman-r9-news-timeline-readiness-v1"
DEFAULT_EVENTS="/opt/kalman/state/r8_sec/events.json"
DEFAULT_R8_MANIFEST="/opt/kalman/state/r8_sec/manifest.json"
DEFAULT_OUT="/opt/kalman/state/r9_news_timeline"
DEFAULT_CACHE="/opt/kalman/state/r9_news_timeline/cache"
GDELT="https://api.gdeltproject.org/api/v2/doc/doc"

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

def clean_company_name(x):
    import re
    s=str(x or "").replace("&"," and ")
    s=re.sub(r"[^A-Za-z0-9. -]+"," ",s)
    s=re.sub(r"\s+"," ",s).strip(" .-")
    return s

def query_alias(company_name,symbol=None):
    import re
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
        uniq=sorted(
            set(names),
            key=lambda x:(-len(clean_company_name(x)),clean_company_name(x)),
        )
        name=uniq[0]
        reg.append({
            "symbol":sym,
            "company_name":name,
            "query_alias":query_alias(name,sym),
        })
    return pd.DataFrame(reg)

def select_smoke_symbols(reg):
    preferred=["AAPL","MSFT","NVDA","AMZN","META","GOOG","JPM","XOM","WMT","UNH"]
    have=set(reg["symbol"])
    got=[x for x in preferred if x in have]
    if len(got)<10:
        got += [x for x in reg["symbol"] if x not in got][:10-len(got)]
    return got[:10]

def parse_timeline(payload,symbol,company_name,alias):
    if not isinstance(payload,dict):
        return pd.DataFrame()

    series_list=payload.get("timeline")
    if not isinstance(series_list,list) or not series_list:
        return pd.DataFrame()

    primary=None
    for s in series_list:
        if isinstance(s,dict) and isinstance(s.get("data"),list):
            primary=s
            break
    if primary is None:
        return pd.DataFrame()

    series_name=str(primary.get("series") or "Volume Intensity")
    rows=[]
    for x in primary.get("data") or []:
        if not isinstance(x,dict):
            continue
        dt=pd.to_datetime(x.get("date"),utc=True,errors="coerce")
        value=pd.to_numeric(x.get("value"),errors="coerce")
        norm=pd.to_numeric(x.get("norm"),errors="coerce")
        if pd.isna(dt):
            continue
        share=(float(value)/float(norm)) if pd.notna(value) and pd.notna(norm) and float(norm)>0 else math.nan
        rows.append({
            "symbol":symbol,
            "company_name":company_name,
            "query_alias":alias,
            "date_utc":dt,
            "matched_articles":float(value) if pd.notna(value) else math.nan,
            "monitored_articles":float(norm) if pd.notna(norm) else math.nan,
            "coverage_share":share,
            "gdelt_series":series_name,
            "source":"GDELT_DOC_2_TIMELINEVOLRAW",
        })
    return pd.DataFrame(rows)

class TimelineClient:
    def __init__(self,cache_dir,min_interval=12.0,timeout=90,max_retries=2):
        self.client=httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent":"KalmanR9TimelineResearch/1.0"},
        )
        self.cache_dir=Path(cache_dir)
        self.cache_dir.mkdir(parents=True,exist_ok=True)
        self.min_interval=float(min_interval)
        self.max_retries=int(max_retries)
        self.last=0.0

    def _wait(self):
        wait=self.min_interval-(time.monotonic()-self.last)
        if wait>0:
            time.sleep(wait)

    def _cache_path(self,alias,start,end):
        raw=json.dumps(
            {"alias":alias,"start":str(start),"end":str(end),"mode":"timelinevolraw"},
            sort_keys=True,
        )
        h=hashlib.sha256(raw.encode()).hexdigest()
        return self.cache_dir/h[:2]/f"{h}.json"

    def fetch(self,alias,start,end):
        cp=self._cache_path(alias,start,end)
        if cp.exists():
            return json.loads(cp.read_text(encoding="utf-8")),True,0

        params={
            "query":f'\"{alias}\" sourcelang:english',
            "mode":"timelinevolraw",
            "format":"json",
            "startdatetime":pd.Timestamp(start).strftime("%Y%m%d%H%M%S"),
            "enddatetime":pd.Timestamp(end).strftime("%Y%m%d%H%M%S"),
        }

        last_error=None
        attempts=0
        for attempt in range(self.max_retries+1):
            attempts=attempt+1
            self._wait()
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
            return payload,False,attempts

        raise RuntimeError(last_error or "timeline retry exhaustion")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--events",default=DEFAULT_EVENTS)
    ap.add_argument("--r8-manifest",default=DEFAULT_R8_MANIFEST)
    ap.add_argument("--output-dir",default=DEFAULT_OUT)
    ap.add_argument("--cache-dir",default=DEFAULT_CACHE)
    ap.add_argument("--mode",choices=["smoke","full"],default="smoke")
    ap.add_argument("--min-request-interval",type=float,default=12.0)
    ap.add_argument("--max-retries",type=int,default=2)
    args=ap.parse_args()

    r8=json.loads(Path(args.r8_manifest).read_text())
    if r8.get("schema")!="kalman-r8-sec-corporate-events-v2" or not r8.get("sec_event_ready"):
        raise RuntimeError("R8 SEC v2 registry is not ready")

    reg=load_registry(args.events)
    if len(reg)!=93:
        raise RuntimeError(f"expected 93-symbol registry, got {len(reg)}")

    symbols=select_smoke_symbols(reg) if args.mode=="smoke" else reg["symbol"].tolist()
    start=pd.Timestamp("2023-07-01T00:00:00Z")
    end=pd.Timestamp("2026-09-02T00:00:00Z")

    client=TimelineClient(
        args.cache_dir,
        min_interval=args.min_request_interval,
        max_retries=args.max_retries,
    )

    audits=[]
    frames=[]

    for sym in symbols:
        rr=reg.loc[reg["symbol"]==sym].iloc[0]
        alias=rr["query_alias"]
        status="OK"
        error=None
        cache_hit=False
        attempts=0
        parsed=pd.DataFrame()

        try:
            payload,cache_hit,attempts=client.fetch(alias,start,end)
            parsed=parse_timeline(payload,sym,rr["company_name"],alias)
            if parsed.empty:
                status="PARSE_EMPTY"
        except Exception as exc:
            status="ERROR"
            error=f"{type(exc).__name__}: {exc}"

        if not parsed.empty:
            frames.append(parsed)

        audits.append({
            "symbol":sym,
            "company_name":rr["company_name"],
            "query_alias":alias,
            "status":status,
            "cache_hit":cache_hit,
            "attempts":attempts,
            "timeline_points":len(parsed),
            "first_date":parsed["date_utc"].min() if len(parsed) else pd.NaT,
            "last_date":parsed["date_utc"].max() if len(parsed) else pd.NaT,
            "error":error,
        })
        print(
            f"{sym} status={status} points={len(parsed)} "
            f"cache_hit={cache_hit} attempts={attempts}",
            flush=True,
        )

    audit=pd.DataFrame(audits)
    data=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame(
        columns=[
            "symbol","company_name","query_alias","date_utc",
            "matched_articles","monitored_articles","coverage_share",
            "gdelt_series","source",
        ]
    )

    if len(data):
        data=data.sort_values(["symbol","date_utc"]).reset_index(drop=True)

    out=Path(args.output_dir)
    out.mkdir(parents=True,exist_ok=True)
    reg.to_csv(out/"symbol_alias_registry.csv",index=False)
    audit.to_csv(out/f"audit_{args.mode}.csv",index=False)
    data.to_parquet(out/f"timeline_{args.mode}.parquet",index=False)

    request_success=float(audit["status"].ne("ERROR").mean()) if len(audit) else 0.0
    parse_success=float(audit["status"].eq("OK").mean()) if len(audit) else 0.0
    counts=data.groupby("symbol").size() if len(data) else pd.Series(dtype=int)
    symbols_ge300=int((counts>=300).sum())
    symbols_ge700=int((counts>=700).sum())

    norm_positive=float((data["monitored_articles"]>0).mean()) if len(data) else 0.0
    finite_share=float(
        pd.to_numeric(data["coverage_share"],errors="coerce").map(math.isfinite).mean()
    ) if len(data) else 0.0

    duplicates=int(data.duplicated(["symbol","date_utc"]).sum()) if len(data) else 0
    duplicate_ratio=float(duplicates/len(data)) if len(data) else 0.0

    dates=pd.to_datetime(data["date_utc"],utc=True,errors="coerce").dropna()
    span_months=(
        (dates.max()-dates.min()).total_seconds()/86400/30.4375
        if len(dates)>=2 else 0.0
    )

    if args.mode=="smoke":
        gates={
            "request_success_ge_90pct":request_success>=0.90,
            "timeline_parse_success_ge_90pct":parse_success>=0.90,
            "symbols_ge300_points_ge_9_of_10":symbols_ge300>=9,
            "monitored_articles_positive_ge_99pct":norm_positive>=0.99,
            "duplicate_symbol_date_zero":duplicates==0,
        }
        ready=False
        smoke_pass=all(gates.values())
        next_action="RUN_R9_TIMELINE_FULL" if smoke_pass else "FIX_R9_TIMELINE_SOURCE"
    else:
        gates={
            "universe_is_93":len(reg)==93,
            "request_success_ge_90pct":request_success>=0.90,
            "timeline_parse_success_ge_90pct":parse_success>=0.90,
            "symbols_ge700_points_ge_80":symbols_ge700>=80,
            "usable_span_months_ge_24":span_months>=24,
            "monitored_articles_positive_ge_99pct":norm_positive>=0.99,
            "finite_coverage_share_ge_99pct":finite_share>=0.99,
            "duplicate_symbol_date_zero":duplicates==0,
        }
        smoke_pass=None
        ready=all(gates.values())
        next_action="PREREGISTER_SINGLE_R9_TIMELINE_ABLATION" if ready else "FIX_R9_TIMELINE_SOURCE"

    manifest={
        "schema":SCHEMA,
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "research_only":True,
        "production_changed":False,
        "model_fitting_allowed":False,
        "source":"GDELT_DOC_2_TIMELINEVOLRAW",
        "mode":args.mode,
        "historical_start_utc":start.isoformat(),
        "historical_end_exclusive_utc":end.isoformat(),
        "pit_contract":"for any hourly signal, use only timeline dates strictly earlier than signal_as_of UTC date",
        "universe_symbols":len(reg),
        "query_symbols":len(symbols),
        "request_success_ratio":request_success,
        "timeline_parse_success_ratio":parse_success,
        "timeline_rows":len(data),
        "symbols_ge300_points":symbols_ge300,
        "symbols_ge700_points":symbols_ge700,
        "monitored_articles_positive_ratio":norm_positive,
        "finite_coverage_share_ratio":finite_share,
        "duplicate_symbol_date_rows":duplicates,
        "duplicate_symbol_date_ratio":duplicate_ratio,
        "usable_span_months":span_months,
        "cache_hits":int(audit["cache_hit"].fillna(False).astype(bool).sum()) if len(audit) else 0,
        "min_request_interval_seconds":args.min_request_interval,
        "max_retries":args.max_retries,
        "smoke_quality_pass":smoke_pass,
        "gates":gates,
        "r9_timeline_ready":ready,
        "next_action":next_action,
    }
    (out/f"manifest_{args.mode}.json").write_text(
        json.dumps(manifest,indent=2,default=str)+"\n"
    )
    print(json.dumps(manifest,indent=2,default=str))
    print("TIMELINE=",out/f"timeline_{args.mode}.parquet")
    print("AUDIT=",out/f"audit_{args.mode}.csv")
    print("MANIFEST=",out/f"manifest_{args.mode}.json")

if __name__=="__main__":
    main()
