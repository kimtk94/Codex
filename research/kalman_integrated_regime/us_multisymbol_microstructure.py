#!/usr/bin/env python3
"""Reusable read-only U.S. stock/ETF SIP volume and quote-side research.

Symbol universe comes from the versioned Kalman market-data config. Indices,
FX, crypto and Korean exchanges are intentionally excluded from this adapter.
The remote probe uses only 10 historical seconds per symbol and publishes
derived aggregates, never raw SIP prints / quotes / secrets.

This is NOT live execution and never modifies existing signal models.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

import exchange_calendars as xcals
import numpy as np
import pandas as pd
import requests

from research.kalman_integrated_regime.sip_quote_aggressor_probe import (
    TRADE_START, TRADE_END, QUOTE_START, QUOTE_END,
    fetch as fetch_prints_or_quotes, classify as classify_aggressor,
)

MANIFEST = Path("kalman-toss-gateway/config/market-data-v2-universe.json")
# Existing dedicated QLD SIP-research asset is not in the market-data-v2
# universe. QQQ is, and QLD must be explicitly opted in as a research asset.
EXTRA_RESEARCH_SYMBOLS = frozenset(("QLD",))
PROBE_DEFAULT = "SPY,IWM,SMH,MU,COIN"
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")
NY = "America/New_York"


def approved_us_symbols(path=MANIFEST):
    manifest = json.loads(Path(path).read_text())
    candidates = set(EXTRA_RESEARCH_SYMBOLS)
    for record in manifest["assets"]:
        if (record.get("market") == "US"
                and record.get("kind") in ("equity","etf")
                and record.get("provider") == "yfinance"):
            symbol = record.get("provider_symbol")
            if isinstance(symbol,str) and SYMBOL_RE.fullmatch(symbol):
                candidates.add(symbol)
    return tuple(sorted(candidates))


def select_symbols(raw, allowed, max_symbols=5):
    pieces = [s.strip().upper() for s in raw.split(",")]
    if not pieces or any(not SYMBOL_RE.fullmatch(s) for s in pieces):
        raise ValueError("INVALID_US_SYMBOL")
    if len(pieces) != len(set(pieces)):
        raise ValueError("DUPLICATE_US_SYMBOL")
    if not 1 <= len(pieces) <= max_symbols:
        raise ValueError("BAD_SYMBOL_COUNT")
    missing = sorted(set(pieces)-set(allowed))
    if missing:
        raise ValueError("SYMBOL_NOT_IN_APPROVED_US_EQUITY_ETF_UNIVERSE:"+",".join(missing))
    return tuple(pieces)


def symbol_volume_features(bars, lookback=20):
    """Fully observed RTH for every symbol/date or explicit NA.

    Returns one row per requested symbol-session, and the four existing
    QLD/QQQ-compatible volume feature definitions, generalized by symbol.
    Calendar is XNYS; all requested symbols must trade on matching U.S.
    exchange sessions for this pilot, otherwise their session is NA/HOLD.
    """
    if lookback < 5:
        raise ValueError("LOOKBACK_LT_5")
    req={"market","candle_time_utc","volume","unit_min"}
    if not req.issubset(bars):
        raise ValueError("MISSING_SIP_BAR_FIELDS:"+",".join(sorted(req-set(bars))))
    x=bars.copy()
    x["market"]=x.market.astype(str).str.upper()
    if x.empty or x.market.isna().any() or not x.market.map(lambda k: bool(SYMBOL_RE.fullmatch(k))).all():
        raise ValueError("INVALID_SYMBOL_IN_BARS")
    if not pd.to_numeric(x.unit_min,errors="coerce").eq(15).all():
        raise ValueError("WRONG_BAR_TIMEFRAME")
    x["ts"]=pd.to_datetime(x.candle_time_utc,utc=True,errors="coerce")
    x["v"]=pd.to_numeric(x.volume,errors="coerce")
    if (x.ts.isna().any() or x.v.isna().any() or
            (x.v<0).any() or not np.isfinite(x.v.to_numpy()).all()):
        raise ValueError("INVALID_SIP_VOLUME")
    if x.duplicated(["market","ts"]).any():
        raise ValueError("DUPLICATED_SIP_BAR")
    x["local"]=x.ts.dt.tz_convert(NY)
    x["day"]=pd.to_datetime(x.local.dt.strftime("%Y-%m-%d"))
    calendar=xcals.get_calendar("XNYS")
    dates=calendar.sessions_in_range(x.day.min(),x.day.max())
    if len(dates)==0:
        raise ValueError("NO_US_SESSIONS")
    grouped={(s,d):a for (s,d),a in x.groupby(["market","day"])}
    rows=[]
    for symbol in sorted(x.market.unique()):
        for day in dates:
            session=pd.Timestamp(day).tz_localize(None)
            op=calendar.session_open(day).tz_convert(NY)
            cl=calendar.session_close(day).tz_convert(NY)
            expected=pd.date_range(op,cl-pd.Timedelta(minutes=15),freq="15min")
            subset=grouped.get((symbol,session))
            complete=False
            volume=np.nan
            if subset is not None:
                rth=subset.loc[subset.local.ge(op)&subset.local.lt(cl)].sort_values("local")
                complete=pd.DatetimeIndex(rth.local).equals(expected)
                if complete:
                    volume=float(rth.v.sum())
            rows.append({"symbol":symbol,"date_ny":session,
                         "rth_volume_shares":volume,
                         "complete_rth":complete,
                         "available_after_close_utc":cl.tz_convert("UTC").isoformat()})
    d=pd.DataFrame(rows).sort_values(["symbol","date_ny"])
    # Rolling window uses last 20 EXCHANGE sessions, not the last 20 non-null
    # observations. Missing volume blocks the denominator; fail closed.
    output=[]
    for symbol,section in d.groupby("symbol",sort=True):
        s=section.copy()
        v=s.rth_volume_shares.astype(float)
        prior=v.shift(1).rolling(lookback,min_periods=lookback)
        baseline=prior.median().where(lambda v:v>0)
        std=prior.std(ddof=0).where(lambda v:v>0)
        s["rvol20"]=v/baseline
        s["volume_z20"]=(v-prior.mean())/std
        s["volume_over_2x"]=s.rvol20.ge(2).where(s.rvol20.notna())
        # note: labels are historical research features and may only be
        # consumed once the regular exchange session is complete.
        output.append(s)
    merged=pd.concat(output,ignore_index=True)
    quality={"schema":"us-multisymbol-sip-15min-volume-v1",
             "symbol_count":int(merged.symbol.nunique()),
             "symbols":sorted(merged.symbol.unique().tolist()),
             "sessions_per_symbol":int(len(dates)),
             "complete_symbol_sessions":int(merged.complete_rth.sum()),
             "partial_or_missing_symbol_sessions":int((~merged.complete_rth).sum()),
             "signal_available":"AFTER_RTH_CLOSE_ONLY",
             "next_eligible_entry":"NEXT_NYSE_SESSION",
             "no_partial_day_fill":True,
             "no_live_changes":True}
    return merged,quality


def historical_quote_probe(symbols, max_pages, stale_ms, key, secret):
    results={}
    with requests.Session() as session:
        for symbol in symbols:
            try:
                trades,tpages=fetch_prints_or_quotes(
                    session,symbol,"trades",TRADE_START,TRADE_END,
                    key,secret,max_pages)
                quotes,qpages=fetch_prints_or_quotes(
                    session,symbol,"quotes",QUOTE_START,QUOTE_END,
                    key,secret,max_pages)
                metric=classify_aggressor(trades,quotes,stale_ms)
                metric["pages"]={"trades":tpages,"quotes":qpages}
                hc=metric.get("high_confidence_classified_share_pct",0)
                metric["coverage_note"]=(
                    "LOW_HIGH_CONFIDENCE_CLASSIFICATION_COVERAGE"
                    if hc<70 else "COVERAGE_ABOVE_EXPLORATORY_70PCT")
                results[symbol]={"status":"ACCESS_PASS_CLASSIFICATION_EXPLORATORY",**metric}
            except (RuntimeError,ValueError,KeyError) as exc:
                results[symbol]={"status":"HOLD","reason":str(exc)}
    return results


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--symbols",default=PROBE_DEFAULT)
    p.add_argument("--universe",default=str(MANIFEST))
    p.add_argument("--max-symbols",type=int,default=5)
    p.add_argument("--mode",choices=("probe","volume"),default="probe")
    p.add_argument("--input-bars",help="private 15min Parquet required in volume mode")
    p.add_argument("--max-pages",type=int,default=12)
    p.add_argument("--stale-ms",type=int,default=1000)
    p.add_argument("--out",required=True)
    args=p.parse_args()
    allow=approved_us_symbols(args.universe)
    symbols=select_symbols(args.symbols,allow,max_symbols=args.max_symbols)
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    if args.mode=="volume":
        if not args.input_bars:
            raise SystemExit("PRIVATE_INPUT_BARS_REQUIRED")
        raw=pd.read_parquet(args.input_bars)
        actual=set(raw.market.astype(str).str.upper())
        if actual!=set(symbols):
            raise SystemExit("BAR_SYMBOL_SET_MISMATCH")
        d,quality=symbol_volume_features(raw)
        # aggregated daily derived features only, no raw intraday SIP bars.
        d.to_parquet(out.with_name(out.stem+"_daily_features.parquet"),index=False)
        result={"status":"FEATURES_COMPUTED_RESEARCH_ONLY",
                "universe_source":args.universe,
                "quality":quality,
                "output":out.with_name(out.stem+"_daily_features.parquet").name,
                "no_live_changes":True}
    else:
        if not 1<=args.max_pages<=25 or not 100<=args.stale_ms<=2000:
            raise SystemExit("INVALID_PROBE_BOUNDS")
        import os
        key=os.getenv("ALPACA_API_KEY_ID") or os.getenv("APCA_API_KEY_ID")
        secret=os.getenv("ALPACA_API_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY")
        if not key or not secret:
            result={"status":"HOLD_NO_CREDENTIALS","symbols":symbols}
        else:
            metrics=historical_quote_probe(symbols,args.max_pages,args.stale_ms,key,secret)
            complete=all(v["status"].startswith("ACCESS_PASS")
                         for v in metrics.values())
            result={"status":"PROBE_ACCESS_PASS_MODEL_HOLD"
                    if complete else "HOLD_INCOMPLETE_SOURCE",
                    "symbols":list(symbols),
                    "window":[TRADE_START,TRADE_END],
                    "method":"STRICTLY_PRIOR_QUOTE_ASOF",
                    "quote_max_age_ms":args.stale_ms,
                    "reconciliation":"SHARES_BY_CLASS_EQUAL_SUM_PRINT_SIZES",
                    "raw_trade_conditions_unfiltered":True,
                    "print_correction_chain_unverified":True,
                    "only_10_seconds_not_multiyear_data":True,
                    "no_live_changes":True,
                    "data":metrics}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print("US_MULTISYMBOL_RESEARCH "+json.dumps(result,ensure_ascii=False),flush=True)
    if result["status"] not in ("PROBE_ACCESS_PASS_MODEL_HOLD",
                                "FEATURES_COMPUTED_RESEARCH_ONLY"):
        raise SystemExit(2)


if __name__=="__main__":
    main()
