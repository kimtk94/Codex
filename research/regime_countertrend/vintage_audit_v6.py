"""Retrospective price vintage audit. All previous 2022-26 research is HOLD
if a later Yahoo adjusted-close/FX response revises frozen historical data
or changes selected signal identities. No raw private broker data included.
"""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
import numpy as np

def signal_fingerprint(df,selector=None):
    keys=["date","symbol","year"]
    if not set(keys).issubset(df):raise ValueError("missing selected-signal identity")
    part=df if selector is None else df.loc[df[selector].astype(bool)]
    if part.duplicated(keys).any():raise ValueError("duplicate historical signal")
    values=sorted(f"{r.date}|{r.symbol}|{int(r.year)}" for r in part.itertuples())
    return {"rows":len(values),
            "sha256":hashlib.sha256("\n".join(values).encode()).hexdigest()}

def audit_price_vintage(prices,fx,baseline,v4,v5,threshold=None):
    threshold=float(threshold if threshold is not None else baseline["revision_hold_threshold_bps"])
    if not 0<threshold<100:raise ValueError("invalid hold threshold")
    points=[]
    for ticker,days in baseline["symbols"].items():
        if ticker not in prices:
            for date in days:
                points.append({"symbol":ticker,"date":date,
                    "status":"HOLD_SOURCE_MISSING","revision_bps":None})
            continue
        d=prices[ticker]
        if d.date.duplicated().any():raise ValueError("duplicate prices for "+ticker)
        frame=d.set_index("date")
        for date,old in days.items():
            if date not in frame.index:
                points.append({"symbol":ticker,"date":date,
                    "status":"HOLD_CHECKPOINT_MISSING","revision_bps":None})
                continue
            new=float(frame.loc[date,"close"])
            if not np.isfinite(new) or new<=0:raise ValueError("invalid close for "+ticker)
            bp=(new/float(old)-1)*10000
            points.append({"symbol":ticker,"date":date,"frozen_price":float(old),
                 "current_price":new,"revision_bps":float(bp),
                 "status":"HOLD_REVISED_CLOSE" if abs(bp)>threshold else "MATCH_5BP"})
    points_df=pd.DataFrame(points)
    expected=sum(len(x) for x in baseline["symbols"].values())
    if len(points_df)!=expected:raise ValueError("checkpoint cardinality mismatch")
    if fx.date.duplicated().any():raise ValueError("duplicate FX dates")
    anchor=fx.loc[fx.date=="2026-11-10","usdkrw_close"]
    fx_diff=None
    fx_state="HOLD_MISSING_FX_ANCHOR"
    if len(anchor)==1:
        fx_rate=float(anchor.iloc[0])
        if not 500<fx_rate<3000:raise ValueError("currency direction mismatch")
        fx_diff=(fx_rate/float(baseline["fx_baseline_2026_11_10_krw_per_usd"])-1)*10000
        fx_state="HOLD_REVISED_FX" if abs(fx_diff)>threshold else "MATCH_5BP"
    refs=baseline["frozen_selected_signal_sha256"]
    p4=signal_fingerprint(v4,"macro_market_selected")
    p5base=v5[v5.model=="FX_REGIME_BASE"]
    p5=signal_fingerprint(p5base,"selected")
    all_events=signal_fingerprint(v4)
    ids={
       "V4_ETF_MARKET":{**p4,"baseline_sha256":refs["V4_ETF_MARKET"]["sha256"],
            "matches":p4["sha256"]==refs["V4_ETF_MARKET"]["sha256"]},
       "V5_KRW_REGIME_BASE":{**p5,"baseline_sha256":refs["V5_KRW_REGIME_BASE"]["sha256"],
            "matches":p5["sha256"]==refs["V5_KRW_REGIME_BASE"]["sha256"]},
       "ALL_EVALUABLE_PROXY_EVENTS":{**all_events,
            "baseline_sha256":refs["ALL_EVALUABLE_PROXY_EVENTS"]["sha256"],
            "matches":all_events["sha256"]==refs["ALL_EVALUABLE_PROXY_EVENTS"]["sha256"]}
    }
    drift=points_df[points_df.status!="MATCH_5BP"]
    hold=bool(len(drift) or fx_state!="MATCH_5BP" or not all(x["matches"] for x in ids.values()))
    per_symbol=points_df.loc[points_df.status=="HOLD_REVISED_CLOSE"].groupby(
        "symbol",as_index=False).agg(max_abs_revision_bps=("revision_bps",
            lambda x:float(x.abs().max())),revised_checkpoints=("date","size"))
    report={
       "status":"HOLD_REVISED_RETROSPECTIVE_DATA" if hold else "PASS_FROZEN_VINTAGE",
       "frozen_reference_artifact":baseline["source_artifact_id"],
       "checkpoint_rows_checked":len(points_df),
       "revised_or_missing_checkpoint_rows":len(drift),
       "affected_equity_or_etf_symbols":sorted(
            set(drift.symbol)-{"KRW=X"}),
       "max_abs_checkpoint_revision_bps":float(
            points_df.revision_bps.abs().max()) if points_df.revision_bps.notna().any() else None,
       "fx_2026_11_10_revision_bps":float(fx_diff) if fx_diff is not None else None,
       "fx_status":fx_state,
       "frozen_selection_identity":ids,
       "affected_asset_summary":per_symbol.to_dict("records"),
       "correlation_and_model_inputs_comparable":not hold,
       "actual_broker_reconciliation":False,
       "promotion_allowed":False,
       "explanation":"Yahoo retrospective adjusted OHLC and FX may change across runs. Model results are versioned, not a new independent test."
    }
    return points_df,report

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--sources",default="results/regime_countertrend/universe_v3_prices")
    a.add_argument("--fx",default="results/regime_countertrend/krw_fx_v5/usdkrw_public_daily.csv")
    a.add_argument("--v4",default="results/regime_countertrend/peer_macro_v4/probabilities.csv")
    a.add_argument("--v5",default="results/regime_countertrend/krw_detail_v5/yearly_krw_detail_predictions.csv")
    a.add_argument("--baseline",default="research/regime_countertrend/frozen_vintage_checkpoints_v6.json")
    a.add_argument("--out",default="results/regime_countertrend/vintage_v6")
    args=a.parse_args()
    root=Path(args.out);root.mkdir(parents=True,exist_ok=True)
    frozen=json.loads(Path(args.baseline).read_text())
    sources={}
    for ticker in frozen["symbols"]:
        fn=Path(args.sources)/f"{ticker}.csv"
        if fn.is_file():sources[ticker]=pd.read_csv(fn)
    records,status=audit_price_vintage(sources,pd.read_csv(args.fx),frozen,
                         pd.read_csv(args.v4),pd.read_csv(args.v5))
    records.to_csv(root/"frozen_checkpoints_vs_latest.csv",index=False)
    (root/"decision.json").write_text(json.dumps(status,indent=2,ensure_ascii=False))
    print("VINTAGE_V6",json.dumps({k:status[k] for k in (
        "status","checkpoint_rows_checked","revised_or_missing_checkpoint_rows",
        "affected_equity_or_etf_symbols","max_abs_checkpoint_revision_bps",
        "fx_2026_11_10_revision_bps","fx_status","frozen_selection_identity",
        "promotion_allowed")},ensure_ascii=False))
if __name__=="__main__":main()
