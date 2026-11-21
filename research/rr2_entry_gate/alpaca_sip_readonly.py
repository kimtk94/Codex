#!/usr/bin/env python3
"""Alpaca historical-data GET-only SIP reader; emits raw bars to temporary CI file."""
from __future__ import annotations
import argparse,json,os,time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError

ENDPOINT="https://data.alpaca.markets/v2/stocks/COIN/bars"

def fetch(*,key,secret,start,end,max_pages=160):
    if not key or not secret:
        raise RuntimeError("SIP_READ_BLOCKED_MISSING_CREDENTIALS")
    seen=set();token=None;bars=[]
    for page in range(max_pages):
        args={"timeframe":"15Min","feed":"sip","adjustment":"all",
              "start":start,"end":end,"limit":10000,"sort":"asc"}
        if token: args["page_token"]=token
        req=Request(ENDPOINT+"?"+urlencode(args),headers={
            "APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret,
            "Accept":"application/json"},method="GET")
        payload=None
        for attempt in range(4):
            try:
                with urlopen(req,timeout=35) as response:
                    payload=json.load(response)
                break
            except HTTPError as exc:
                if exc.code not in (429,500,502,503,504) or attempt==3:
                    raise RuntimeError("HISTORICAL_SIP_HTTP_"+str(exc.code)) from None
            except (URLError,TimeoutError):
                if attempt==3: raise RuntimeError("HISTORICAL_SIP_NETWORK_FAILED") from None
            time.sleep(min(2**attempt,6))
        if not isinstance(payload,dict) or not isinstance(payload.get("bars"),list):
            raise RuntimeError("HISTORICAL_SIP_SCHEMA_INVALID")
        new_rows=payload["bars"]
        if not new_rows and payload.get("next_page_token"):
            raise RuntimeError("SIP_EMPTY_PAGE_WITH_CONTINUATION")
        bars.extend(new_rows)
        new_token=payload.get("next_page_token")
        if not new_token: return bars
        if new_token in seen: raise RuntimeError("SIP_PAGINATION_LOOP")
        seen.add(new_token);token=new_token
    raise RuntimeError("SIP_PAGE_LIMIT_EXCEEDED_160_CHECK_FETCH_ENTITLEMENT_AND_LIMIT")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--start",default="2024-01-01T00:00:00Z")
    p.add_argument("--end",default="2026-10-31T00:00:00Z")
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    if a.end<=a.start: p.error("end must exceed start")
    bars=fetch(key=os.getenv("ALPACA_API_KEY_ID") or os.getenv("APCA_API_KEY_ID",""),
               secret=os.getenv("ALPACA_API_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY",""),
               start=a.start,end=a.end)
    if len(bars)<5000: raise RuntimeError("SIP_INCOMPLETE_OR_WRONG_ENTITLEMENT")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(bars,separators=(",",":")),encoding="utf-8")
    print(json.dumps({"status":"PRIVATE_SIP_READ_COMPLETE","bars":len(bars),
                      "feed":"sip","timeframe":"15Min","adjustment":"all",
                      "license_sensitive_not_uploaded":True}))

if __name__=="__main__":main()
