#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
SCHEMA_VERSION = "kalman-r5-conditional-challenger-stress-v1"

FREEZE = {
    "gap_quantile": 0.35,
    "confidence_quantile": 0.30,
    "rank2_weight": 0.50,
    "cash_fraction": 0.50,
    "min_history": 100,
}


def _remote_spec(remote: str, relative: Path) -> str:
    remote = remote.strip()
    if not remote.endswith(":"):
        remote = remote.rstrip("/") + ":"
    return remote + relative.as_posix().lstrip("/")


def _stage(path: Path, cache_root: Path, remote: str) -> Path:
    if path.is_file():
        return path
    rel = path.relative_to("/mnt/gdrive")
    target = cache_root / rel
    if target.is_file():
        return target
    if shutil.which("rclone") is None:
        raise RuntimeError("rclone not found")
    target.parent.mkdir(parents=True, exist_ok=True)
    src = _remote_spec(remote, rel)
    print(f"[RCLONE_STAGE] {src} -> {target}", flush=True)
    rc = subprocess.run(["rclone", "copyto", src, str(target)], check=False).returncode
    if rc != 0 or not target.is_file():
        raise FileNotFoundError(src)
    return target


def _read_price(path: Path) -> pd.DataFrame:
    x = pd.read_parquet(path)
    seq = next(c for c in ("expected_seq","seq","bar_seq") if c in x.columns)
    close = next(c for c in ("close","adj_close") if c in x.columns)
    ts = next((c for c in ("timestamp","ts") if c in x.columns), None)
    out = pd.DataFrame({
        "expected_seq": pd.to_numeric(x[seq], errors="coerce"),
        "close": pd.to_numeric(x[close], errors="coerce"),
    })
    if ts:
        out["timestamp"] = pd.to_datetime(x[ts], utc=True, errors="coerce")
    else:
        mo = pd.to_datetime(x["market_open_utc"], utc=True, errors="coerce")
        bucket = pd.to_numeric(x["session_bucket"], errors="coerce")
        out["timestamp"] = mo + pd.to_timedelta(bucket, unit="h")
    return out.dropna().sort_values("expected_seq").drop_duplicates("expected_seq", keep="last")


class Prices:
    def __init__(self, panel: Path, cache: Path, remote: str):
        self.panel = panel
        self.cache = cache
        self.remote = remote
        self.mem = {}

    def frame(self, symbol: str) -> pd.DataFrame:
        if symbol in self.mem:
            return self.mem[symbol]
        p = self.panel / f"{symbol}_1h_gap_aware.parquet"
        local = _stage(p, self.cache, self.remote)
        self.mem[symbol] = _read_price(local)
        return self.mem[symbol]

    def at(self, symbol: str, seq: int):
        f = self.frame(symbol)
        z = f.loc[f.expected_seq.eq(int(seq))]
        if z.empty:
            return None, None
        r = z.iloc[-1]
        return pd.Timestamp(r.timestamp), float(r.close)

    def friday_exit(self, symbol: str, entry_seq: int, fixed_exit_seq: int) -> int:
        f = self.frame(symbol)
        z = f.loc[f.expected_seq.between(entry_seq, fixed_exit_seq)].copy()
        if z.empty:
            return fixed_exit_seq
        z["date_et"] = z.timestamp.dt.tz_convert(NY).dt.date
        z["weekday_et"] = z.timestamp.dt.tz_convert(NY).dt.weekday
        fixed = z.loc[z.expected_seq.eq(fixed_exit_seq)]
        if fixed.empty:
            return fixed_exit_seq
        fixed_date = fixed.iloc[-1]["date_et"]
        fri = z.loc[(z.weekday_et == 4) & (z.date_et < fixed_date)]
        if fri.empty:
            return fixed_exit_seq
        d = fri.date_et.max()
        return int(fri.loc[fri.date_et.eq(d), "expected_seq"].max())


def build_horizon_panel(base: pd.DataFrame, prices: Prices, horizon: int) -> pd.DataFrame:
    rows = []
    for _, r in base.iterrows():
        seq = int(r.expected_seq)
        s1, s2 = str(r.rank1_symbol), str(r.rank2_symbol)
        e1t, e1 = prices.at(s1, seq)
        e2t, e2 = prices.at(s2, seq)
        if None in (e1t, e1, e2t, e2):
            continue
        fx = seq + horizon
        ex = prices.friday_exit(s1, seq, fx)
        x1t, x1 = prices.at(s1, ex)
        x2t, x2 = prices.at(s2, ex)
        if None in (x1t, x1, x2t, x2):
            continue
        q = r.copy()
        q["exit_timestamp"] = x1t
        q["actual_exit_seq"] = ex
        q["rank1_raw_return"] = x1 / e1 - 1.0
        q["rank2_raw_return"] = x2 / e2 - 1.0
        rows.append(q)
    return pd.DataFrame(rows)


def prepare(panel: pd.DataFrame, gq: float, cq: float, min_history: int) -> pd.DataFrame:
    z = panel.sort_values(["entry_timestamp","expected_seq"]).reset_index(drop=True).copy()
    z["entry_timestamp"] = pd.to_datetime(z.entry_timestamp, utc=True)
    z["exit_timestamp"] = pd.to_datetime(z.exit_timestamp, utc=True)
    z["score_gap"] = z.rank1_score - z.rank2_score
    z["relative_score_gap"] = z.score_gap / z.rank1_score.abs().clip(lower=1e-12)
    z["gap_threshold"] = z.relative_score_gap.shift(1).expanding(min_periods=min_history).quantile(gq)
    z["confidence_threshold"] = z.rank1_score.shift(1).expanding(min_periods=min_history).quantile(cq)
    z["ready"] = z.gap_threshold.notna() & z.confidence_threshold.notna()
    z["close_gap"] = z.ready & (z.relative_score_gap <= z.gap_threshold)
    z["low_conf"] = z.ready & (z.rank1_score <= z.confidence_threshold)
    return z


def simulate(z: pd.DataFrame, cost_bps: float, rank2_weight=.5, cash_fraction=.5) -> pd.DataFrame:
    out = z.copy()
    w1 = np.ones(len(z)); w2 = np.zeros(len(z)); cash = np.zeros(len(z))
    low = z.low_conf.to_numpy(bool)
    gap = (z.close_gap & ~z.low_conf).to_numpy(bool)
    w1[low] = 1-cash_fraction; cash[low] = cash_fraction
    w1[gap] = 1-rank2_weight; w2[gap] = rank2_weight
    gross = w1*z.rank1_raw_return.to_numpy(float) + w2*z.rank2_raw_return.to_numpy(float)
    invested = w1+w2
    out["net_return"] = gross - (cost_bps/10000.0)*invested
    out["rank1_weight"]=w1; out["rank2_weight"]=w2; out["cash_weight"]=cash
    return out


def metrics(df: pd.DataFrame) -> dict:
    r = pd.to_numeric(df.net_return, errors="coerce").dropna()
    if r.empty: return {}
    wealth=(1+r).cumprod(); dd=wealth/wealth.cummax()-1
    total=float(wealth.iloc[-1]-1)
    start=pd.Timestamp(df.entry_timestamp.min()); end=pd.Timestamp(df.exit_timestamp.max())
    years=max((end-start).total_seconds()/(365.25*86400),1/365.25)
    cagr=float((1+total)**(1/years)-1) if total>-1 else -1
    sd=float(r.std(ddof=0)); tpy=len(r)/years
    sharpe=float(r.mean()/sd*math.sqrt(tpy)) if sd>0 else None
    return {
        "trades":len(r),"total_return":total,"cagr":cagr,
        "max_drawdown":float(dd.min()),
        "cagr_over_abs_mdd":float(cagr/abs(dd.min())) if dd.min()<0 else None,
        "sharpe":sharpe,"win_rate":float((r>0).mean()),
        "mean_net_return":float(r.mean())
    }


def block_bootstrap_delta(ch: pd.DataFrame, base: pd.DataFrame, reps: int, block: int, seed: int) -> dict:
    a=ch.net_return.to_numpy(float); b=base.net_return.to_numpy(float)
    n=min(len(a),len(b)); a=a[:n]; b=b[:n]
    rng=np.random.default_rng(seed); vals=[]
    starts=np.arange(max(1,n-block+1))
    for _ in range(reps):
        idx=[]
        while len(idx)<n:
            s=int(rng.choice(starts))
            idx.extend(range(s,min(s+block,n)))
        idx=np.asarray(idx[:n])
        vals.append(float(a[idx].mean()-b[idx].mean()))
    v=np.asarray(vals)
    return {
        "reps":reps,"block":block,
        "mean_delta":float(v.mean()),
        "p_delta_gt_0":float((v>0).mean()),
        "p05":float(np.quantile(v,.05)),
        "p50":float(np.quantile(v,.50)),
        "p95":float(np.quantile(v,.95)),
    }


def main():
    p=argparse.ArgumentParser()
    home=Path.home()
    p.add_argument("--input",type=Path,default=home/".cache/kalman-r5-topk/output/r5_1_topk_portfolio_v1/r5_topk_common_trade_panel.parquet")
    p.add_argument("--output-dir",type=Path,default=home/".cache/kalman-r5-topk/output/r5_1_conditional_challenger_stress_v1")
    p.add_argument("--cache-root",type=Path,default=home/".cache/kalman-r5-topk/data")
    p.add_argument("--rclone-remote",default="gdrive:")
    p.add_argument("--locked-panel",type=Path,default=Path("/mnt/gdrive/US_ETF/directional_research/canonical_history_v1/panel_1h_gap_aware"))
    p.add_argument("--bootstrap-reps",type=int,default=2000)
    args=p.parse_args()

    base_panel=pd.read_parquet(args.input)
    prices=Prices(args.locked_panel,args.cache_root,args.rclone_remote)
    rows=[]; boot=[]

    for horizon in [3,4,5]:
        panel = base_panel.copy() if horizon==4 else build_horizon_panel(base_panel,prices,horizon)
        for gq in [0.30,0.35,0.40]:
            for cq in [0.25,0.30,0.35]:
                z=prepare(panel,gq,cq,FREEZE["min_history"])
                for cost in [10,20,30,50]:
                    ch=simulate(z,cost,.5,.5)
                    top1=z.copy(); top1["net_return"]=z.rank1_raw_return.astype(float)-cost/10000.0
                    cm=metrics(ch); bm=metrics(top1)
                    row={
                        "horizon":horizon,"gap_quantile":gq,"confidence_quantile":cq,
                        "cost_bps":cost,**{f"challenger_{k}":v for k,v in cm.items()},
                        **{f"top1_{k}":v for k,v in bm.items()},
                    }
                    row["delta_cagr"]=cm.get("cagr",np.nan)-bm.get("cagr",np.nan)
                    row["delta_mdd"]=cm.get("max_drawdown",np.nan)-bm.get("max_drawdown",np.nan)
                    row["delta_sharpe"]=(cm.get("sharpe") or np.nan)-(bm.get("sharpe") or np.nan)
                    row["pass_cagr"]=bool(row["delta_cagr"]>=0)
                    row["pass_mdd"]=bool(row["delta_mdd"]>=0)
                    row["pass_joint"]=bool(row["pass_cagr"] and row["pass_mdd"])
                    rows.append(row)

                    if horizon==4 and gq==.35 and cq==.30 and cost in [10,30,50]:
                        bs=block_bootstrap_delta(ch,top1,args.bootstrap_reps,20,20261002+cost)
                        boot.append({"horizon":horizon,"gap_quantile":gq,"confidence_quantile":cq,"cost_bps":cost,**bs})

    stress=pd.DataFrame(rows)
    bootstrap=pd.DataFrame(boot)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    stress.to_csv(args.output_dir/"stress_grid.csv",index=False)
    bootstrap.to_csv(args.output_dir/"block_bootstrap.csv",index=False)

    nominal=stress.loc[
        (stress.horizon.eq(4)) & (stress.gap_quantile.eq(.35)) &
        (stress.confidence_quantile.eq(.30)) & (stress.cost_bps.eq(10))
    ].iloc[0].to_dict()

    status={
        "schema_version":SCHEMA_VERSION,"status":"COMPLETE","freeze":FREEZE,
        "stress_cases":int(len(stress)),
        "joint_pass_cases":int(stress.pass_joint.sum()),
        "nominal":nominal,
        "bootstrap":bootstrap.to_dict(orient="records"),
        "promotion_gate":{
            "all_costs_10_20_30_50_nominal_threshold_joint_pass":bool(
                stress.loc[(stress.horizon.eq(4))&(stress.gap_quantile.eq(.35))&(stress.confidence_quantile.eq(.30))].pass_joint.all()
            ),
            "all_threshold_perturbations_at_10bp_joint_pass":bool(
                stress.loc[(stress.horizon.eq(4))&(stress.cost_bps.eq(10))].pass_joint.all()
            ),
            "all_horizons_nominal_threshold_at_10bp_joint_pass":bool(
                stress.loc[(stress.gap_quantile.eq(.35))&(stress.confidence_quantile.eq(.30))&(stress.cost_bps.eq(10))].pass_joint.all()
            ),
        }
    }
    (args.output_dir/"status.json").write_text(json.dumps(status,indent=2,default=str)+"\n")
    print(json.dumps(status,indent=2,default=str))
    print("\n===== NOMINAL + NEIGHBORS =====")
    print(stress.loc[(stress.cost_bps.eq(10)) & (stress.horizon.eq(4))].sort_values("challenger_cagr_over_abs_mdd",ascending=False).head(20).to_csv(index=False))
    print("===== BOOTSTRAP =====")
    print(bootstrap.to_csv(index=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
