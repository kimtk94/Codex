"""CFM-V6 KRW portfolio cash simulation and read-only broker-evidence gate.

Never represent synthetic fills as brokerage statements. Uses known synthetic
net USD trade returns (including 20bp stock cost), adjusted OHLC for interim
marks, and previous-dated USD/KRW marks. No leverage or negative cash. Runs
with both USD-cash retention and immediate KRW reconversion policies.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

INITIAL_KRW=10_000_000.0
MAX_OPEN_POSITIONS=5
FRACTION_PER_NEW_POSITION=.20
FX_SPREAD_BPS=10
POLICIES=("USD_RETAIN","EACH_SALE_CONVERT_TO_KRW")
MODELS=("V4_ETF_MARKET","V5_KRW_REGIME_BASE")
EPS=1e-5

def selected_research_trades(fx_trades,v4_predictions,v5_predictions):
    """Join exactly one score per signal; prohibit different cohort labels."""
    keys=["date","symbol","year"]
    v4cols=keys+["macro_market_selected","macro_market_probability"]
    if not set(v4cols).issubset(v4_predictions):
        raise ValueError("V4 probability/selection columns unavailable")
    v5=v5_predictions[v5_predictions.model=="FX_REGIME_BASE"][
        keys+["selected","probability"]].rename(columns={
            "selected":"v5_selected","probability":"v5_probability"})
    if fx_trades.duplicated(keys).any() or v4_predictions.duplicated(keys).any() or v5.duplicated(keys).any():
        raise ValueError("duplicate signal identity")
    joined=fx_trades.merge(v4_predictions[v4cols],on=keys,how="inner",
                           validate="one_to_one",suffixes=("","_new"))
    if "macro_market_selected_new" in joined:
        if not (joined.macro_market_selected.astype(bool)==
                joined.macro_market_selected_new.astype(bool)).all():
            raise ValueError("V4 selection values changed")
        joined=joined.drop(columns="macro_market_selected_new")
    joined=joined.merge(v5,on=keys,how="inner",validate="one_to_one")
    if len(joined)!=len(fx_trades):
        raise ValueError("cash account cohorts don't match identical FX events")
    if (joined.entry_date.astype(str)<=joined.date.astype(str)).any():
        raise ValueError("entries earlier than signal completion")
    if (joined.exit_date.astype(str)<joined.entry_date.astype(str)).any():
        raise ValueError("exit occurs before synthetic entry")
    if not np.isfinite(joined[["usd_net_return","entry_fx_close_previous_session",
                             "exit_fx_close_previous_session",
                             "macro_market_probability","v5_probability"]].to_numpy(float)).all():
        raise ValueError("missing synthetic price or FX marks")
    return joined

def _daily_fx_rate(day,fx):
    """Use only an FX close dated STRICTLY BEFORE the equity day."""
    df=fx[fx.date.astype(str)<day]
    if df.empty:raise ValueError("no preceding FX quotation")
    row=df.iloc[-1]
    age=(pd.Timestamp(day)-pd.Timestamp(row.date)).days
    if age>5 or age<1:raise ValueError(f"FX stale or future: {day}")
    f=float(row.usdkrw_close)
    if not (500<f<3000):raise ValueError("USD/KRW quote direction invalid")
    return f

def broker_evidence_gate(folder=None):
    """Source is NEVER included in output. Presence alone is NOT reconciliation."""
    if not folder:return {"status":"HOLD_BROKER_LEDGER_NOT_CONNECTED",
                           "actual_fills_verified":False,
                           "actual_fx_conversions_verified":False}
    location=Path(folder)
    needed={"fills.csv":{"timestamp_utc","symbol","side","quantity","price_usd","fee_usd","order_id"},
            "fx_conversions.csv":{"timestamp_utc","from_currency","to_currency","amount_from","amount_to","conversion_id"},
            "cash_balances.csv":{"timestamp_utc","currency","balance"}}
    missing=[]
    for file,columns in needed.items():
        path=location/file
        if not path.is_file():missing.append(file);continue
        head=pd.read_csv(path,nrows=0)
        if not columns.issubset(head):missing.append(file+":SCHEMA_INVALID")
    if missing:return {"status":"HOLD_BROKER_LEDGER_MISSING_OR_INVALID",
                       "missing_or_invalid_files":missing,
                       "actual_fills_verified":False,
                       "actual_fx_conversions_verified":False}
    return {"status":"HOLD_BROKER_FILES_PRESENT_NOT_RECONCILED",
            "actual_fills_verified":False,
            "actual_fx_conversions_verified":False,
            "note":"Schemas are present; trade IDs, quantities, fees and cash movements must be fully reconciled before PASS."}

def simulate_cash(trades,prices,fx,model,policy,spread_bps=FX_SPREAD_BPS,
                  initial_krw=INITIAL_KRW,max_positions=MAX_OPEN_POSITIONS,
                  allocation=FRACTION_PER_NEW_POSITION):
    if policy not in POLICIES or model not in MODELS:raise ValueError("invalid policy/model")
    if initial_krw<=0 or not 0<allocation<=1 or max_positions<1 or not 0<=spread_bps<10000:
        raise ValueError("invalid account risk parameters")
    g=trades.copy()
    if model=="V4_ETF_MARKET":
        g=g[g.macro_market_selected.astype(bool)]
        score="macro_market_probability"
    else:
        g=g[g.v5_selected.astype(bool)]
        score="v5_probability"
    if g.empty:raise ValueError("no selected candidates")
    g=g.sort_values(["entry_date",score,"symbol"],ascending=[True,False,True])
    if g.duplicated(["date","symbol"]).any():raise ValueError("duplicate account signal")
    names=sorted(set(g.symbol))
    for name in names:
        if name not in prices:raise ValueError("missing stock daily source "+name)
        if prices[name].date.duplicated().any():raise ValueError("duplicate market dates")
    close_lookup={sym:dict(zip(df.date.astype(str),df.close.astype(float))) for sym,df in prices.items()}
    open_lookup={sym:dict(zip(df.date.astype(str),df.open.astype(float))) for sym,df in prices.items()}
    first=str(g.entry_date.min())
    last=str(g.exit_date.max())
    timeline=sorted(set().union(*(set(d.date.astype(str)) for d in prices.values())))
    timeline=[d for d in timeline if first<=d<=last]
    if not timeline:raise ValueError("no aligned trading timeline")
    entering={day:group for day,group in g.groupby("entry_date")}
    cash_krw=float(initial_krw);cash_usd=0.0
    positions={};last_close={}
    events=[];equity_rows=[];conversions=0;skipped=0;invested_trades=0
    spread=spread_bps/10000.0
    for day in timeline:
        rate=_daily_fx_rate(day,fx)
        # At 09:30 ET, existing holdings are valued at the PREVIOUS completed close.
        holding_usd=sum(p["shares"]*last_close.get(sym,p["entry_open"])
                        for sym,p in positions.items())
        equity_before=cash_krw+(cash_usd+holding_usd)*rate
        if day in entering:
            for row in entering[day].itertuples():
                sym=row.symbol
                if sym in positions or len(positions)>=max_positions:
                    skipped+=1
                    events.append({"date":day,"symbol":sym,"action":"SKIP_CAPACITY_OR_DUPLICATE"})
                    continue
                stake_target=equity_before*allocation/rate
                fundable=cash_usd+cash_krw/(rate*(1+spread))
                stake=min(stake_target,fundable)
                if stake<1.0:
                    skipped+=1
                    events.append({"date":day,"symbol":sym,"action":"SKIP_NO_CASH"})
                    continue
                shortage=max(0.0,stake-cash_usd)
                if shortage>EPS:
                    krw_spent=shortage*rate*(1+spread)
                    cash_krw-=krw_spent
                    cash_usd+=shortage
                    conversions+=1
                    events.append({"date":day,"symbol":sym,"action":"BUY_USD",
                                  "usd":shortage,"krw_delta":-krw_spent,"rate":rate})
                cash_usd-=stake
                entry_open=float(open_lookup[sym][day])
                if not np.isfinite(entry_open) or entry_open<=0:
                    raise ValueError("invalid entry price")
                positions[sym]={"entry_date":day,"entry_open":entry_open,
                    "exit_date":str(row.exit_date),"shares":stake/entry_open,
                    "invested_usd":stake,"usd_return":float(row.usd_net_return)}
                invested_trades+=1
                events.append({"date":day,"symbol":sym,"action":"BUY_STOCK",
                               "usd":stake,"shares":stake/entry_open})
        # Exit after the session open, before EOD mark. Never use today's exit
        # proceeds to fund today's earlier open.
        for sym,p in list(positions.items()):
            if p["exit_date"]!=day:continue
            payout=p["invested_usd"]*(1+p["usd_return"])
            if payout<0:raise ValueError("negative synthetic payout")
            cash_usd+=payout
            events.append({"date":day,"symbol":sym,"action":"SELL_STOCK",
                           "usd":payout,"usd_return":p["usd_return"]})
            del positions[sym]
            if policy=="EACH_SALE_CONVERT_TO_KRW":
                received=payout*rate*(1-spread)
                cash_usd-=payout
                cash_krw+=received
                conversions+=1
                events.append({"date":day,"symbol":sym,"action":"SELL_USD",
                               "usd":payout,"krw_delta":received,"rate":rate})
        for sym,d in close_lookup.items():
            if day in d:last_close[sym]=d[day]
        current_position_usd=sum(p["shares"]*last_close.get(sym,p["entry_open"])
                                for sym,p in positions.items())
        equity=cash_krw+(cash_usd+current_position_usd)*rate
        if cash_krw<-EPS or cash_usd<-EPS or equity<-EPS:
            raise ValueError("cash/account leverage constraint violated")
        equity_rows.append({"date":day,"equity_krw":equity,
             "cash_krw":cash_krw,"cash_usd":cash_usd,
             "position_mark_usd":current_position_usd,
             "open_positions":len(positions),"fx_rate":rate})
    equity_curve=pd.DataFrame(equity_rows)
    if positions:
        raise ValueError("open positions beyond final synthetic exit; source incomplete")
    peak=np.maximum.accumulate(np.r_[initial_krw,equity_curve.equity_krw.to_numpy()])
    drawdown=equity_curve.equity_krw.to_numpy()/peak[1:]-1
    # Passive USD cash is a necessary control: KRW gains may simply be FX
    # exposure on idle USD balances, unrelated to stock selection alpha.
    first_rate=float(equity_curve.fx_rate.iloc[0])
    final_rate=float(equity_curve.fx_rate.iloc[-1])
    fx_cash_only_pct=((final_rate/(first_rate*(1+spread)))-1)*100
    realized_strategy_pct=(float(equity_curve.equity_krw.iloc[-1])/initial_krw-1)*100
    summary={"model":model,"cash_policy":policy,"initial_krw":initial_krw,
        "passive_usd_cash_krw_return_pct":float(fx_cash_only_pct),
        "passive_krw_cash_return_pct":0.,
        "excess_vs_passive_usd_cash_pp":float(realized_strategy_pct-fx_cash_only_pct),
        "valuation_rate_initial":first_rate,"valuation_rate_final":final_rate,
        "last_krw_mark_equity":float(equity_curve.equity_krw.iloc[-1]),
        "initial_to_final_krw_return_pct":float(
            (equity_curve.equity_krw.iloc[-1]/initial_krw-1)*100),
        "maximum_drawdown_pct":float(drawdown.min()*100),
        "trades_executed_proxy":invested_trades,
        "eligible_selected_signals":len(g),"skipped_due_capacity_or_cash":skipped,
        "fx_conversions":conversions,"last_cash_usd":cash_usd,
        "last_cash_krw":cash_krw,"valuation_quote":"prior FX session close",
        "overlapping_trades_limited_to":max_positions,
        "fraction_per_new_position":allocation,
        "roundtrip_equity_fee_already_in_usd_net":True,
        "spread_per_conversion_leg_bps":spread_bps,
        "portfolio_status":"SYNTHETIC_NOT_BROKER_RECONCILED",
        "promotion_allowed":False}
    return equity_curve,pd.DataFrame(events),summary

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source-dir",default="results/regime_countertrend/universe_v3_prices")
    p.add_argument("--fx",default="results/regime_countertrend/krw_fx_v5/usdkrw_public_daily.csv")
    p.add_argument("--trades",default="results/regime_countertrend/krw_fx_v5/v4_krw_trades_with_fx_attribution.csv")
    p.add_argument("--v4",default="results/regime_countertrend/peer_macro_v4/probabilities.csv")
    p.add_argument("--v5",default="results/regime_countertrend/krw_detail_v5/yearly_krw_detail_predictions.csv")
    p.add_argument("--out",default="results/regime_countertrend/krw_cash_v6")
    a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    ledger=broker_evidence_gate(os.getenv("KALMAN_BROKER_LEDGER_DIR"))
    (out/"broker_evidence_gate.json").write_text(json.dumps(ledger,indent=2))
    trades=selected_research_trades(pd.read_csv(a.trades),pd.read_csv(a.v4),
                                   pd.read_csv(a.v5))
    fx=pd.read_csv(a.fx)
    prices={sym:pd.read_csv(Path(a.source_dir)/f"{sym}.csv")
            for sym in trades.symbol.unique()}
    results=[]
    for model in MODELS:
        for policy in POLICIES:
            for spread in (0,10,25):
                curve,actions,summary=simulate_cash(trades,prices,fx,
                     model,policy,spread_bps=spread)
                tag=f"{model}__{policy}__{spread}bps"
                # Store curves/actions at the reference 10bp scenario, summary
                # table for all 0/10/25bp alternatives. Keeps artifact lean.
                if spread==10:
                    curve.to_csv(out/f"{tag}_equity.csv",index=False)
                    actions.to_csv(out/f"{tag}_synthetic_transactions.csv",index=False)
                results.append(summary)
    pd.DataFrame(results).to_csv(out/"policy_comparison.csv",index=False)
    decision={"status":"HOLD_PORTFOLIO_PROXY_NOT_ACTUAL_CASH",
        "portfolio_scenarios":len(results),"account_initial_krw_assumed":INITIAL_KRW,
        "broker_evidence_status":ledger["status"],"reports":results,
        "no_live_strategy_change":True,"promotion_allowed":False,
        "warnings":["Hypothetical 10M KRW account, 20% position sizing and 5 slots",
          "Previously explored retrospective model selection; not independent OOS",
          "Synthetic trade exit price/fees and adjusted daily mark (not broker order fills)",
          "FX uses previous-dated Yahoo daily close, not actual bank execution",
          "No actual brokerage statements or cash/FX ledger reconciled",
          "Price series adjustments, dividends, taxes and exchange fees may differ",
          "Source-vintage drift can change past trades and all reported return values",
          "Passive USD cash and passive KRW cash baselines separate currency exposure from stock selection",
          "This is portfolio proxy for policy sensitivity, not validated CAGR or account MDD"]}
    (out/"decision.json").write_text(json.dumps(decision,indent=2,ensure_ascii=False))
    print("KRW_CASH_V6",json.dumps({
      "status":decision["status"],"scenarios":results,
      "broker_evidence":ledger["status"],"promotion_allowed":False},ensure_ascii=False))
if __name__=="__main__":main()
