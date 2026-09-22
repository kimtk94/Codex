from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
import math
import os
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import HashingVectorizer

SCHEMA="kalman-r9-sec-text-readiness-v1"
DEFAULT_EVENTS="/opt/kalman/state/r8_sec/events.json"
DEFAULT_R8_MANIFEST="/opt/kalman/state/r8_sec/manifest.json"
DEFAULT_OUT="/opt/kalman/state/r9_sec_text"
DEFAULT_CACHE="/opt/kalman/state/r9_sec_text/cache"

SEMANTIC_ITEMS={
    "1.01":"MATERIAL_AGREEMENT",
    "2.01":"ACQUISITION_DISPOSITION",
    "2.02":"EARNINGS_RESULTS",
    "2.03":"FINANCING_OBLIGATION",
    "3.02":"FINANCING_OBLIGATION",
    "3.01":"DELISTING_COMPLIANCE",
    "2.05":"RESTRUCTURING_IMPAIRMENT",
    "2.06":"RESTRUCTURING_IMPAIRMENT",
    "5.02":"MANAGEMENT_BOARD",
    "7.01":"REG_FD",
    "8.01":"OTHER_EVENT",
}
PRIMARY_PRIORITY=[
    "EARNINGS_RESULTS",
    "ACQUISITION_DISPOSITION",
    "MATERIAL_AGREEMENT",
    "FINANCING_OBLIGATION",
    "RESTRUCTURING_IMPAIRMENT",
    "MANAGEMENT_BOARD",
    "REG_FD",
    "OTHER_EVENT",
    "DELISTING_COMPLIANCE",
]

ITEM_RE=re.compile(r"(?i)\bITEM\s+([1-9]\.\d{2})\b")
NUM_TOKEN_RE=re.compile(r"(?<![A-Za-z])[-+]?\d[\d,]*(?:\.\d+)?%?")
WS_RE=re.compile(r"\s+")

class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[]
        self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag.lower() in {"script","style","svg","noscript","ix:hidden","ix:header"}:
            self.skip+=1
    def handle_endtag(self,tag):
        if tag.lower() in {"script","style","svg","noscript","ix:hidden","ix:header"} and self.skip:
            self.skip-=1
    def handle_data(self,data):
        if not self.skip and data:
            self.parts.append(data)

def clean_html_text(raw:str)->str:
    p=TextExtractor()
    try:
        p.feed(raw)
        txt=" ".join(p.parts)
    except Exception:
        txt=re.sub(r"<[^>]+>"," ",raw)
    txt=html.unescape(txt)
    return WS_RE.sub(" ",txt).strip()

def semantic_items_from_event(e):
    return sorted({x for x in (e.get("items") or []) if x in SEMANTIC_ITEMS})

def primary_bucket(e):
    buckets=set(e.get("event_buckets") or [])
    for b in PRIMARY_PRIORITY:
        if b in buckets:
            return b
    return None

def extract_item_sections(text,target_items):
    hits=list(ITEM_RE.finditer(text))
    if not hits:
        return "", []
    candidates={}
    for i,m in enumerate(hits):
        code=m.group(1)
        if code not in target_items:
            continue
        end=hits[i+1].start() if i+1<len(hits) else len(text)
        seg=text[m.start():end].strip()
        if len(seg)<80:
            continue
        candidates.setdefault(code,[]).append(seg)

    chosen=[]
    found=[]
    for code in sorted(candidates):
        # Prefer the longest occurrence to avoid table-of-contents/reference snippets.
        seg=max(candidates[code],key=len)
        chosen.append(seg)
        found.append(code)
    return "\n\n".join(chosen).strip(), found

def cache_key(url):
    return hashlib.sha256(url.encode()).hexdigest()

def cache_path(cache_root,url):
    k=cache_key(url)
    return Path(cache_root)/k[:2]/f"{k}.json.gz"

def read_cache(path):
    if not path.exists():
        return None
    with gzip.open(path,"rt",encoding="utf-8") as f:
        return json.load(f)

def write_cache(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    with gzip.open(tmp,"wt",encoding="utf-8") as f:
        json.dump(obj,f,ensure_ascii=False)
    tmp.replace(path)

EMAIL_RE=re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def declared_sec_identity():
    email=str(os.environ.get("SEC_CONTACT_EMAIL") or "").strip()
    org=str(os.environ.get("SEC_ORG_NAME") or "Kalman Research").strip()
    if not EMAIL_RE.match(email):
        raise RuntimeError(
            "SEC_CONTACT_EMAIL must be a real contact email for declared automated access; "
            "do not use a URL-only User-Agent"
        )
    ua=str(os.environ.get("SEC_USER_AGENT") or f"{org} {email}").strip()
    if email.lower() not in ua.lower():
        ua=f"{ua} {email}"
    return ua,email

class SecDocClient:
    def __init__(self,user_agent,contact_email,min_interval=0.35,timeout=30):
        self.client=httpx.Client(
            timeout=timeout,
            headers={
                "User-Agent":user_agent,
                "From":contact_email,
                "Accept-Encoding":"gzip, deflate",
                "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Host":"www.sec.gov",
            },
            follow_redirects=True,
        )
        self.min_interval=float(min_interval)
        self.last=0.0
    def get_text(self,url):
        wait=self.min_interval-(time.monotonic()-self.last)
        if wait>0:
            time.sleep(wait)
        r=self.client.get(url)
        self.last=time.monotonic()
        if r.status_code >= 400:
            body=WS_RE.sub(" ",r.text or "")[:800]
            raise RuntimeError(
                f"SEC_HTTP_{r.status_code} url={url} "
                f"content_type={r.headers.get('content-type')} "
                f"retry_after={r.headers.get('retry-after')} "
                f"body={body}"
            )
        if len(r.content)>25_000_000:
            raise RuntimeError("document_too_large_gt_25mb")
        return r.text

def fetch_extract_one(client,event,cache_root):
    url=event.get("primary_url")
    if not url:
        return {"status":"NO_PRIMARY_URL"}
    cp=cache_path(cache_root,url)
    cached=read_cache(cp)
    if cached is not None:
        return cached

    try:
        raw=client.get_text(url)
        cleaned=clean_html_text(raw)
        target=semantic_items_from_event(event)
        semantic_text,found=extract_item_sections(cleaned,set(target))
        result={
            "status":"OK",
            "url":url,
            "cleaned_text_chars":len(cleaned),
            "semantic_text":semantic_text,
            "semantic_text_chars":len(semantic_text),
            "target_items":target,
            "found_items":found,
            "semantic_extract_ok":bool(semantic_text),
            "cleaned_sha256":hashlib.sha256(cleaned.encode()).hexdigest(),
            "semantic_sha256":hashlib.sha256(semantic_text.encode()).hexdigest() if semantic_text else None,
        }
        write_cache(cp,result)
        return result
    except Exception as exc:
        return {
            "status":"ERROR",
            "url":url,
            "error":f"{type(exc).__name__}: {exc}",
        }

def numeric_token_ratio(text):
    toks=text.split()
    if not toks:
        return np.nan
    return float(len(NUM_TOKEN_RE.findall(text))/len(toks))

def add_novelty(df):
    v=HashingVectorizer(
        n_features=2**18,
        alternate_sign=False,
        norm="l2",
        lowercase=True,
        stop_words="english",
        ngram_range=(1,2),
        analyzer="word",
    )
    df=df.copy()
    df["novelty_prev_symbol"]=np.nan
    df["novelty_prev_primary_bucket"]=np.nan
    prev_symbol={}
    prev_bucket={}
    for idx,row in df.sort_values(["acceptance_at","symbol","accession_number"]).iterrows():
        text=row["semantic_text"]
        if not isinstance(text,str) or not text:
            continue
        vec=v.transform([text])
        sym=row["symbol"]
        bucket=row["primary_bucket"]
        if sym in prev_symbol:
            sim=float(vec.multiply(prev_symbol[sym]).sum())
            df.at[idx,"novelty_prev_symbol"]=float(np.clip(1.0-sim,0.0,2.0))
        key=(sym,bucket)
        if bucket and key in prev_bucket:
            sim=float(vec.multiply(prev_bucket[key]).sum())
            df.at[idx,"novelty_prev_primary_bucket"]=float(np.clip(1.0-sim,0.0,2.0))
        prev_symbol[sym]=vec
        if bucket:
            prev_bucket[key]=vec
    return df

def select_smoke_urls(events,max_docs):
    if max_docs<=0:
        return []
    # Deterministic diversity-first smoke: first usable URL from each symbol,
    # then fill remaining slots from the global chronological pool.
    selected=[]
    seen=set()
    ordered=sorted(
        events,
        key=lambda e:(str(e.get("symbol") or ""),str(e.get("acceptance_at") or ""),str(e.get("primary_url") or "")),
    )
    for e in ordered:
        sym=str(e.get("symbol") or "")
        url=e.get("primary_url")
        if not url or sym in seen:
            continue
        selected.append(url)
        seen.add(sym)
        if len(selected)>=max_docs:
            return selected
    for e in sorted(events,key=lambda e:(str(e.get("acceptance_at") or ""),str(e.get("primary_url") or ""))):
        url=e.get("primary_url")
        if url and url not in selected:
            selected.append(url)
            if len(selected)>=max_docs:
                break
    return selected


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--events",default=DEFAULT_EVENTS)
    ap.add_argument("--r8-manifest",default=DEFAULT_R8_MANIFEST)
    ap.add_argument("--output-dir",default=DEFAULT_OUT)
    ap.add_argument("--cache-dir",default=DEFAULT_CACHE)
    ap.add_argument("--min-request-interval",type=float,default=0.35)
    ap.add_argument("--max-documents",type=int,default=0)
    args=ap.parse_args()

    r8=json.loads(Path(args.r8_manifest).read_text())
    if r8.get("schema")!="kalman-r8-sec-corporate-events-v2":
        raise RuntimeError(f"unexpected R8 schema: {r8.get('schema')}")
    if not r8.get("sec_event_ready"):
        raise RuntimeError("R8 SEC v2 readiness is not PASS")

    raw=json.loads(Path(args.events).read_text())
    semantic=[]
    for e in raw:
        target=semantic_items_from_event(e)
        if not target:
            continue
        if not e.get("primary_url"):
            continue
        x=dict(e)
        x["_target_semantic_items"]=target
        semantic.append(x)

    all_unique_urls=sorted({e["primary_url"] for e in semantic})
    if len(all_unique_urls)<7000:
        raise RuntimeError(f"unexpectedly low unique semantic URLs before fetch: {len(all_unique_urls)}")
    smoke_mode=args.max_documents>0
    unique_urls=(
        select_smoke_urls(semantic,args.max_documents)
        if smoke_mode else all_unique_urls
    )

    user_agent,contact_email=declared_sec_identity()
    client=SecDocClient(
        user_agent,
        contact_email,
        args.min_request_interval,
    )

    by_url={}
    total=len(unique_urls)
    first_event_by_url={}
    for e in semantic:
        first_event_by_url.setdefault(e["primary_url"],e)

    for i,url in enumerate(unique_urls,1):
        e=first_event_by_url[url]
        res=fetch_extract_one(client,e,args.cache_dir)
        by_url[url]=res
        if i%100==0 or i==total:
            print(f"[{i}/{total}] {res.get('status')} {e.get('symbol')} {e.get('accession_number')}",flush=True)

    selected_urls=set(unique_urls)
    rows=[]
    for e in semantic:
        if e["primary_url"] not in selected_urls:
            continue
        res=by_url[e["primary_url"]]
        accepted=pd.to_datetime(e.get("acceptance_at"),utc=True,errors="coerce")
        rows.append({
            "symbol":str(e.get("symbol") or "").upper(),
            "accession_number":e.get("accession_number"),
            "form":e.get("form"),
            "acceptance_at":accepted,
            "available_at":accepted+pd.to_timedelta(5,unit="m") if pd.notna(accepted) else pd.NaT,
            "primary_url":e.get("primary_url"),
            "primary_bucket":primary_bucket(e),
            "event_buckets_json":json.dumps(e.get("event_buckets") or []),
            "target_items_json":json.dumps(e.get("_target_semantic_items") or []),
            "fetch_status":res.get("status"),
            "cleaned_text_chars":res.get("cleaned_text_chars"),
            "semantic_text_chars":res.get("semantic_text_chars"),
            "found_items_json":json.dumps(res.get("found_items") or []),
            "semantic_extract_ok":bool(res.get("semantic_extract_ok")),
            "semantic_sha256":res.get("semantic_sha256"),
            "semantic_text":res.get("semantic_text") or "",
            "fetch_error":res.get("error"),
        })

    df=pd.DataFrame(rows)
    df["semantic_text_chars_log1p"]=np.log1p(pd.to_numeric(df["semantic_text_chars"],errors="coerce").fillna(0))
    df["numeric_token_ratio"]=[
        numeric_token_ratio(x) if isinstance(x,str) and x else np.nan
        for x in df["semantic_text"]
    ]
    df=add_novelty(df)

    out=Path(args.output_dir)
    out.mkdir(parents=True,exist_ok=True)
    df.to_parquet(out/"documents.parquet",index=False)

    unique_status=pd.DataFrame([
        {
            "url":u,
            "status":r.get("status"),
            "cleaned_text_chars":r.get("cleaned_text_chars"),
            "semantic_extract_ok":bool(r.get("semantic_extract_ok")),
            "semantic_text_chars":r.get("semantic_text_chars"),
        }
        for u,r in by_url.items()
    ])

    uniq_n=len(unique_status)
    fetched=int((unique_status["status"]=="OK").sum())
    parsed=int(((unique_status["status"]=="OK") & (pd.to_numeric(unique_status["cleaned_text_chars"],errors="coerce")>0)).sum())
    extracted=int(unique_status["semantic_extract_ok"].sum())

    usable=df.loc[df["semantic_extract_ok"] & (df["semantic_text_chars"]>=80)].copy()
    per_symbol=usable.groupby("symbol").size()
    symbols_ge20=int((per_symbol>=20).sum())
    times=pd.to_datetime(usable["acceptance_at"],utc=True,errors="coerce").dropna()
    span_months=((times.max()-times.min()).total_seconds()/86400/30.4375 if len(times)>=2 else 0.0)

    by_symbol_nonfirst=usable.sort_values(["symbol","acceptance_at"]).copy()
    by_symbol_nonfirst["_ord"]=by_symbol_nonfirst.groupby("symbol").cumcount()
    eligible_prev=by_symbol_nonfirst["_ord"]>0
    novelty_cov=float(
        by_symbol_nonfirst.loc[eligible_prev,"novelty_prev_symbol"].notna().mean()
    ) if eligible_prev.any() else 0.0

    gates={
        "r8_sec_v2_ready":bool(r8.get("sec_event_ready")),
        "unique_semantic_documents_ge_7000":(len(all_unique_urls)>=7000 and not smoke_mode),
        "unique_fetch_success_ge_95pct":(fetched/uniq_n if uniq_n else 0)>=0.95,
        "cleaned_text_parse_ge_95pct":(parsed/fetched if fetched else 0)>=0.95,
        "semantic_section_extract_ge_75pct":(extracted/fetched if fetched else 0)>=0.75,
        "usable_event_rows_ge_5000":len(usable)>=5000,
        "symbols_ge20_usable_ge_80":symbols_ge20>=80,
        "usable_span_months_ge_24":span_months>=24,
        "novelty_prev_symbol_coverage_ge_90pct":novelty_cov>=0.90,
    }

    manifest={
        "schema":SCHEMA,
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "research_only":True,
        "production_changed":False,
        "model_fitting_allowed":False,
        "api_key_required":False,
        "source":"SEC_PRIMARY_8K_DOCUMENTS",
        "sec_user_agent":user_agent,
        "sec_contact_email_sha256":hashlib.sha256(contact_email.lower().encode()).hexdigest(),
        "declared_automated_access":True,
        "request_interval_seconds":args.min_request_interval,
        "r8_manifest_schema":r8.get("schema"),
        "mode":"smoke" if smoke_mode else "full",
        "max_documents":args.max_documents,
        "all_unique_semantic_documents":len(all_unique_urls),
        "semantic_event_rows":len(df),
        "unique_semantic_documents":uniq_n,
        "unique_fetch_success":fetched,
        "unique_fetch_success_ratio":fetched/uniq_n if uniq_n else 0.0,
        "cleaned_text_parse_success":parsed,
        "cleaned_text_parse_ratio":parsed/fetched if fetched else 0.0,
        "semantic_section_extract_success":extracted,
        "semantic_section_extract_ratio":extracted/fetched if fetched else 0.0,
        "usable_event_rows":int(len(usable)),
        "symbols_with_20plus_usable":symbols_ge20,
        "usable_first_acceptance_at":times.min().isoformat() if len(times) else None,
        "usable_last_acceptance_at":times.max().isoformat() if len(times) else None,
        "usable_span_months":span_months,
        "novelty_prev_symbol_coverage":novelty_cov,
        "hashing_vectorizer":{
            "n_features":2**18,
            "alternate_sign":False,
            "norm":"l2",
            "lowercase":True,
            "stop_words":"english",
            "ngram_range":[1,2],
        },
        "gates":gates,
        "r9_text_ready":bool((not smoke_mode) and all(gates.values())),
        "smoke_quality_pass":bool(
            smoke_mode
            and (fetched/uniq_n if uniq_n else 0)>=0.95
            and (parsed/fetched if fetched else 0)>=0.95
            and (extracted/fetched if fetched else 0)>=0.75
        ),
        "next_action":(
            (
                "RUN_FULL_READINESS"
                if (
                    (fetched/uniq_n if uniq_n else 0)>=0.95
                    and (parsed/fetched if fetched else 0)>=0.95
                    and (extracted/fetched if fetched else 0)>=0.75
                )
                else "FIX_TEXT_EXTRACTION_BEFORE_FULL"
            )
            if smoke_mode
            else ("PREREGISTER_SINGLE_R9_TEXT_ABLATION" if all(gates.values()) else "FIX_TEXT_DATA_READINESS_ONLY")
        ),
    }
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2,default=str)+"\n")
    print(json.dumps(manifest,indent=2,default=str))
    print("DOCUMENTS=",out/"documents.parquet")
    print("MANIFEST=",out/"manifest.json")

if __name__=="__main__":
    main()
