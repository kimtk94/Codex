"""Market-relative, not sector-relative, research on frozen QQQ/AAPL/AMZN/IONQ daily bars.

No point-in-time constituent eligibility, corporate action audit, or executable fills.
Input base64 parquet assets are explicitly frozen user Drive history snapshots.
"""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import numpy as np
import pandas as pd

SYMBOLS = ("QQQ","AAPL","AMZN","IONQ")
HASHES = {
 "QQQ":"0508fd19fa3c738ad5f36645dfd75880da6860190a1ca82ba205ad07076b2a0e",
 "AAPL":"dfd25a0d989ab1a1366768e2c19e9fe8399055f1cee3cb8056ca94ad80c4ecef",
 "AMZN":"09e3fa26b2b9f7dfbdfca4f92621be30f4e2390ef3ccd2767039eaabccbdeb35",
 "IONQ":"3c20fce5eea14b67e1b724b18afd7e16a94ef2e250c8de6e954fff8a5e639ec9",
}
DATE_FIELDS = ("date_ny","date","datetime","timestamp","ts_utc","date_utc","time","ts","bar_time")
PRICE_FIELDS = ("adj close","adj_close","adjusted_close","adjusted close")

def load_history(folder):
    rows=[]
    details=[]
    for symbol in SYMBOLS:
        p=Path(folder)/(symbol+"_1d_long.parquet.b64")
        if not p.exists(): raise ValueError(f"missing {symbol} parquet fixture")
        raw=base64.b64decode(p.read_text().strip(),validate=True)
        sha=hashlib.sha256(raw).hexdigest()
        if sha!=HASHES[symbol]:raise ValueError(f"checksum mismatch {symbol}: {sha}")
        df=pd.read_parquet(io.BytesIO(raw))
        df.columns=[str(c).strip().lower() for c in df.columns]
        if not any(x in df.columns for x in DATE_FIELDS):
            if isinstance(df.index,pd.DatetimeIndex):
                df=df.reset_index()
                df.columns=[str(c).strip().lower() for c in df.columns]
            else:
                raise ValueError(f"{symbol} missing date column; columns={list(df.columns)}")
        date_col=next((x for x in DATE_FIELDS if x in df.columns),None)
        if date_col is None and "index" in df.columns:date_col="index"
        price_col=next((x for x in PRICE_FIELDS if x in df.columns),None)
        if date_col is None or price_col is None:
            raise ValueError(f"{symbol} cannot infer date/adjusted price from {list(df.columns)}")
        x=pd.DataFrame({"date":pd.to_datetime(df[date_col],utc=True,errors="raise").dt.tz_convert(None).dt.normalize(),
                        "symbol":symbol,"close":pd.to_numeric(df[price_col],errors="raise")})
        if x.date.duplicated().any() or x.close.isna().any() or (x.close<=0).any():
            raise ValueError(f"{symbol} duplicate dates, nulls or nonpositive close")
        x=x.sort_values("date")
        if len(x)<200:raise ValueError(f"{symbol} insufficient history")
        details.append({"symbol":symbol,"rows":len(x),"first":str(x.date.iloc[0].date()),"last":str(x.date.iloc[-1].date()),"columns":list(df.columns),"sha256":sha,"price_basis":price_col})
        rows.append(x)
    return pd.concat(rows,ignore_index=True),details

def analyze(panel):
    p=panel.copy().sort_values(["symbol","date"]).reset_index(drop=True)
    if p.duplicated(["symbol","date"]).any():raise ValueError("duplicate price identity")
    g=p.groupby("symbol",sort=False)
    p["ret1"]=g.close.pct_change()
    p["ret5"]=g.close.pct_change(5)
    p["market60"]=np.nan
    q=p[p.symbol=="QQQ"][["date","ret1","ret5"]].copy()
    q["qqq60"]=p.loc[p.symbol=="QQQ","close"].pct_change(60).values
    q=q.rename(columns={"ret1":"qqqret1","ret5":"qqqret5"})
    p=p.merge(q,on="date",how="left",validate="many_to_one")
    g=p.groupby("symbol",sort=False)
    p["beta60"]=g.apply(lambda x:x.ret1.rolling(60,min_periods=45).cov(x.qqqret1)/x.qqqret1.rolling(60,min_periods=45).var(),include_groups=False).reset_index(level=0,drop=True)
    p["rel5"]=p.ret5-p.qqqret5
    p["beta_residual5"]=p.ret5-p.beta60*p.qqqret5
    p["market_regime"]=np.select([p.qqq60>=.08,p.qqq60<=-.08],["UP","DOWN"],default="SIDE")
    p["event"]=np.select([
      (p.market_regime=="UP")&(p.beta_residual5<=-.03),
      (p.market_regime=="DOWN")&(p.beta_residual5>=.03)
      ],["UP_WEAK","DOWN_STRONG"],default="NONE")
    p.loc[(p.symbol=="QQQ")|p.beta60.isna()|p.qqq60.isna(),"event"]="NONE"
    p["fwd5"]=g.close.shift(-5)/p.close-1
    # Future benchmark is for outcome attribution only; no use in event generation.
    qfuture=q[["date"]].copy()
    market_close=p[p.symbol=="QQQ"][["date","close"]].copy()
    market_close["qqq_fwd5"]=market_close.close.shift(-5)/market_close.close-1
    p=p.merge(market_close[["date","qqq_fwd5"]],on="date",how="left")
    p["fwd_beta_excess"]=p.fwd5-p.beta60*p.qqq_fwd5
    events=[]
    last={}
    for i,row in p.iterrows():
        if row.event=="NONE" or pd.isna(row.fwd5) or pd.isna(row.fwd_beta_excess):continue
        key=(row.symbol,row.event)
        # Need trading-session spacing, not row count across different symbols.
        session=int((p.loc[(p.symbol==row.symbol)&(p.date<=row.date)].shape[0]))
        if session-last.get(key,-999)<5:continue
        last[key]=session
        events.append(i)
    e=p.loc[events].copy()
    e["year"]=e.date.dt.year
    summary=e.groupby(["symbol","event"],as_index=False).agg(
        events=("date","size"),avg_fwd5=("fwd5","mean"),avg_beta_excess5=("fwd_beta_excess","mean"),
        relative_win_rate=("fwd_beta_excess",lambda x:float((x>0).mean())))
    return e,summary

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--data-dir",default="research/regime_countertrend/data/stock_history")
    ap.add_argument("--out",default="results/regime_countertrend/cross_symbol")
    args=ap.parse_args()
    panel,details=load_history(args.data_dir)
    events,summary=analyze(panel)
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    events.to_csv(out/"events.csv",index=False)
    summary.to_csv(out/"symbol_summary.csv",index=False)
    events["era"]=np.where(events.year<=2024,"DEVELOPMENT_PRE2025","HOLDOUT_2025_2026")
    by_era=events.groupby(["era","symbol","event"],as_index=False).agg(
        n=("date","size"),
        avg_5day_beta_excess=("fwd_beta_excess","mean"),
        median_5day_beta_excess=("fwd_beta_excess","median"),
        beat_beta_benchmark=("fwd_beta_excess",lambda x:float((x>0).mean())))
    by_era["reliable_for_promotion"]=False
    by_era.to_csv(out/"symbol_era_comparison.csv",index=False)
    print("BY_ERA:\\n"+by_era.to_string(index=False))
    (out/"provenance.json").write_text(json.dumps({
      "sources":details,
      "status":"EXPLORATORY_NO_LIVE_PROMOTION",
      "warning":"Adjusted close used for all names. Static universe, different volatility, and retrospective constituents; neither sector-relative nor executable strategy evaluation.",
    },indent=2))
    print("SOURCE:",json.dumps(details,ensure_ascii=False))
    print("SUMMARY:\n"+summary.to_string(index=False))
if __name__=="__main__":main()
