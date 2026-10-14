#!/usr/bin/env python3
"""Read-only Binance ETHUSDT daily regime study. No live orders or set -e."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

def load(path):
    p = Path(path).expanduser()
    files = [p] if p.is_file() else sorted(p.glob("ETHUSDT_*_1d.parquet"))
    if not files:
        raise FileNotFoundError(f"No ETHUSDT daily Parquet files: {p}")
    rows = []
    for file in files:
        frame = pd.read_parquet(file)
        frame.columns = [str(c).strip().lower() for c in frame.columns]
        time_key = next((c for c in ("open_time", "timestamp", "datetime", "date", "time") if c in frame), None)
        if time_key is None and isinstance(frame.index, pd.DatetimeIndex):
            frame = frame.reset_index().rename(columns={frame.index.name or "index": "datetime"})
            time_key = "datetime"
        if not time_key or not {"open", "high", "low", "close"}.issubset(frame):
            raise ValueError(f"Unrecognized parquet schema: {file}: {list(frame.columns)}")
        source = frame[time_key]
        if pd.api.types.is_numeric_dtype(source):
            numeric = pd.to_numeric(source, errors="coerce")
            magnitude = numeric.dropna().abs().median()
            unit = "us" if magnitude >= 1e14 else "ms" if magnitude >= 1e11 else "s"
            dt = pd.to_datetime(numeric, unit=unit, utc=True, errors="coerce")
        else:
            dt = pd.to_datetime(source, utc=True, errors="coerce")
        frame = frame[["open", "high", "low", "close"]].apply(pd.to_numeric, errors="coerce")
        frame["datetime"] = dt
        rows.append(frame)
    result = pd.concat(rows, ignore_index=True).dropna().sort_values("datetime")
    duplicates = int(result.datetime.duplicated().sum())
    result = result.drop_duplicates("datetime", keep="last").set_index("datetime")
    result = result[(result.index >= "2017-01-01") & (result.index < "2024-01-01")]
    if result.empty:
        raise ValueError("No 2017-2023 data")
    return result, files, duplicates

def analyze(raw):
    if raw.index.to_series().diff().dropna().lt(pd.Timedelta(days=1)).any():
        raise ValueError("Expected 1d candles, but intraday timestamps detected")
    daily = raw.resample("1D").agg({"open":"first","high":"max","low":"min","close":"last"})
    complete = daily[["open","high","low","close"]].notna().all(axis=1)
    daily["observed"] = complete
    daily["log_return"] = np.log(daily.close / daily.close.shift(1))
    daily["vol30"] = daily.log_return.rolling(30, min_periods=30).std() * np.sqrt(365)
    daily["ema50"] = daily.close.ewm(span=50, adjust=False, min_periods=50).mean()
    daily["ema200"] = daily.close.ewm(span=200, adjust=False, min_periods=200).mean()
    daily["trend_gap"] = daily.ema50 / daily.ema200 - 1
    daily["ret7"] = daily.close / daily.close.shift(7) - 1
    daily["dd90"] = daily.close / daily.close.rolling(90, min_periods=90).max() - 1
    threshold_sample = daily.loc["2017":"2022", "vol30"].dropna()
    if len(threshold_sample) < 200:
        raise ValueError("Insufficient pre-2023 volatility calibration sample")
    vol_high = float(threshold_sample.quantile(.75))
    regime = np.select(
        [(daily.dd90 <= -.25) | ((daily.ret7 <= -.18) & (daily.vol30 >= vol_high)),
         daily.trend_gap <= -.025,
         daily.trend_gap >= .025],
        ["CRASH_STRESS", "BEAR", "BULL"],
        default="RANGE")
    combined = np.where(regime == "BULL", np.where(daily.vol30 >= vol_high, "BULL_HIGH_VOL", "BULL_LOW_VOL"),
               np.where(regime == "RANGE", np.where(daily.vol30 >= vol_high, "RANGE_HIGH_VOL", "RANGE_LOW_VOL"), regime))
    valid = complete.rolling(200, min_periods=200).sum().eq(200)
    daily["regime"] = np.where(valid, combined, "WARMUP_OR_GAP")
    for horizon in (7, 30):
        future_coverage = complete.iloc[::-1].rolling(horizon+1, min_periods=horizon+1).sum().iloc[::-1].eq(horizon+1)
        daily[f"forward_{horizon}d"] = (daily.close.shift(-horizon)/daily.close - 1).where(future_coverage)
    daily["segment_id"] = daily.regime.ne(daily.regime.shift()).cumsum()
    sub = daily[daily.regime != "WARMUP_OR_GAP"]
    summary = sub.groupby("regime").agg(days=("close","size"), median_vol=("vol30","median"),
        forward_7d_mean=("forward_7d","mean"), forward_30d_mean=("forward_30d","mean"),
        median_drawdown=("dd90","median"))
    summary["share"] = summary.days/len(sub) if len(sub) else np.nan
    segments = sub.groupby("segment_id").agg(regime=("regime","first"), days=("close","size"),
        start=("close",lambda x:x.index.min()), end=("close",lambda x:x.index.max()))
    coverage = daily.assign(month=daily.index.strftime("%Y-%m")).groupby("month").agg(
        expected_days=("observed","size"), observed_days=("observed","sum"))
    coverage["missing_days"] = coverage.expected_days - coverage.observed_days
    coverage["coverage"] = coverage.observed_days / coverage.expected_days
    return daily, summary, segments, coverage, vol_high

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/home/taehoon/BOX_OCCUPANCY_RESEARCH_20261012/regime_history_spot")
    ap.add_argument("--out", default="/home/taehoon/BOX_OCCUPANCY_RESEARCH_20261012/regime_results")
    args = ap.parse_args()
    raw, files, duplicates = load(args.input)
    daily, summary, segments, coverage, threshold = analyze(raw)
    dest = Path(args.out).expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    daily.to_csv(dest/"daily_regimes.csv")
    summary.to_csv(dest/"regime_summary.csv")
    segments.to_csv(dest/"regime_segments.csv")
    coverage.to_csv(dest/"monthly_coverage.csv")
    audit = {"status":"COMPLETE", "role":"REGIME_ONLY", "input_market":"VERIFY_SPOT_OR_FUTURES",
        "source_files":len(files), "duplicates":duplicates, "daily_rows":len(daily),
        "valid_regime_days":int((daily.regime!="WARMUP_OR_GAP").sum()),
        "missing_days":int((~daily.observed).sum()),
        "volatility_threshold":threshold, "calibration":"2017-2022", "holdout":"2023",
        "warning":"Never use these prices for Upbit order fills or KRW PnL."}
    (dest/"audit.json").write_text(json.dumps(audit,indent=2),encoding="utf-8")
    print(json.dumps(audit, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
