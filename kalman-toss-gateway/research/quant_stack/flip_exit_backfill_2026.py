"""Read-only Alpaca 5-minute SIP backfill for frozen 2026 historical trade entries.

No production DB writes, no order API calls, no secret output. Historical SIP
access is probed before download. Each trade is independently cached, so a
terminated run can resume. The source ledger is preserved verbatim.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, time, timezone
from pathlib import Path
import gzip
import json
import sys
import os
import time as walltime
from zoneinfo import ZoneInfo

import requests

NY = ZoneInfo("America/New_York")
ROOT = Path(os.environ.get("KALMAN_FLIP_RESEARCH_ROOT", "/home/taehoon/kalman-data/trading/research_flip_2026"))
SOURCE_ENV = Path(os.environ.get("KALMAN_RESEARCH_ENV_FILE", "/home/taehoon/Codex/kalman-toss-gateway/.env"))
URL = "https://data.alpaca.markets/v2/stocks/{symbol}/bars"


def load_creds():
    values = {}
    for line in SOURCE_ENV.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        if k in ("ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY"):
            values[k] = v.strip().strip("'").strip('"')
    if not values.get("ALPACA_API_KEY_ID") or not values.get("ALPACA_API_SECRET_KEY"):
        raise ValueError("Credentials absent from existing research source")
    return {"APCA-API-KEY-ID": values["ALPACA_API_KEY_ID"],
            "APCA-API-SECRET-KEY": values["ALPACA_API_SECRET_KEY"]}


def parse_ts(v):
    return datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(timezone.utc)


def effective_hour_end(v):
    local = parse_ts(v).astimezone(NY)
    day_close = datetime.combine(local.date(), time(16, 0), NY)
    return min(local + timedelta(hours=1), day_close).astimezone(timezone.utc)


def request_bars(session, symbol, start, end, feed, headers):
    bars = []
    token = None
    for _page in range(12):
        params = {"timeframe": "5Min", "start": start.isoformat(),
                  "end": end.isoformat(), "limit": 10000,
                  "feed": feed, "adjustment": "raw", "sort": "asc"}
        if token:
            params["page_token"] = token
        for attempt in range(4):
            try:
                response = session.get(URL.format(symbol=symbol), params=params,
                                       headers=headers, timeout=28)
                if response.status_code in (429, 500, 502, 503):
                    walltime.sleep(3.5 * (attempt + 1))
                    continue
                if response.status_code != 200:
                    return {"status":"HTTP_ERROR", "code":response.status_code,
                            "error":response.text[:120], "bars":[]}
                data = response.json()
                bars.extend(data.get("bars") or [])
                token = data.get("next_page_token")
                break
            except requests.RequestException:
                if attempt == 3:
                    return {"status":"NETWORK_ERROR", "bars":[]}
                walltime.sleep(3 * (attempt+1))
        else:
            return {"status":"RETRY_EXHAUSTED", "bars":[]}
        if not token:
            break
    return {"status":"PASS" if bars else "EMPTY","bars":bars, "pages_truncated":bool(token)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--feed", choices=["sip", "iex"], default="sip")
    p.add_argument("--max-trades", type=int, default=0)
    p.add_argument("--limit-rpm", type=float, default=115)
    args = p.parse_args()
    ledger = json.loads((ROOT/"neon_251_snapshot.json").read_text())["rows"]
    ledger = ledger[:args.max_trades or len(ledger)]
    out = ROOT/"cache_5min"/args.feed
    out.mkdir(parents=True, exist_ok=True)
    headers = load_creds()
    session = requests.Session()
    records = []
    fetched = 0
    for index, trade in enumerate(ledger,1):
        tid = trade["trade_id"]
        outfile = out/(tid+".json.gz")
        if outfile.is_file():
            with gzip.open(outfile, "rt") as h:
                record = json.load(h)
            records.append({"trade_id":tid,"symbol":trade["symbol"],
                           "status":record.get("status"),
                           "bars":len(record.get("bars",[])),"cached":True})
            continue
        start = effective_hour_end(trade["entry_time"]) - timedelta(minutes=15)
        end = effective_hour_end(trade["exit_time"]) + timedelta(minutes=15)
        if end <= start:
            records.append({"trade_id":tid,"symbol":trade["symbol"],"status":"BAD_WINDOW"})
            continue
        fetched += 1
        result = request_bars(session,trade["symbol"],start,end,args.feed,headers)
        result.update({"trade_id":tid,"symbol":trade["symbol"],"start":start.isoformat(),
                       "end":end.isoformat(),"feed":args.feed})
        with gzip.open(outfile, "wt") as h:
            json.dump(result,h,separators=(",",":"))
        records.append({"trade_id":tid,"symbol":trade["symbol"],
                        "status":result.get("status"),"bars":len(result.get("bars",[]))})
        if index % 15 == 0 or index == len(ledger):
            print(json.dumps({"progress":index,"total":len(ledger),"fetched":fetched,
                              "pass":sum(r["status"]=="PASS" for r in records),
                              "empty":sum(r["status"]=="EMPTY" for r in records),
                              "errors":sum(r["status"] not in ("PASS","EMPTY") for r in records)}),
                  flush=True)
        walltime.sleep(60/max(args.limit_rpm,1))
    status = ROOT/("alpaca_"+args.feed+"_backfill_audit.json")
    status.write_text(json.dumps({"feed":args.feed,"total":len(ledger),
                                  "source":"Alpaca historical SIP 5Min raw",
                                  "data":records},indent=2)+"\n")
    print(json.dumps({"final":True,"total":len(ledger),
                      "passed":sum(r["status"]=="PASS" for r in records),
                      "empty":sum(r["status"]=="EMPTY" for r in records),
                      "failed":sum(r["status"] not in ("PASS","EMPTY") for r in records),
                      "audit":str(status)}),flush=True)


if __name__=="__main__":
    main()
