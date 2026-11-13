"""CFM-V6 passive US ETF benchmarks evaluated in KRW, aligned to cash account.

One-time conversion KRW->USD with 10bp assumed spread; 20bp total
stock roundtrip synthetic cost included in terminal mark (conservative).
Not execution fills, commissions, tax or true risk-adjusted alpha.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .krw_fx_v5 import previous_fx_marks

BENCHMARKS=("SPY","QQQ","IWM","SMH","GLD")
CAPITAL=10_000_000.0
FX_SPREAD_BPS=10
STOCK_ROUNDTRIP_BPS=20

def evaluate_buyhold(frame,fx,start,end,symbol,initial_krw=CAPITAL,
                     fx_spread_bps=FX_SPREAD_BPS,stock_roundtrip_bps=STOCK_ROUNDTRIP_BPS):
    if initial_krw<=0 or not 0<=fx_spread_bps<10000 or not 0<=stock_roundtrip_bps<10000:
        raise ValueError("invalid benchmark fee setup")
    d=frame.copy().sort_values("date")
    if d.date.duplicated().any():raise ValueError("duplicate benchmark dates")
    d=d[(d.date>=start)&(d.date<=end)].copy()
    if d.empty or str(d.date.iloc[0])!=start or str(d.date.iloc[-1])!=end:
        raise ValueError("benchmark missing exactly aligned start/end sessions")
    prices=d.close.to_numpy(float)
    if not np.isfinite(prices).all() or (prices<=0).any():
        raise ValueError("invalid benchmark close")
    marks=previous_fx_marks(d.date,fx)
    rates=marks.fx_close_previous_session.to_numpy(float)
    if not np.isfinite(rates).all():
        raise ValueError("missing/stale previous-day FX close for benchmark")
    starting_usd=initial_krw/(rates[0]*(1+fx_spread_bps/10000))
    # Split the assumed roundtrip stock costs: charge 10bp on initial buy,
    # retain another 10bp for hypothetical final liquidation into USD.
    half=stock_roundtrip_bps/20000
    shares=starting_usd*(1-half)/prices[0]
    equity=shares*prices*rates
    equity[-1]*=(1-half)
    peak=np.maximum.accumulate(np.r_[initial_krw,equity])
    mdd=(equity/peak[1:]-1).min()
    p_and_l=equity[-1]/initial_krw-1
    passive_fx_cash_return=rates[-1]/(rates[0]*(1+fx_spread_bps/10000))-1
    row={"symbol":symbol,"start":start,"end":end,
        "begin_adj_close_usd":float(prices[0]),
        "end_adj_close_usd":float(prices[-1]),
        "begin_fx_krw_per_usd":float(rates[0]),
        "end_fx_krw_per_usd":float(rates[-1]),
        "buy_hold_usd_return_pct":float((prices[-1]/prices[0]-1)*100),
        "buy_hold_krw_return_pct":float(p_and_l*100),
        "usd_cash_only_krw_return_pct":float(passive_fx_cash_return*100),
        "max_drawdown_eod_krw_pct":float(mdd*100),
        "stock_roundtrip_cost_bps":stock_roundtrip_bps,
        "initial_fx_conversion_cost_bps":fx_spread_bps,
        "hypothetical_end_usd_cash_not_converted_back":True,
        "research_only":True,"promotion_allowed":False}
    return pd.DataFrame({"date":d.date,"equity_krw":equity,
                         "usdkrw_mark":rates}),row

def compare_to_strategies(root,prices,fx):
    folder=Path(root)
    selected=[]
    models=["V4_ETF_MARKET","V5_KRW_REGIME_BASE"]
    for model in models:
        file=folder/f"{model}__USD_RETAIN__10bps_equity.csv"
        if not file.exists():raise ValueError("no matching cash curve: "+str(file))
        c=pd.read_csv(file)
        if len(c)<120:raise ValueError("short account time series")
        selected.append({"symbol":model,"start":str(c.date.iloc[0]),
            "end":str(c.date.iloc[-1]),
            "buy_hold_krw_return_pct":float(
                (c.equity_krw.iloc[-1]/CAPITAL-1)*100),
            "max_drawdown_eod_krw_pct":float((c.equity_krw/
                np.maximum.accumulate(np.r_[CAPITAL,c.equity_krw.to_numpy()])[1:]-1).min()*100),
            "research_only":True,"promotion_allowed":False})
    periods={(x["start"],x["end"]) for x in selected}
    if len(periods)!=1:raise ValueError("model cash benchmarking periods differ")
    start,end=next(iter(periods))
    bench=[]
    for sym in BENCHMARKS:
        if sym not in prices:raise ValueError("missing benchmark ETF "+sym)
        equity,row=evaluate_buyhold(prices[sym],fx,start,end,sym)
        equity.to_csv(folder/f"passive_{sym}_equity_krw.csv",index=False)
        bench.append(row)
    r=pd.DataFrame(selected+bench)
    return r,{
        "status":"HOLD_RETROSPECTIVE_BENCHMARKS_NO_FRESH_ALPHA",
        "comparison_start":start,"comparison_end":end,
        "comparisons":len(r),"stock_cost_roundtrip_bps":STOCK_ROUNDTRIP_BPS,
        "fx_initial_conversion_bps":FX_SPREAD_BPS,
        "currency":"KRW",
        "warning":"Strategy cash utilization/drawdown differs from fully invested passive ETFs; no risk parity, intraday fills, real FX ledger or untouched OOS.",
        "promotion_allowed":False}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source-dir",default="results/regime_countertrend/universe_v3_prices")
    ap.add_argument("--cash-dir",default="results/regime_countertrend/krw_cash_v6")
    ap.add_argument("--fx",default="results/regime_countertrend/krw_fx_v5/usdkrw_public_daily.csv")
    a=ap.parse_args()
    folder=Path(a.cash_dir)
    prices={s:pd.read_csv(Path(a.source_dir)/f"{s}.csv") for s in BENCHMARKS}
    fx=pd.read_csv(a.fx)
    result,meta=compare_to_strategies(folder,prices,fx)
    result.to_csv(folder/"passive_etf_comparisons.csv",index=False)
    (folder/"passive_etf_decision.json").write_text(json.dumps(meta,indent=2))
    print("CFM_V6_PASSIVE_ETF_BENCHMARKS",result.to_json(orient="records"))
if __name__=="__main__":main()
