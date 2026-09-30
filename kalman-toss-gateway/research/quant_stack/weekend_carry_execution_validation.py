from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


@dataclass
class PricePoint:
    price: float | None
    timestamp: pd.Timestamp | None
    source_file: str | None
    source_feed: str | None
    distance_seconds: float | None


def _find_root(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if p.exists():
            return p
        raise FileNotFoundError(p)

    candidates = [
        Path("/mnt/gdrive/US_ETF/directional_research/live_policy_replay_1m_alpaca_v1"),
        Path("/mnt/gdrive/directional_research/live_policy_replay_1m_alpaca_v1"),
        Path("/content/drive/MyDrive/US_ETF/directional_research/live_policy_replay_1m_alpaca_v1"),
    ]
    for p in candidates:
        if p.exists():
            return p

    for base in [Path("/mnt/gdrive/US_ETF"), Path("/mnt/gdrive"), Path("/content/drive/MyDrive")]:
        if not base.exists():
            continue
        try:
            for p in base.glob("**/live_policy_replay_1m_alpaca_v1"):
                if p.is_dir():
                    return p
        except OSError:
            continue
    raise FileNotFoundError("live_policy_replay_1m_alpaca_v1 root not found")


def _normalize_minute_frame(df: pd.DataFrame, source_file: Path, feed: str) -> pd.DataFrame:
    x = df.copy()
    if isinstance(x.index, (pd.DatetimeIndex, pd.MultiIndex)):
        x = x.reset_index()

    lower = {str(c).lower(): c for c in x.columns}
    ts_col = next((lower[k] for k in ("timestamp", "time", "datetime", "t", "ts") if k in lower), None)
    if ts_col is None:
        for c in x.columns:
            if "time" in str(c).lower():
                ts_col = c
                break
    if ts_col is None:
        raise RuntimeError(f"timestamp column missing: {source_file} columns={list(x.columns)}")

    close_col = next((lower[k] for k in ("close", "c", "price", "last") if k in lower), None)
    if close_col is None:
        raise RuntimeError(f"close column missing: {source_file} columns={list(x.columns)}")

    out = pd.DataFrame({
        "timestamp": pd.to_datetime(x[ts_col], utc=True, errors="coerce"),
        "close": pd.to_numeric(x[close_col], errors="coerce"),
    })

    for key in ("vwap", "vw"):
        if key in lower:
            out["vwap"] = pd.to_numeric(x[lower[key]], errors="coerce")
            break
    if "vwap" not in out:
        out["vwap"] = np.nan

    out["source_file"] = str(source_file)
    out["source_feed"] = feed
    out = out.dropna(subset=["timestamp", "close"]).sort_values("timestamp")
    return out.drop_duplicates(subset=["timestamp"], keep="last")


def _load_symbol_feed(root: Path, feed: str, symbol: str) -> pd.DataFrame:
    folder = root / feed / symbol.upper()
    if not folder.exists():
        return pd.DataFrame(columns=["timestamp", "close", "vwap", "source_file", "source_feed"])

    frames = []
    for file in sorted(folder.glob("*.parquet")):
        try:
            raw = pd.read_parquet(file)
            frames.append(_normalize_minute_frame(raw, file, feed))
        except Exception as exc:
            print(f"[WARN] {feed}/{symbol} read failed {file.name}: {exc}")
    if not frames:
        return pd.DataFrame(columns=["timestamp", "close", "vwap", "source_file", "source_feed"])
    return (
        pd.concat(frames, ignore_index=True)
        .sort_values("timestamp")
        .drop_duplicates(subset=["timestamp"], keep="last")
        .reset_index(drop=True)
    )


def _regular_mask(local_ts: pd.Series) -> pd.Series:
    mins = local_ts.dt.hour * 60 + local_ts.dt.minute
    return (mins >= 9 * 60 + 30) & (mins < 16 * 60)


def _session_table(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["session_date", "first_ts", "last_ts", "regular_end"])

    x = frame.copy()
    x["local_ts"] = x["timestamp"].dt.tz_convert(NY)
    x = x.loc[_regular_mask(x["local_ts"])].copy()
    if x.empty:
        return pd.DataFrame(columns=["session_date", "first_ts", "last_ts", "regular_end"])

    x["session_date"] = x["local_ts"].dt.date
    rows = []
    for d, g in x.groupby("session_date", sort=True):
        first_ts = g["local_ts"].min()
        last_ts = g["local_ts"].max()
        # Alpaca 1m timestamps normally mark minute start; last regular bar
        # 15:59 implies a 16:00 session end, 12:59 implies 13:00 early close.
        regular_end = last_ts.floor("min") + pd.Timedelta(minutes=1)
        rows.append({
            "session_date": d,
            "first_ts": first_ts,
            "last_ts": last_ts,
            "regular_end": regular_end,
        })
    return pd.DataFrame(rows).sort_values("session_date").reset_index(drop=True)


def _find_pregap_session(
    sessions: pd.DataFrame,
    entry_utc: pd.Timestamp,
    fixed_exit_utc: pd.Timestamp,
) -> dict | None:
    if sessions.empty:
        return None

    entry_date = entry_utc.tz_convert(NY).date()
    exit_date = fixed_exit_utc.tz_convert(NY).date()

    s = sessions.loc[
        (sessions["session_date"] >= entry_date)
        & (sessions["session_date"] <= exit_date)
    ].copy()
    if len(s) < 2:
        return None

    dates = list(s["session_date"])
    best = None
    for i in range(len(dates) - 1):
        a, b = dates[i], dates[i + 1]
        gap_days = (b - a).days
        is_friday = pd.Timestamp(a).weekday() == 4
        crosses_weekend = is_friday and b > a
        long_gap = gap_days >= 3
        if crosses_weekend or long_gap:
            best = s.iloc[i].to_dict()

    return best


def _point_near(
    frame: pd.DataFrame,
    target: pd.Timestamp,
    *,
    before_seconds: int,
    after_seconds: int,
    prefer_before: bool = True,
) -> PricePoint:
    if frame.empty:
        return PricePoint(None, None, None, None, None)

    lo = target - pd.Timedelta(seconds=before_seconds)
    hi = target + pd.Timedelta(seconds=after_seconds)
    x = frame.loc[(frame["timestamp"] >= lo) & (frame["timestamp"] <= hi)].copy()
    if x.empty:
        return PricePoint(None, None, None, None, None)

    x["delta"] = (x["timestamp"] - target).dt.total_seconds()
    if prefer_before:
        before = x.loc[x["delta"] <= 0]
        if not before.empty:
            row = before.sort_values(["delta"], ascending=False).iloc[0]
        else:
            row = x.iloc[x["delta"].abs().argmin()]
    else:
        row = x.iloc[x["delta"].abs().argmin()]

    price = float(row["vwap"]) if pd.notna(row.get("vwap")) and float(row["vwap"]) > 0 else float(row["close"])
    return PricePoint(
        price=price,
        timestamp=pd.Timestamp(row["timestamp"]),
        source_file=str(row.get("source_file")),
        source_feed=str(row.get("source_feed")),
        distance_seconds=float(row["delta"]),
    )


def _paired_bootstrap(delta: np.ndarray, seed: int = 20261001, n_boot: int = 20000) -> dict:
    d = np.asarray(delta, dtype=float)
    d = d[np.isfinite(d)]
    if len(d) == 0:
        return {"n": 0, "mean": None, "ci95_low": None, "ci95_high": None, "p_le_zero": None}
    rng = np.random.default_rng(seed)
    n = len(d)
    means = np.empty(n_boot)
    for i in range(n_boot):
        means[i] = d[rng.integers(0, n, n)].mean()
    return {
        "n": n,
        "mean": float(d.mean()),
        "median": float(np.median(d)),
        "ci95_low": float(np.quantile(means, 0.025)),
        "ci95_high": float(np.quantile(means, 0.975)),
        "p_le_zero": float((means <= 0).mean()),
        "positive_share": float((d > 0).mean()),
    }


def _trade_equity_metrics(r: pd.Series) -> dict:
    arr = pd.to_numeric(r, errors="coerce").dropna().to_numpy(float)
    if not len(arr):
        return {}
    log_growth = float(np.log1p(np.clip(arr, -0.999999, None)).sum())
    eq = np.cumprod(1 + arr)
    peak = np.maximum.accumulate(np.r_[1.0, eq])[1:]
    return {
        "n": int(len(arr)),
        "cum_return": float(np.exp(log_growth) - 1),
        "log_growth": log_growth,
        "mdd_trade_path": float((eq / peak - 1).min()),
        "hit_rate": float((arr > 0).mean()),
        "mean_return": float(arr.mean()),
        "median_return": float(np.median(arr)),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--audit",
        default="/mnt/gdrive/US_ETF/model_lab_v1/results/weekend_carry_policy_v1/weekend_carry_policy_trade_audit.parquet",
    )
    ap.add_argument("--alpaca-root", default=None)
    ap.add_argument(
        "--outdir",
        default="/mnt/gdrive/US_ETF/model_lab_v1/results/weekend_carry_execution_validation_v1",
    )
    ap.add_argument("--primary-feed", default="iex+boats")
    ap.add_argument("--secondary-feed", default="sip+boats")
    ap.add_argument("--buffer-minutes", type=int, default=15)
    args = ap.parse_args()

    root = _find_root(args.alpaca_root)
    audit = pd.read_parquet(args.audit)

    required = {
        "policy", "spans_weekend", "symbol", "entry_timestamp",
        "fixed4_exit_timestamp", "baseline_gross_return",
        "baseline_net_return", "fold",
    }
    missing = required - set(audit.columns)
    if missing:
        raise RuntimeError(f"audit missing columns: {sorted(missing)}")

    weekend = audit.loc[
        (audit["policy"].astype(str) == "CARRY_ALL")
        & audit["spans_weekend"].astype(bool)
    ].copy()
    weekend["entry_timestamp"] = pd.to_datetime(weekend["entry_timestamp"], utc=True)
    weekend["fixed4_exit_timestamp"] = pd.to_datetime(weekend["fixed4_exit_timestamp"], utc=True)
    weekend = weekend.sort_values(["entry_timestamp", "symbol"]).reset_index(drop=True)

    symbols = sorted(weekend["symbol"].astype(str).str.upper().unique())
    print("alpaca_root =", root)
    print("weekend_trades =", len(weekend))
    print("symbols =", len(symbols))

    cache: dict[tuple[str, str], pd.DataFrame] = {}
    sessions: dict[tuple[str, str], pd.DataFrame] = {}

    for feed in (args.primary_feed, args.secondary_feed):
        for symbol in symbols:
            f = _load_symbol_feed(root, feed, symbol)
            cache[(feed, symbol)] = f
            sessions[(feed, symbol)] = _session_table(f)

    rows = []

    for trade_id, row in weekend.iterrows():
        symbol = str(row["symbol"]).upper()
        entry = pd.Timestamp(row["entry_timestamp"])
        fixed_exit = pd.Timestamp(row["fixed4_exit_timestamp"])
        baseline_gross = float(row["baseline_gross_return"])
        baseline_net = float(row["baseline_net_return"])
        cost_proxy = baseline_gross - baseline_net

        rec = {
            "weekend_trade_id": int(trade_id),
            "source_trade_id": int(row["trade_id"]) if "trade_id" in row.index else int(trade_id),
            "fold": row["fold"],
            "symbol": symbol,
            "entry_timestamp": entry,
            "fixed4_exit_timestamp": fixed_exit,
            "baseline_gross_return": baseline_gross,
            "baseline_net_return": baseline_net,
            "cost_proxy": cost_proxy,
        }

        for feed in (args.primary_feed, args.secondary_feed):
            frame = cache[(feed, symbol)]
            sess = sessions[(feed, symbol)]
            pregap = _find_pregap_session(sess, entry, fixed_exit)

            prefix = feed.replace("+", "_").replace("-", "_")
            if pregap is None:
                rec[f"{prefix}_covered"] = False
                rec[f"{prefix}_reason"] = "NO_PREGAP_SESSION"
                continue

            regular_end_local = pd.Timestamp(pregap["regular_end"])
            fractional_end_local = regular_end_local - pd.Timedelta(hours=1)
            safe_deadline_local = fractional_end_local - pd.Timedelta(minutes=args.buffer_minutes)
            safe_deadline_utc = safe_deadline_local.tz_convert(UTC)

            safe = _point_near(
                frame,
                safe_deadline_utc,
                before_seconds=5 * 60,
                after_seconds=2 * 60,
                prefer_before=True,
            )
            fixed = _point_near(
                frame,
                fixed_exit,
                before_seconds=10 * 60,
                after_seconds=10 * 60,
                prefer_before=False,
            )

            after = sess.loc[sess["session_date"] > pregap["session_date"]]
            next_open = PricePoint(None, None, None, None, None)
            next_session_date = None
            if not after.empty:
                nxt = after.iloc[0]
                next_session_date = nxt["session_date"]
                next_open_target = pd.Timestamp(nxt["first_ts"]).tz_convert(UTC)
                next_open = _point_near(
                    frame,
                    next_open_target,
                    before_seconds=60,
                    after_seconds=5 * 60,
                    prefer_before=False,
                )

            covered = safe.price is not None and fixed.price is not None
            rec.update({
                f"{prefix}_covered": bool(covered),
                f"{prefix}_pregap_session": str(pregap["session_date"]),
                f"{prefix}_regular_end_local": regular_end_local,
                f"{prefix}_fractional_end_local": fractional_end_local,
                f"{prefix}_safe_deadline_local": safe_deadline_local,
                f"{prefix}_safe_price": safe.price,
                f"{prefix}_safe_timestamp": safe.timestamp,
                f"{prefix}_safe_distance_seconds": safe.distance_seconds,
                f"{prefix}_fixed4_price": fixed.price,
                f"{prefix}_fixed4_timestamp": fixed.timestamp,
                f"{prefix}_fixed4_distance_seconds": fixed.distance_seconds,
                f"{prefix}_next_session_date": str(next_session_date) if next_session_date else None,
                f"{prefix}_next_open_price": next_open.price,
                f"{prefix}_next_open_timestamp": next_open.timestamp,
            })

            if covered:
                ratio = float(safe.price) / float(fixed.price)
                friday_gross = (1.0 + baseline_gross) * ratio - 1.0
                friday_net = friday_gross - cost_proxy
                rec[f"{prefix}_friday_flat_gross_return"] = friday_gross
                rec[f"{prefix}_friday_flat_net_return"] = friday_net
                rec[f"{prefix}_friday_flat_minus_carry_net"] = friday_net - baseline_net

            if safe.price is not None and next_open.price is not None:
                rec[f"{prefix}_weekend_gap_return"] = (
                    float(next_open.price) / float(safe.price) - 1.0
                )

        rows.append(rec)

    out = pd.DataFrame(rows)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    out.to_parquet(outdir / "weekend_carry_execution_audit.parquet", index=False)
    out.to_csv(outdir / "weekend_carry_execution_audit.csv", index=False)

    primary = args.primary_feed.replace("+", "_").replace("-", "_")
    secondary = args.secondary_feed.replace("+", "_").replace("-", "_")

    p_cov = out[f"{primary}_covered"].fillna(False)
    s_cov = out[f"{secondary}_covered"].fillna(False)

    p_delta = pd.to_numeric(
        out.loc[p_cov, f"{primary}_friday_flat_minus_carry_net"],
        errors="coerce",
    ).dropna()
    p_gap = pd.to_numeric(
        out.loc[p_cov, f"{primary}_weekend_gap_return"],
        errors="coerce",
    ).dropna()

    all_carry_rows = audit.loc[audit["policy"].astype(str) == "CARRY_ALL"].copy()
    all_carry_rows["replay_net_return"] = pd.to_numeric(
        all_carry_rows["baseline_net_return"], errors="coerce"
    )

    replacement_map = {}
    for _, r in out.loc[p_cov].iterrows():
        key = int(r["source_trade_id"])
        value = r.get(f"{primary}_friday_flat_net_return")
        if pd.notna(value):
            replacement_map[key] = float(value)

    if "trade_id" in all_carry_rows.columns:
        mask = all_carry_rows["trade_id"].isin(replacement_map)
        all_carry_rows.loc[mask, "replay_net_return"] = (
            all_carry_rows.loc[mask, "trade_id"].map(replacement_map)
        )

    full_carry_metrics = _trade_equity_metrics(
        pd.to_numeric(all_carry_rows["baseline_net_return"], errors="coerce")
    )
    full_friday_flat_partial_metrics = _trade_equity_metrics(
        pd.to_numeric(all_carry_rows["replay_net_return"], errors="coerce")
    )

    result = {
        "schema": "kalman-weekend-carry-execution-validation-v1",
        "research_only": True,
        "production_changed": False,
        "audit_source": args.audit,
        "alpaca_root": str(root),
        "eligible_weekend_trades": int(len(out)),
        "primary_feed": args.primary_feed,
        "secondary_feed": args.secondary_feed,
        "execution_contract": {
            "regular_session_end_source": "last observed regular 1m bar + 1 minute",
            "fractional_order_end": "regular_session_end - 60 minutes",
            "safe_exit_deadline": f"fractional_order_end - {args.buffer_minutes} minutes",
            "normal_session_safe_exit_et": "14:45 America/New_York" if args.buffer_minutes == 15 else None,
            "safe_price_proxy": "nearest observed 1m VWAP/close at-or-before deadline within 5m, fallback up to +2m",
            "carry_price_proxy": "nearest observed 1m VWAP/close to original FIXED_4 exit timestamp within +/-10m",
        },
        "coverage": {
            "primary_trades": int(p_cov.sum()),
            "primary_ratio": float(p_cov.mean()) if len(out) else 0.0,
            "secondary_trades": int(s_cov.sum()),
            "secondary_ratio": float(s_cov.mean()) if len(out) else 0.0,
        },
        "primary_friday_flat_minus_carry": _paired_bootstrap(p_delta.to_numpy()),
        "primary_weekend_gap": _paired_bootstrap(p_gap.to_numpy()),
        "primary_carry_metrics": _trade_equity_metrics(
            out.loc[p_cov, "baseline_net_return"]
        ),
        "primary_friday_flat_metrics": _trade_equity_metrics(
            out.loc[p_cov, f"{primary}_friday_flat_net_return"]
        ),
        "full_889_carry_metrics": full_carry_metrics,
        "full_889_friday_flat_execution_adjusted_metrics": full_friday_flat_partial_metrics,
        "full_889_adjusted_weekend_trades": int(len(replacement_map)),
        "full_889_adjustment_complete": bool(
            len(replacement_map) == int(len(out))
        ),
    }

    if p_cov.any() and s_cov.any():
        both = p_cov & s_cov
        safe_diff = (
            pd.to_numeric(out.loc[both, f"{secondary}_safe_price"], errors="coerce")
            / pd.to_numeric(out.loc[both, f"{primary}_safe_price"], errors="coerce")
            - 1.0
        ).dropna()
        delta_diff = (
            pd.to_numeric(
                out.loc[both, f"{secondary}_friday_flat_minus_carry_net"],
                errors="coerce",
            )
            - pd.to_numeric(
                out.loc[both, f"{primary}_friday_flat_minus_carry_net"],
                errors="coerce",
            )
        ).dropna()
        result["cross_feed"] = {
            "both_covered": int(both.sum()),
            "safe_price_relative_diff_abs_median": (
                float(safe_diff.abs().median()) if len(safe_diff) else None
            ),
            "policy_delta_diff_abs_median": (
                float(delta_diff.abs().median()) if len(delta_diff) else None
            ),
        }

    folds = []
    for fold, g in out.loc[p_cov].groupby("fold", sort=True):
        d = pd.to_numeric(g[f"{primary}_friday_flat_minus_carry_net"], errors="coerce").dropna()
        folds.append({
            "fold": fold,
            "trades": int(len(d)),
            "mean_friday_flat_minus_carry": float(d.mean()) if len(d) else None,
            "positive_share": float((d > 0).mean()) if len(d) else None,
            "sum_delta": float(d.sum()) if len(d) else None,
        })
    result["folds"] = folds

    # Fail closed for decision-making if execution-price coverage is inadequate.
    result["coverage_gate"] = {
        "required_primary_ratio": 0.90,
        "passed": bool(result["coverage"]["primary_ratio"] >= 0.90),
    }

    (outdir / "weekend_carry_execution_decision.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )

    print("============================================================")
    print("KALMAN WEEKEND CARRY 1M EXECUTION VALIDATION")
    print("============================================================")
    print("eligible_weekend_trades =", len(out))
    print("primary_feed =", args.primary_feed)
    print("primary_coverage =", result["coverage"]["primary_trades"], "/", len(out))
    print("secondary_coverage =", result["coverage"]["secondary_trades"], "/", len(out))
    print("coverage_gate =", result["coverage_gate"])
    print()
    print("FRIDAY_FLAT_MINUS_CARRY")
    print(json.dumps(result["primary_friday_flat_minus_carry"], indent=2))
    print()
    print("WEEKEND_GAP")
    print(json.dumps(result["primary_weekend_gap"], indent=2))
    print()
    print("CARRY_METRICS")
    print(json.dumps(result["primary_carry_metrics"], indent=2))
    print()
    print("FRIDAY_FLAT_METRICS")
    print(json.dumps(result["primary_friday_flat_metrics"], indent=2))
    print()
    print("FULL_889_CARRY")
    print(json.dumps(result["full_889_carry_metrics"], indent=2))
    print()
    print("FULL_889_FRIDAY_FLAT_EXECUTION_ADJUSTED")
    print(json.dumps(result["full_889_friday_flat_execution_adjusted_metrics"], indent=2))
    print("adjusted_weekend_trades =", result["full_889_adjusted_weekend_trades"])
    print("adjustment_complete =", result["full_889_adjustment_complete"])
    print()
    print("FOLDS")
    print(pd.DataFrame(folds).to_string(index=False) if folds else "NONE")
    print()
    if result.get("cross_feed"):
        print("CROSS_FEED")
        print(json.dumps(result["cross_feed"], indent=2))
        print()
    print("outdir =", outdir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
