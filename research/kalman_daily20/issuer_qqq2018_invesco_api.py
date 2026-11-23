#!/usr/bin/env python3
"""Original Invesco 2018 QQQ distribution API, read-only and fail-closed.

Use Invesco's KEYLESS JSON CDN for CUSIP 46090E103 (ISIN US46090E1038).
One modern API response is a current issuer *publication*, not a 2018
contemporaneous signed declaration, settlement ledger, split-factor proof,
or independent 16:00 close. Never alter Yahoo, Alpaca, prices or signals.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import gzip
from hashlib import sha256
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

VERSION="daily20-qqq2018-invesco-api-v1"
CUSIP="46090E103"
TARGET="2018-06-18"
PREFIX=("https://dng-api.invesco.com/cache/v1/accounts/en_US/"
        "shareclasses/46090E103/distribution")
URLS=(
    PREFIX+"?idType=cusip&productType=ETF&loadType=initial",
    PREFIX+"?productType=ETF&loadType=initial&idType=cusip",
)
ARCHIVE="qqq_2018_invesco_original_distribution_response.json.gz"
MAX_BYTES=2_000_000


def get_bytes(url):
    if url not in URLS:
        raise ValueError("INVESCO_SOURCE_URL_NOT_PINNED")
    req=Request(url,headers={
        "Accept":"application/json",
        "User-Agent":"KalmanDaily20ResearchEvidence/1.0 (+https://github.com/kimtk94/Codex)",
    })
    with urlopen(req,timeout=28) as resp:
        final=urlparse(resp.geturl())
        if final.scheme!="https" or final.hostname!="dng-api.invesco.com":
            raise ValueError("INVESCO_UNTRUSTED_REDIRECT")
        if resp.status != 200:
            raise ValueError("INVESCO_HTTP_NOT_200")
        raw=resp.read(MAX_BYTES+1)
    if not raw or len(raw)>MAX_BYTES:
        raise ValueError("INVESCO_SOURCE_EMPTY_OR_TOO_LARGE")
    return raw


def iso_date(value):
    if not isinstance(value,str):
        return None
    s=value.strip()
    for pattern in ("%Y-%m-%d","%Y-%m-%dT%H:%M:%S",
                    "%m/%d/%Y","%Y-%m-%dT%H:%M:%S.000Z"):
        try:
            return datetime.strptime(s,pattern).date().isoformat()
        except ValueError:
            pass
    return None


def usd_as_published(value):
    if value is None or value=="":
        return None
    try:
        d=Decimal(str(value).replace(",","").replace("$","").strip())
    except (InvalidOperation,TypeError,ValueError):
        return None
    return str(d) if d.is_finite() and d>=0 else None


def inspect(raw):
    obj=json.loads(raw.decode("utf-8-sig"))
    if not isinstance(obj,dict):
        raise ValueError("INVESCO_RESPONSE_NOT_OBJECT")
    if obj.get("cusip") not in (None,CUSIP):
        raise ValueError("INVESCO_PAYLOAD_CUSIP_MISMATCH")
    items=obj.get("distributions")
    if not isinstance(items,list):
        raise ValueError("INVESCO_DISTRIBUTIONS_MISSING")
    if len(items)>1000:
        raise ValueError("INVESCO_DISTRIBUTIONS_OVERSIZE")
    dates=[]
    hits=[]
    missing_date_rows=0
    for item in items:
        if not isinstance(item,dict):
            raise ValueError("INVESCO_DISTRIBUTION_ITEM_NOT_OBJECT")
        day=iso_date(item.get("exDate"))
        if day is None:
            missing_date_rows+=1
            continue
        dates.append(day)
        if day!=TARGET:
            continue
        amount=usd_as_published(item.get("distributionAmountPerUnit"))
        if amount is None:
            raise ValueError("INVESCO_2018_CASH_ABSENT_OR_INVALID")
        hits.append({
            "ex_date":day,
            "record_date":iso_date(item.get("recordDate")),
            "pay_date":iso_date(item.get("payDate")),
            "reported_distribution_amount_per_unit_usd":amount,
            "reported_ordinary_income_usd":usd_as_published(
                item.get("ordinaryIncomeDistribution")),
            "source_field":"distributionAmountPerUnit",
            "historical_payment_settlement_certified":False,
            "independent_adjustment_factor_certified":False,
        })
    if len(hits)>1:
        raise ValueError("INVESCO_DUPLICATE_2018_EVENT")
    return {
        "issuer_api_total_distribution_rows":len(items),
        "issuer_api_rows_with_valid_ex_date":len(dates),
        "issuer_api_rows_missing_ex_date":missing_date_rows,
        "issuer_api_historical_2018_row_count":sum(d.startswith("2018-") for d in dates),
        "issuer_api_target_row":hits[0] if hits else None,
        "issuer_api_date_coverage_min":min(dates) if dates else None,
        "issuer_api_date_coverage_max":max(dates) if dates else None,
        "issuer_api_payload_cusip_supplied":obj.get("cusip")==CUSIP,
    }


def status_code(exc):
    if isinstance(exc,HTTPError):
        return "HTTP_"+str(exc.code)
    if isinstance(exc,URLError):
        return "TRANSPORT_ERROR"
    if isinstance(exc,json.JSONDecodeError):
        return "INVALID_JSON"
    if isinstance(exc,UnicodeDecodeError):
        return "INVALID_UTF8"
    if isinstance(exc,ValueError):
        s=str(exc)
        if s.startswith("INVESCO_") and s.replace("_","").isalnum() and len(s)<80:
            return s
    return "UNCLASSIFIED_ERROR"


def collect(*,offline=False,getter=get_bytes,out_dir=None):
    r={
        "version":VERSION,
        "source_url_primary":URLS[0],
        "issuer":"Invesco",
        "fund":"QQQ", "cusip":CUSIP, "event_ex_date":TARGET,
        "research_only":True, "production_writes":False,
        "strategy_promoted":False,
        "source_finality_verified_assets":0,
        "issuer_2018_payment_settlement_certified":False,
        "issuer_2018_cash_finality_certified":False,
        "independent_factor_certified":False,
        "historical_nonpayment_proven":False,
        "source_history_completeness_certified":False,
        "source_share_unit_basis_certified":False,
        "issuer_api_payload_cusip_supplied":False,
        "status":"OFFLINE_ISSUER_JSON_UNFETCHED_HOLD" if offline
                 else "ISSUER_JSON_PENDING_HOLD",
        "used_source_url":None, "http_attempt_errors":[],
        "source_sha256":None, "source_archive":None, "source_bytes":None,
        "issuer_api_target_row":None,
        "fetch_or_schema_failure_code":None,
    }
    if offline:
        return r
    raw=None
    for url in URLS:
        try:
            raw=getter(url)
            r["used_source_url"]=url
            break
        except (HTTPError,URLError,ValueError,OSError,TimeoutError) as exc:
            code=status_code(exc)
            r["http_attempt_errors"].append(code)
            if code!="HTTP_406":
                break
    if raw is None:
        r["status"]="ISSUER_JSON_TRANSPORT_FAILED_HOLD"
        r["fetch_or_schema_failure_code"]=(
            r["http_attempt_errors"][-1] if r["http_attempt_errors"] else
            "NO_HTTP_ATTEMPTS")
        return r
    if not isinstance(raw,bytes) or not raw or len(raw)>MAX_BYTES:
        r["status"]="ISSUER_JSON_SOURCE_SIZE_INVALID_HOLD"
        r["fetch_or_schema_failure_code"]="INVESCO_SOURCE_EMPTY_OR_TOO_LARGE"
        return r
    r.update(source_sha256=sha256(raw).hexdigest(),source_bytes=len(raw))
    if out_dir is not None:
        folder=Path(out_dir)
        folder.mkdir(parents=True,exist_ok=True)
        (folder/ARCHIVE).write_bytes(gzip.compress(raw,mtime=0))
        r["source_archive"]=ARCHIVE
    try:
        observed=inspect(raw)
        r.update(observed)
        r["status"]=(
            "ISSUER_API_2018_EVENT_OBSERVED_CASH_FINALITY_HOLD"
            if observed["issuer_api_target_row"]
            else "ISSUER_API_2018_EVENT_NOT_IN_CURRENT_HISTORY_HOLD")
    except (ValueError,TypeError,UnicodeDecodeError) as exc:
        r["status"]="ISSUER_JSON_SCHEMA_REJECTED_RAW_ARCHIVED_HOLD"
        r["fetch_or_schema_failure_code"]=status_code(exc)
    return r


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--offline",action="store_true")
    p.add_argument("--out-dir",default="output/daily20/research/issuer_qqq2018_invesco")
    a=p.parse_args()
    r=collect(offline=a.offline,out_dir=a.out_dir)
    dest=Path(a.out_dir)/"report.json"
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("DAILY20_QQQ_ISSUER_API",r["status"],
          "target",r["issuer_api_target_row"],"failure",
          r["fetch_or_schema_failure_code"],"FINALITY 0/26 HOLD")

if __name__=="__main__":
    main()
