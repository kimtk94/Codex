"""CFM-V5: USD/KRW historical conversion of US-dollar proxy trades.

Yahoo KRW=X (USD/KRW: won per 1 USD), DAILY FX marks only. For causal
provenance, use the last FX DAILY CLOSE dated strictly BEFORE each US equity
entry/exit NY calendar date. This is conservative as-of timing, not the actual
bank/broker's 9:30ET FX execution quote. Compare USD and KRW winning trades,
not a realized portfolio statement. KRW crypto is a SEPARATE venue pipeline.
"""
import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

FX_TICKER="KRW=X"
FX_FROM="2016-12-01"
FX_THROUGH_EXCLUSIVE="2026-11-11"
FX_MIN=500.0
FX_MAX=3000.0
FX_STALE_DAYS=5
SPREAD_SCENARIOS=(0,10,25)  # each side, basis points
STOCK_CURRENCY="USD"
EVALUATION_CURRENCY="KRW"

def parse_fx_chart(raw):
    obj=json.loads(raw)["chart"]["result"][0]
    q=obj["indicators"]["quote"][0]
    dates=pd.to_datetime(obj["timestamp"],unit="s",utc=True).tz_convert(
        "America/New_York").strftime("%Y-%m-%d")
    data=pd.DataFrame({"date":dates,"usdkrw_close":q["close"]})
    data=data.dropna().sort_values("date").reset_index(drop=True)
    if data.empty or data.date.duplicated().any():
        raise ValueError("FX dates missing or duplicate")
    vals=pd.to_numeric(data.usdkrw_close,errors="coerce")
    if not np.isfinite(vals).all() or not vals.between(FX_MIN,FX_MAX).all():
        raise ValueError("USD/KRW data direction or values invalid")
    data["usdkrw_close"]=vals.astype(float)
    return data

def fetch_fx():
    start=int(pd.Timestamp(FX_FROM,tz="UTC").timestamp())
    end=int(pd.Timestamp(FX_THROUGH_EXCLUSIVE,tz="UTC").timestamp())
    args=urllib.parse.urlencode({"period1":start,"period2":end,
                                 "interval":"1d","events":"history"})
    errors=[]
    for ticker in ("KRW=X","USDKRW=X"):
        for host in ("query1.finance.yahoo.com","query2.finance.yahoo.com"):
            try:
                url=f"https://{host}/v8/finance/chart/{ticker}?{args}"
                req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
                with urllib.request.urlopen(req,timeout=24) as r:
                    raw=r.read(3_000_000)
                fx=parse_fx_chart(raw)
                if fx.date.min()>"2017-01-01" or fx.date.max()<"2026-11-09":
                    raise ValueError("FX historical coverage incomplete")
                return fx,{"status":"SOURCE_PASS","ticker":ticker,
                    "vendor":host,"raw_sha256":hashlib.sha256(raw).hexdigest(),
                    "rows":len(fx),"first_date":str(fx.date.min()),
                    "last_date":str(fx.date.max()),
                    "quote_direction":"KRW_PER_USD",
                    "rate_basis":"Daily close, previous dated FX session only"}
            except Exception as e:
                errors.append({"ticker":ticker,"host":host,"type":type(e).__name__,
                               "detail":str(e)[:110]})
    raise ValueError("No usable FX quote. "+json.dumps(errors)[-1000:])

def previous_fx_marks(equity_dates,fx):
    """Strictly preceding calendar day close; max 5 calendar-day age."""
    fx=fx.sort_values("date").copy()
    if fx.date.duplicated().any():raise ValueError("FX duplicate date")
    src=pd.to_datetime(fx.date).to_numpy(dtype="datetime64[ns]")
    price=pd.to_numeric(fx.usdkrw_close,errors="raise").to_numpy(float)
    if not np.isfinite(price).all() or not ((price>=FX_MIN)&(price<=FX_MAX)).all():
        raise ValueError("FX quote not KRW per USD")
    requested=pd.to_datetime(equity_dates).to_numpy(dtype="datetime64[ns]")
    indices=np.searchsorted(src,requested,side="left")-1
    values=np.full(len(indices),np.nan,dtype=float)
    dates=np.full(len(indices),np.datetime64("NaT","ns"))
    good=indices>=0
    values[good]=price[indices[good]]
    dates[good]=src[indices[good]]
    age=np.full(len(indices),np.nan)
    age[good]=((requested[good]-dates[good])/np.timedelta64(1,"D")).astype(float)
    if (age[good]<=0).any():
        raise ValueError("FX lookahead error")
    values[age>FX_STALE_DAYS]=np.nan
    return pd.DataFrame({
        "fx_close_previous_session":values,
        "fx_reference_date":pd.to_datetime(dates).strftime("%Y-%m-%d"),
        "fx_age_calendar_days":age
    })

def build_entry_dates(events,stock_prices):
    result=events.copy().reset_index(drop=True)
    if result.duplicated(["date","symbol"]).any():
        raise ValueError("duplicate event identity")
    date_maps={}
    for sym,table in stock_prices.items():
        days=table.date.astype(str).sort_values().reset_index(drop=True)
        if days.duplicated().any():raise ValueError("stock prices have duplicate date")
        date_maps[sym]=days.to_numpy()
    entries=[]
    for row in result.itertuples():
        dates=date_maps.get(row.symbol)
        if dates is None:raise ValueError(f"{row.symbol}: missing stock prices")
        i=np.searchsorted(dates,row.date,side="right")
        if i>=len(dates):raise ValueError(f"{row.symbol}: no next-session open")
        if row.exit_date<str(dates[i]):
            raise ValueError("exit precedes entry")
        entries.append(str(dates[i]))
    result["entry_date"]=entries
    return result

def attach_fx(events,fx,spreads=SPREAD_SCENARIOS):
    needed={"date","entry_date","exit_date","symbol","net_20bp"}
    if needed-set(events):raise ValueError("missing events "+str(needed-set(events)))
    if events.empty:raise ValueError("no event data")
    out=events.copy().reset_index(drop=True)
    entry=previous_fx_marks(out.entry_date,fx).add_prefix("entry_")
    leave=previous_fx_marks(out.exit_date,fx).add_prefix("exit_")
    out=pd.concat([out,entry,leave],axis=1)
    a=out.entry_fx_close_previous_session.to_numpy(float)
    b=out.exit_fx_close_previous_session.to_numpy(float)
    usd=out.net_20bp.to_numpy(float)
    if not np.isfinite(usd).all() or (usd<=-1).any():
        raise ValueError("invalid USD trade returns")
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("missing or stale matched USDKRW (do not fill zero)")
    fx_move=b/a-1
    out["fx_return"]=fx_move
    out["usd_net_return"]=usd
    out["krw_mark_return"]=(1+usd)*(1+fx_move)-1
    out["fx_contribution"]=fx_move
    out["interaction_contribution"]=usd*fx_move
    for basis_points in spreads:
        spread=basis_points/10000.0
        # If FULL notional is converted on BOTH sides, buy USD at higher quote,
        # sell USD at lower quote. Not equivalent to the mark-to-market of a
        # USD cash balance kept unconverted between trades.
        out[f"krw_roundtrip_fx_{basis_points}bps_each_side"]=(1+usd)*(b/a)*(
            (1-spread)/(1+spread))-1
    out["usd_win"]=out.usd_net_return>0
    out["krw_mark_win"]=out.krw_mark_return>0
    for basis_points in spreads:
        out[f"krw_conversion_win_{basis_points}bps_each_side"]=(
            out[f"krw_roundtrip_fx_{basis_points}bps_each_side"]>0)
    if not np.allclose(out.krw_mark_return,
        out.usd_net_return+out.fx_contribution+out.interaction_contribution,
        rtol=1e-11,atol=1e-11):
        raise ValueError("currency attribution identity mismatch")
    return out

def summarize(e,models=None):
    model_masks=models or {"ALL_TRADES":np.ones(len(e),dtype=bool)}
    rows=[]
    for name,mask in model_masks.items():
        m=np.asarray(mask,dtype=bool)
        if m.shape!=(len(e),):raise ValueError("selection mask misaligned")
        taken=e.loc[m]
        for col,quote_type in (
            ("usd_net_return","USD"),
            ("krw_mark_return","KRW_MARK"),
            ("krw_roundtrip_fx_10bps_each_side","KRW_CONVERT_10BPS_SIDE"),
            ("krw_roundtrip_fx_25bps_each_side","KRW_CONVERT_25BPS_SIDE")):
            rows.append({"model":name,"quote_type":quote_type,
                "opportunities":len(e),"trades":len(taken),
                "win_rate":float((taken[col]>0).mean()) if len(taken) else None,
                "mean_per_selected":float(taken[col].mean()) if len(taken) else None,
                "mean_per_opportunity":float(taken[col].sum()/len(e)),
                "worst_trade":float(taken[col].min()) if len(taken) else None,
                "negative_trades":int((taken[col]<0).sum())})
    return pd.DataFrame(rows)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source-dir",default="results/regime_countertrend/universe_v3_prices")
    p.add_argument("--events",default="results/regime_countertrend/sector_v3/all_symbol_proxy_events.csv")
    p.add_argument("--v4-pred",default="results/regime_countertrend/peer_macro_v4/probabilities.csv")
    p.add_argument("--out",default="results/regime_countertrend/krw_fx_v5")
    a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    status={"research_only":True,"quote_direction":"KRW per USD",
            "primary_reporting_currency":"KRW",
            "secondary_reporting_currency":"USD",
            "actual_broker_cash_policy":"UNKNOWN_NEEDS_ACCOUNT_CASH_LEDGER",
            "currency_scenarios":["USD","KRW_MARK","KRW_CONVERT_10BPS_SIDE",
                                   "KRW_CONVERT_25BPS_SIDE"],
            "actual_broker_fx_conversions_verified":False,"promotion_allowed":False}
    try:
        fx,provenance=fetch_fx()
        status["source"]=provenance
        prices={}
        events=pd.read_csv(a.events)
        for sym in events.symbol.unique():
            fp=Path(a.source_dir)/f"{sym}.csv"
            if not fp.is_file():raise ValueError(f"missing stock {sym} price")
            prices[sym]=pd.read_csv(fp)
        positioned=build_entry_dates(events,prices)
        priced=attach_fx(positioned,fx)
        old=pd.read_csv(a.v4_pred)
        compared=priced.merge(old[["date","symbol","year",
            "macro_market_selected","macro_peer_selected"]],
            on=["date","symbol","year"],how="inner",validate="one_to_one")
        if len(compared)!=len(old) or compared.duplicated(["date","symbol"]).any():
            raise ValueError("V4 event set not identically matched")
        compared=compared.sort_values(["date","symbol"])
        compared.to_csv(out/"v4_krw_trades_with_fx_attribution.csv",index=False)
        masks={"BASELINE":np.ones(len(compared),dtype=bool),
               "V4_ETF_MARKET":compared.macro_market_selected.astype(bool).to_numpy(),
               "V4_ETF_PEER_SYMBOL":compared.macro_peer_selected.astype(bool).to_numpy()}
        summary=summarize(compared,masks)
        summary.to_csv(out/"usd_krw_wins_and_costs.csv",index=False)
        fx.to_csv(out/"usdkrw_public_daily.csv",index=False)
        status.update({"status":"KRW_BACKTEST_RESEARCH_ONLY",
            "events":len(compared),
            "source_coverage":int(compared.entry_fx_reference_date.notna().sum()),
            "price_only":True,
            "not_account_settlement":True,
            "notes":["Historical mark-to-market uses FX dated before equity entry/exit dates.",
                "Conversion scenarios charge spread on each conversion leg.",
                "Actual FX bank fills, rate, custody, taxes and stock commissions unverified.",
                "Original V4 win labels are USD-trained; KRW evaluation is not KRW-trained model.",
                "All models selected on the same already reviewed history."]})
        print("KRW_FX_SUMMARY",summary.to_json(orient="records"))
    except Exception as e:
        status.update({"status":"HOLD_FX_SOURCE_OR_ALIGNMENT",
                       "reason":type(e).__name__,"detail":str(e)[:320]})
    (out/"status.json").write_text(json.dumps(status,indent=2,ensure_ascii=False))
    print("KRW_FX_STATUS",json.dumps(status,ensure_ascii=False))
if __name__=="__main__":main()
