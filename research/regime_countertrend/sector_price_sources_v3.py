"""Frozen-date public market-data inventory for 24 US assets; 4 crypto separate.

Data provider can change historical OHLC. Save per-symbol exact-source digest,
open/high/low adjusted to adjusted-close basis, and fail closed on bad data.
No broker login, orders, LIVE, Neon, or crypto conversion.
"""
import argparse
import hashlib
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd

FROM_DATE="2017-01-01"
THROUGH_EXCLUSIVE="2026-11-11"
EXPECTED_LATEST="2026-11-10"

def manifest_load(path):
    info=json.loads(Path(path).read_text())
    u=info["universe"]
    symbols=[r["symbol"] for r in u]
    if len(symbols)!=28 or len(set(symbols))!=len(symbols):
        raise ValueError("universe must contain 28 unique symbols")
    stock=[r for r in u if r["asset_class"]=="STOCK"]
    etf=[r for r in u if r["asset_class"]=="ETF"]
    crypto=[r for r in u if r["asset_class"]=="CRYPTO"]
    if len(stock)!=14 or len(etf)!=10 or len(crypto)!=4:
        raise ValueError("unexpected 10 core, 4 auxiliary stocks, 10 ETF and 4 crypto")
    if any(r["model_eligible"]!=(r["asset_class"]=="STOCK") for r in u):
        raise ValueError("nonstock must never be trained as equity outcome")
    for r in crypto:
        if r["role"]!="separate_crypto_pipeline":
            raise ValueError("crypto exchange/currency separation missing")
    for r in etf:
        if r["role"] in ("target","auxiliary_comparison"):
            raise ValueError("ETF cannot be trained as a stock")
    return info

def parse_chart(raw,symbol):
    obj=json.loads(raw)
    block=obj["chart"]["result"][0]
    q=block["indicators"]["quote"][0]
    adj=block["indicators"].get("adjclose")
    if not adj or not adj[0].get("adjclose"):
        raise ValueError(f"{symbol} has no verified adjclose")
    ny=pd.to_datetime(block["timestamp"],unit="s",utc=True).tz_convert("America/New_York")
    d=pd.DataFrame({"date":ny.strftime("%Y-%m-%d"),
       "open":q["open"],"high":q["high"],"low":q["low"],
       "raw_close":q["close"],"volume":q["volume"],
       "adjclose":adj[0]["adjclose"]})
    d=d.dropna().sort_values("date")
    if d.date.duplicated().any() or len(d)<120:
        raise ValueError(f"{symbol} duplicate dates or fewer than 120 sessions")
    numeric=["open","high","low","raw_close","volume","adjclose"]
    if not np.isfinite(d[numeric].to_numpy(dtype=float)).all():
        raise ValueError(f"{symbol} nonfinite source")
    if (d[numeric[:-2]]<=0).any().any() or (d.adjclose<=0).any() or (d.volume<0).any():
        raise ValueError(f"{symbol} invalid source price/volume")
    factor=d.adjclose/d.raw_close
    d["close"]=d.adjclose
    for field in ("open","high","low"):
        d[field]=d[field]*factor
    if ((d.high<d[["open","close","low"]].max(axis=1)-1e-5)|
        (d.low>d[["open","close","high"]].min(axis=1)+1e-5)).any():
        raise ValueError(f"{symbol} OHLC invalid after adjusted-close conversion")
    d["adj_factor"]=factor
    return d[["date","open","high","low","close","volume","raw_close","adj_factor"]].reset_index(drop=True)

def fetch_symbol(symbol,from_date=FROM_DATE,until=THROUGH_EXCLUSIVE):
    start=int(pd.Timestamp(from_date,tz="UTC").timestamp())
    end=int(pd.Timestamp(until,tz="UTC").timestamp())
    query=urllib.parse.urlencode({
        "period1":start,"period2":end,"interval":"1d","events":"history"})
    errors=[]
    for host in ("query1.finance.yahoo.com","query2.finance.yahoo.com"):
        url=f"https://{host}/v8/finance/chart/{symbol}?{query}"
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req,timeout=22) as f:
                raw=f.read(3_000_000)
            frame=parse_chart(raw,symbol)
            return frame,{"status":"SOURCE_PASS",
              "provider":host,"sha256":hashlib.sha256(raw).hexdigest(),
              "first_date":frame.date.min(),"last_date":frame.date.max(),
              "rows":len(frame),"adjusted_basis":"adjclose OHLC ratio",
              "regular_prices_not_executable":True}
        except Exception as exc:
            errors.append({"host":host,"type":type(exc).__name__,"reason":str(exc)[:90]})
            time.sleep(.35)
    return None,{"status":"SOURCE_UNAVAILABLE","provider_attempts":errors}

def apply_ticker_trade_eligibility(frame,asset):
    """Strip predecessor/SPAC history before any features/labels are computed."""
    eligibility=asset.get("equity_ticker_first_trade")
    if not eligibility or frame is None:
        return frame,0
    filtered=frame.loc[frame.date>=eligibility].copy().reset_index(drop=True)
    if len(filtered)<120:
        raise ValueError(f"{asset['symbol']}: insufficient listed ticker history after {eligibility}")
    if not (filtered.date>=eligibility).all():
        raise ValueError("pre-listing data remains")
    return filtered,len(frame)-len(filtered)

def run_collection(manifest,output):
    folder=Path(output);folder.mkdir(parents=True,exist_ok=True)
    targets=[r for r in manifest["universe"] if r["asset_class"]!="CRYPTO"]
    status=[]
    for asset in targets:
        symbol=asset["symbol"]
        frame,meta=fetch_symbol(symbol)
        if frame is not None:
            frame,prelisting_removed=apply_ticker_trade_eligibility(frame,asset)
            meta["removed_pre_listing_rows"]=prelisting_removed
            meta["equity_ticker_first_trade"]=asset.get("equity_ticker_first_trade")
            meta["rows_after_eligibility"]=len(frame)
            meta["first_eligible_date"]=str(frame.date.min())
            if frame.date.max()<EXPECTED_LATEST:
                meta["status"]="STALE_SOURCE"
            elif len(frame[frame.date<"2025-01-01"])<100:
                meta["status"]="INSUFFICIENT_TRAIN_HISTORY"
            if meta["status"]=="SOURCE_PASS":
                frame.to_csv(folder/f"{symbol}.csv",index=False)
        status.append({"symbol":symbol,"kind":asset["asset_class"],
            "role":asset["role"],"industry":asset["industry"],**meta})
        print("SYMBOL_DATA",json.dumps(status[-1],ensure_ascii=False))
    results={"status":"PASS" if all(a["status"]=="SOURCE_PASS" for a in status) else "PARTIAL_SOURCE_HOLD",
       "stock_success":sum(x["status"]=="SOURCE_PASS" and x["kind"]=="STOCK" for x in status),
       "stock_requested":14,
       "etf_success":sum(x["status"]=="SOURCE_PASS" and x["kind"]=="ETF" for x in status),
       "etf_requested":10,
       "crypto_status":"OUT_OF_SCOPE_SEPARATE_PIPELINE",
       "fetched_at_utc":datetime.now(timezone.utc).isoformat(),
       "price_rows":status,
       "market_price_provenance":"PUBLIC_YAHOO_ADJUSTED_RETROSPECTIVE_NOT_POINT_IN_TIME",
       "promotion_allowed":False}
    (folder/"source_inventory.json").write_text(json.dumps(results,indent=2,ensure_ascii=False))
    return results

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--manifest",default="research/regime_countertrend/universe_sector_v3.json")
    p.add_argument("--out",default="results/regime_countertrend/universe_v3_prices")
    args=p.parse_args()
    manifest=manifest_load(args.manifest)
    outcome=run_collection(manifest,args.out)
    print("UNIVERSE_SOURCE_STATUS",json.dumps({k:v for k,v in outcome.items() if k!="price_rows"}))
