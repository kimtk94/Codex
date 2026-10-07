from __future__ import annotations

import argparse
import bisect
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

NY = ZoneInfo("America/New_York")
BASE_SCORE = "R5C0_HGB_REFERENCE"
STOP = -0.03
TAKE = 0.20
MIN_UNIVERSE = 80
HORIZONS = (4, 8, 12, 16, 20)
THRESHOLDS_BPS = (0.0, 10.0, 15.0, 20.0, 25.0, 30.0)
COSTS = (36.59673953005761, 45.0, 50.0, 60.0)
ALIASES = {"BNY": {"BNY", "BK"}}


def norm(x: str) -> str:
    return str(x).strip().upper().replace("-", ".")


def panel_path(root: Path, symbol: str) -> Path:
    return root / f"{str(symbol).upper().replace('.', '-')}_1h_gap_aware.parquet"


def load_panel(root: Path, symbol: str, cache: dict[str, pd.DataFrame]) -> pd.DataFrame:
    key = str(symbol).upper()
    if key in cache:
        return cache[key]
    p = panel_path(root, key)
    if not p.is_file():
        cache[key] = pd.DataFrame()
        return cache[key]
    z = pd.read_parquet(
        p,
        columns=["expected_seq","open","high","low","close","session_date","session_bucket"],
    )
    z["expected_seq"] = pd.to_numeric(z["expected_seq"], errors="coerce").astype("Int64")
    for c in ["open","high","low","close"]:
        z[c] = pd.to_numeric(z[c], errors="coerce")
    z = z.dropna(subset=["expected_seq","open","high","low","close"]).drop_duplicates("expected_seq",keep="last").set_index("expected_seq").sort_index()
    cache[key] = z
    return z


def load_membership(path: Path):
    z = pd.read_csv(path)
    z["date"] = pd.to_datetime(z["date"], errors="coerce").dt.date
    z = z.dropna(subset=["date"]).sort_values("date")
    dates=[]; members={}
    for r in z.itertuples(index=False):
        dates.append(r.date)
        members[r.date] = {norm(x) for x in str(r.tickers).split(",") if str(x).strip()}
    return dates,members


def member(symbol, day, dates, members):
    i = bisect.bisect_right(dates, day)-1
    if i<0: return False
    s=norm(symbol)
    return bool(ALIASES.get(s,{s}).intersection(members[dates[i]]))


def build_rank1(pred: pd.DataFrame, membership) -> pd.DataFrame:
    dates,members=membership
    z=pred.copy()
    local_days=z["timestamp"].dt.tz_convert(NY).dt.date
    keep=[member(s,d,dates,members) for s,d in zip(z.symbol.astype(str),local_days)]
    z=z.loc[keep].copy()
    rows=[]
    for ts,g in z.groupby("timestamp",sort=True):
        g=g.dropna(subset=[BASE_SCORE])
        if len(g)<MIN_UNIVERSE: continue
        r=g.sort_values([BASE_SCORE,"symbol"],ascending=[False,True]).iloc[0]
        rows.append({"timestamp":ts,"expected_seq":int(r.expected_seq),"fold":str(r.fold),"symbol":str(r.symbol),"score":float(r[BASE_SCORE]),"eligible_symbols":int(len(g))})
    return pd.DataFrame(rows)


def path_return(frame: pd.DataFrame, signal_seq: int, horizon: int):
    entry_seq=signal_seq+1; exit_seq=signal_seq+horizon
    if entry_seq not in frame.index: return None
    entry=float(frame.loc[entry_seq,"open"])
    if not np.isfinite(entry) or entry<=0: return None
    stop_px=entry*(1+STOP); take_px=entry*(1+TAKE)
    path=frame.reindex(range(entry_seq,exit_seq+1))
    complete=bool(path[["open","high","low","close"]].notna().all(axis=1).all())
    valid=path.dropna(subset=["open","high","low","close"])
    if valid.empty: return None
    for seq,bar in valid.iterrows():
        o=float(bar.open); hi=float(bar.high); lo=float(bar.low)
        if lo<=stop_px:
            px=o if o<=stop_px else stop_px
            return dict(raw_return=px/entry-1,reason="STOP_GAP" if o<=stop_px else "STOP_3PCT",actual_exit_seq=int(seq),path_complete=complete)
        if hi>=take_px:
            px=o if o>=take_px else take_px
            return dict(raw_return=px/entry-1,reason="TAKE_GAP" if o>=take_px else "TAKE_20PCT",actual_exit_seq=int(seq),path_complete=complete)
        day=pd.Timestamp(str(bar.session_date)).date()
        if day.weekday()==4 and int(bar.session_bucket)==5:
            return dict(raw_return=float(bar.close)/entry-1,reason="FRIDAY_FLAT",actual_exit_seq=int(seq),path_complete=complete)
    if exit_seq not in frame.index: return None
    return dict(raw_return=float(frame.loc[exit_seq,"close"])/entry-1,reason=f"HORIZON_{horizon}",actual_exit_seq=exit_seq,path_complete=complete)


def simulate(rank1: pd.DataFrame, root: Path, horizon: int, threshold_bps: float, cache):
    z=rank1[rank1.score*10000 >= threshold_bps].sort_values("expected_seq")
    rows=[]; blocked=-10**18
    for r in z.itertuples(index=False):
        entry_seq=int(r.expected_seq)+1; scheduled_exit=int(r.expected_seq)+horizon
        if entry_seq<=blocked: continue
        frame=load_panel(root,r.symbol,cache)
        if frame.empty: continue
        pr=path_return(frame,int(r.expected_seq),horizon)
        if pr is None: continue
        rows.append({**r._asdict(),"horizon":horizon,"threshold_bps":threshold_bps,"entry_expected_seq":entry_seq,"scheduled_exit_seq":scheduled_exit,**pr})
        # Conservative: early exits do not free a slot before scheduled horizon.
        blocked=scheduled_exit
    return pd.DataFrame(rows)


def metrics(z,cost):
    if z.empty: return {"trades":0}
    r=z.raw_return.astype(float)-cost/10000
    w=(1+r).cumprod(); dd=w/w.cummax()-1
    start=pd.Timestamp(z.iloc[0].timestamp); end=pd.Timestamp(z.iloc[-1].timestamp)
    yrs=max((end-start).total_seconds()/(365.25*86400),1/365.25)
    total=float(w.iloc[-1]-1); cagr=(1+total)**(1/yrs)-1 if total>-1 else -1
    return dict(trades=int(len(z)),total_return=total,cagr=float(cagr),max_drawdown=float(dd.min()),mean_net_return=float(r.mean()),median_net_return=float(r.median()),win_rate=float((r>0).mean()),path_complete_rate=float(z.path_complete.mean()))


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--predictions',type=Path,required=True); ap.add_argument('--panel-root',type=Path,required=True); ap.add_argument('--membership',type=Path,required=True); ap.add_argument('--output-dir',type=Path,required=True); a=ap.parse_args()
    a.output_dir.mkdir(parents=True,exist_ok=True)
    pred=pd.read_parquet(a.predictions,columns=['timestamp','expected_seq','fold','symbol',BASE_SCORE])
    pred['timestamp']=pd.to_datetime(pred.timestamp,utc=True)
    rank1=build_rank1(pred,load_membership(a.membership))
    cache={}; summaries=[]; annual=[]; parts=[]
    for h in HORIZONS:
        for t in THRESHOLDS_BPS:
            z=simulate(rank1,a.panel_root,h,t,cache)
            if not z.empty: parts.append(z)
            reasons=json.dumps(z.reason.value_counts().to_dict(),sort_keys=True) if not z.empty else '{}'
            for cost in COSTS:
                m=metrics(z,cost); summaries.append(dict(horizon=h,threshold_bps=t,cost_bps=cost,**m,exit_reason_counts=reasons))
                if not z.empty:
                    q=z.copy(); q['year']=q.timestamp.dt.year
                    for year,g in q.groupby('year'):
                        annual.append(dict(horizon=h,threshold_bps=t,cost_bps=cost,year=int(year),**metrics(g,cost)))
    S=pd.DataFrame(summaries); A=pd.DataFrame(annual); T=pd.concat(parts,ignore_index=True) if parts else pd.DataFrame()
    S.to_csv(a.output_dir/'live_policy_grid_summary.csv',index=False); A.to_csv(a.output_dir/'live_policy_grid_yearly.csv',index=False); T.to_parquet(a.output_dir/'live_policy_grid_trades.parquet',index=False)
    e=S[np.isclose(S.cost_bps,COSTS[0])].copy(); e['cagr_mdd']=e.cagr/e.max_drawdown.abs()
    # Require at least 50 trades for a research candidate to avoid tiny-sample winners.
    viable=e[(e.trades>=50)&(e.cagr>0)].sort_values(['cagr_mdd','cagr'],ascending=False)
    status={"schema_version":"r5-2-live-policy-grid-v1","status":"COMPLETE","research_only":True,"policy":"STOP3_TAKE20_FRIDAY_FLAT","empirical_cost_bps":COSTS[0],"rank1_rows":int(len(rank1)),"viable_scenarios":int(len(viable)),"top_viable":viable.head(20).replace({np.nan:None}).to_dict('records')}
    (a.output_dir/'status.json').write_text(json.dumps(status,indent=2,ensure_ascii=False,default=str)+'\n')
    print(json.dumps(status,indent=2,ensure_ascii=False,default=str))
    return 0
if __name__=='__main__': raise SystemExit(main())
