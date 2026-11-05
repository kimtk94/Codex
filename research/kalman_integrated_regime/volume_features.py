#!/usr/bin/env python3
"""Research-only completed-session QLD / QQQ SIP 15m volume features.

Features are available after NYSE close only; no LIVE behavior is changed.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import exchange_calendars as xcals
import numpy as np
import pandas as pd

NY = "America/New_York"
SYMBOLS = ("QLD", "QQQ")


def completed_daily_volume(bars: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    required = {"market", "candle_time_utc", "volume", "unit_min"}
    if not required.issubset(bars.columns):
        raise ValueError("VOLUME_MISSING_REQUIRED_FIELDS:" + ",".join(sorted(required - set(bars))))
    bars = bars.copy()
    bars["market"] = bars.market.astype(str).str.upper()
    bars = bars.loc[bars.market.isin(SYMBOLS)].copy()
    if bars.empty or set(bars.market.unique()) != set(SYMBOLS):
        raise ValueError("VOLUME_NEEDS_BOTH_QLD_QQQ")
    if not pd.to_numeric(bars.unit_min, errors="coerce").eq(15).all():
        raise ValueError("VOLUME_WRONG_TIMEFRAME")
    bars["ts_utc"] = pd.to_datetime(bars.candle_time_utc, utc=True, errors="coerce")
    bars["v"] = pd.to_numeric(bars.volume, errors="coerce")
    if (bars.ts_utc.isna().any() or bars.v.isna().any() or
            (bars.v < 0).any() or not np.isfinite(bars.v.to_numpy()).all()):
        raise ValueError("VOLUME_INVALID_TIMESTAMP_OR_SIZE")
    if bars.duplicated(["market", "ts_utc"]).any():
        raise ValueError("VOLUME_DUPLICATE_BAR")
    bars["ts_ny"] = bars.ts_utc.dt.tz_convert(NY)
    bars["session"] = pd.to_datetime(bars.ts_ny.dt.strftime("%Y-%m-%d"))
    cal = xcals.get_calendar("XNYS")
    sessions = cal.sessions_in_range(bars.session.min(), bars.session.max())
    if len(sessions) == 0:
        raise ValueError("VOLUME_NO_SESSIONS")
    groups = {(sym,day): g for (sym,day),g in bars.groupby(["market","session"])}
    rows = []
    missing = 0
    for session in sessions:
        day = pd.Timestamp(session).tz_localize(None)
        op = cal.session_open(session).tz_convert(NY)
        cl = cal.session_close(session).tz_convert(NY)
        expected = pd.date_range(op,cl-pd.Timedelta(minutes=15),freq="15min")
        for sym in SYMBOLS:
            sample = groups.get((sym, day))
            if sample is None:
                complete = False
            else:
                rth = sample.loc[sample.ts_ny.ge(op) & sample.ts_ny.lt(cl)].sort_values("ts_ny")
                complete = pd.DatetimeIndex(rth.ts_ny).equals(expected)
            if not complete:
                missing += 1
                vol = np.nan
            else:
                vol = float(rth.v.sum())
            rows.append({"date_ny":day,"market":sym,
                         "rth_volume_shares":vol,"rth_bars_expected":len(expected),
                         "rth_complete":complete,
                         "available_after_close_utc":cl.tz_convert("UTC").isoformat()})
    result = pd.DataFrame(rows)
    qa = {"schema":"qld-qqq-volume-completed-rth-v1",
          "source":"ALPACA_SIP_15MIN_BARS",
          "rth_sessions":len(sessions),
          "rth_rows":len(result),
          "complete_rth_rows":int(result.rth_complete.sum()),
          "partial_or_missing_rth_rows":missing,
          "no_missing_volume_imputation":True,
          "signal_time":"END_OF_SESSION_ONLY_NEXT_SESSION_ENTRY",
          "retained_native_volume_units":"SHARES_PER_15MIN_BAR"}
    return result,qa


def volume_features(bars:pd.DataFrame,history:int=20)->tuple[pd.DataFrame,dict]:
    if history < 5:
        raise ValueError("HISTORY_LT_FIVE")
    daily,qa = completed_daily_volume(bars)
    f = pd.DataFrame(index=pd.DatetimeIndex(sorted(daily.date_ny.unique())))
    for sym in SYMBOLS:
        d=daily.loc[daily.market.eq(sym)].set_index("date_ny").reindex(f.index)
        volume=d.rth_volume_shares.astype(float)
        prior=volume.shift(1).rolling(history,min_periods=history)
        median=prior.median().where(lambda x:x>0)
        std=prior.std(ddof=0).where(lambda x:x>0)
        name=sym.lower()
        f[f"{name}_rth_volume"]=volume
        f[f"{name}_rvol{history}"]=volume/median
        f[f"{name}_volume_z{history}"]=(volume-prior.mean())/std
        rv=f[f"{name}_rvol{history}"]
        f[f"{name}_volume_2x{history}"]=rv.ge(2).where(rv.notna())
    f[f"qld_qqq_rvol{history}_diff"]=f[f"qld_rvol{history}"]-f[f"qqq_rvol{history}"]
    f.index.name="date_ny"
    qa.update({"history_completed_sessions":history,
               "reference_excludes_signal_date":True,
               "same_day_information_available_only_after_rth_close":True,
               "first_valid_reference_requires_consecutive_complete_sessions":True,
               "feature_columns":list(f.columns),
               "non_na_rvol_rows_qqq":int(f[f"qqq_rvol{history}"].notna().sum()),
               "non_na_rvol_rows_qld":int(f[f"qld_rvol{history}"].notna().sum())})
    return f,qa


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--intraday",required=True)
    p.add_argument("--out-dir",required=True)
    p.add_argument("--history",type=int,default=20)
    args=p.parse_args()
    out=Path(args.out_dir)
    out.mkdir(parents=True,exist_ok=True)
    f,qa=volume_features(pd.read_parquet(args.intraday),args.history)
    f.reset_index().to_parquet(out/"volume_features_completed_rth.parquet",index=False)
    (out/"volume_features_qa.json").write_text(json.dumps(qa,indent=2)+"\n")
    print("QLD_QQQ_VOLUME_FEATURES "+json.dumps(qa))


if __name__=="__main__":
    main()
