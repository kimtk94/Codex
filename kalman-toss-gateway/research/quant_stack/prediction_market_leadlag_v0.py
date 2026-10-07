from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


TIMESTAMP_CANDIDATES = (
    "timestamp",
    "datetime",
    "ts",
    "time",
    "observation_date",
    "date",
    "t",
)
PRICE_CANDIDATES = (
    "close",
    "adj_close",
    "adj close",
    "price",
    "last",
    "c",
)
YIELD_CANDIDATES = (
    "yield",
    "value",
    "rate",
    "dgs2",
    "close",
)


def _read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".parquet", ".pq", ".bin"}:
        return pd.read_parquet(path)
    if suffix in {".csv", ".txt"}:
        return pd.read_csv(path)
    raise ValueError(f"unsupported table type: {path}")


def _pick_column(frame: pd.DataFrame, candidates: tuple[str, ...]) -> str:
    by_lower = {str(c).lower(): str(c) for c in frame.columns}
    for candidate in candidates:
        if candidate in by_lower:
            return by_lower[candidate]
    raise ValueError(f"none of {candidates} found in columns={list(frame.columns)}")


def load_asset_history(path: Path, symbol: str) -> pd.DataFrame:
    frame = _read_table(path)
    ts_col = _pick_column(frame, TIMESTAMP_CANDIDATES)
    px_col = _pick_column(frame, PRICE_CANDIDATES)
    out = frame[[ts_col, px_col]].copy()
    out.columns = ["ts", "price"]
    out["ts"] = pd.to_datetime(out["ts"], utc=True, errors="coerce").astype(
        "datetime64[ns, UTC]"
    )
    out["price"] = pd.to_numeric(out["price"], errors="coerce")
    out = out.dropna().sort_values("ts").drop_duplicates("ts")
    out["symbol"] = symbol.upper()
    for bars in (1, 4, 7):
        out[f"fwd_return_{bars}bar"] = out["price"].shift(-bars) / out["price"] - 1.0
    return out.reset_index(drop=True)


def load_us2y(path: Path) -> pd.DataFrame:
    frame = _read_table(path)
    ts_col = _pick_column(frame, TIMESTAMP_CANDIDATES)
    y_col = _pick_column(frame, YIELD_CANDIDATES)
    out = frame[[ts_col, y_col]].copy()
    out.columns = ["ts", "yield_pct"]

    # FRED DGS2 is a daily closing observation. Treating the date as
    # 00:00 UTC would leak the day's close into earlier events. For date-only
    # inputs, make the observation available at 16:00 New York time.
    if str(ts_col).lower() in {"observation_date", "date"}:
        local = pd.to_datetime(out["ts"], errors="coerce").dt.normalize()
        local = local.dt.tz_localize("America/New_York") + pd.Timedelta(hours=16)
        out["ts"] = local.dt.tz_convert("UTC")
    else:
        out["ts"] = pd.to_datetime(out["ts"], utc=True, errors="coerce").astype(
            "datetime64[ns, UTC]"
        )

    out["yield_pct"] = pd.to_numeric(out["yield_pct"], errors="coerce")
    out = out.dropna().sort_values("ts").drop_duplicates("ts")
    out["us2y_change_bps"] = out["yield_pct"].diff() * 100.0
    return out


def build_event_hours(
    prediction: pd.DataFrame,
    *,
    min_abs_delta_1h: float = 0.05,
) -> pd.DataFrame:
    p = prediction.copy()
    if "ts" not in p.columns:
        raise ValueError("prediction table requires ts")
    if "poly_delta_1h" not in p.columns:
        raise ValueError("prediction table requires poly_delta_1h")
    if "question" not in p.columns:
        if "slug" not in p.columns:
            raise ValueError("prediction table requires question or slug")
        p["question"] = p["slug"].astype(str)
    p["ts"] = pd.to_datetime(p["ts"], utc=True, errors="coerce").astype(
        "datetime64[ns, UTC]"
    )
    p["poly_delta_1h"] = pd.to_numeric(p["poly_delta_1h"], errors="coerce")
    p["risk_prior_sign"] = pd.to_numeric(p.get("risk_prior_sign"), errors="coerce")
    p = p.dropna(subset=["ts", "poly_delta_1h", "risk_prior_sign"])
    p = p[p["semantic_channel"].fillna("UNMAPPED") != "UNMAPPED"]
    p = p[p["poly_delta_1h"].abs() >= float(min_abs_delta_1h)]
    if p.empty:
        return pd.DataFrame(
            columns=[
                "event_hour",
                "event_at",
                "event_score",
                "family_count",
                "market_count",
                "mean_abs_delta_1h",
                "dominant_channel",
                "dominant_theme",
            ]
        )

    p["risk_shift"] = p["poly_delta_1h"] * p["risk_prior_sign"]
    p["event_hour"] = p["ts"].dt.floor("1h")

    def mode_or_mixed(series: pd.Series) -> str:
        clean = series.dropna().astype(str)
        if clean.empty:
            return "UNMAPPED"
        counts = clean.value_counts()
        if len(counts) > 1 and counts.iloc[0] == counts.iloc[1]:
            return "MIXED"
        return str(counts.index[0])

    # Contract ladders (for example CPI > 3.0, > 3.1, > 3.2) must not
    # dominate an hour simply because they contain more contracts. Collapse
    # contracts to one question/family score first, then average families.
    family = (
        p.groupby(["event_hour", "question"], as_index=False)
        .agg(
            family_at=("ts", "max"),
            family_score=("risk_shift", "mean"),
            family_abs_delta_1h=("poly_delta_1h", lambda x: float(np.mean(np.abs(x)))),
            family_contract_count=("slug", "nunique"),
            dominant_channel=("semantic_channel", mode_or_mixed),
            dominant_theme=("theme", mode_or_mixed),
        )
    )

    events = (
        family.groupby("event_hour", as_index=False)
        .agg(
            event_at=("family_at", "max"),
            event_score=("family_score", "mean"),
            family_count=("question", "nunique"),
            market_count=("family_contract_count", "sum"),
            mean_abs_delta_1h=("family_abs_delta_1h", "mean"),
            dominant_channel=("dominant_channel", mode_or_mixed),
            dominant_theme=("dominant_theme", mode_or_mixed),
        )
        .sort_values("event_hour")
    )
    return events


def attach_us2y(events: pd.DataFrame, rates: pd.DataFrame | None) -> pd.DataFrame:
    out = events.copy()
    out["us2y_change_bps"] = np.nan
    out["us2y_confirmation"] = pd.Series([pd.NA] * len(out), dtype="boolean")
    if rates is None or rates.empty or out.empty:
        return out

    event_key = "event_at" if "event_at" in out.columns else "event_hour"
    merged = pd.merge_asof(
        out.drop(columns=["us2y_change_bps"], errors="ignore").sort_values(event_key),
        rates[["ts", "us2y_change_bps"]].dropna().sort_values("ts"),
        left_on=event_key,
        right_on="ts",
        direction="backward",
        tolerance=pd.Timedelta(hours=36),
    )
    out = merged.drop(columns=["ts"], errors="ignore")
    confirms: list[bool | None] = []
    for row in out.itertuples(index=False):
        ch = str(row.dominant_channel)
        dy = row.us2y_change_bps
        if pd.isna(dy):
            confirms.append(None)
        elif ch == "FED_EASING":
            confirms.append(float(dy) < 0)
        elif ch == "FED_TIGHTENING":
            confirms.append(float(dy) > 0)
        else:
            confirms.append(None)
    out["us2y_confirmation"] = pd.array(confirms, dtype="boolean")
    return out


def align_asset(events: pd.DataFrame, asset: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame()
    event_key = "event_at" if "event_at" in events.columns else "event_hour"
    merged = pd.merge_asof(
        events.sort_values(event_key),
        asset.sort_values("ts"),
        left_on=event_key,
        right_on="ts",
        direction="forward",
        tolerance=pd.Timedelta(hours=24),
    )
    merged["entry_lag_minutes"] = (
        merged["ts"] - merged[event_key]
    ).dt.total_seconds() / 60.0
    return merged


def summarize_aligned(
    frame: pd.DataFrame,
    symbol: str,
    *,
    max_entry_lag_minutes: float | None = None,
) -> dict[str, Any]:
    if max_entry_lag_minutes is not None and not frame.empty:
        frame = frame[
            frame["entry_lag_minutes"].notna()
            & (frame["entry_lag_minutes"] <= float(max_entry_lag_minutes))
        ].copy()

    result: dict[str, Any] = {
        "symbol": symbol,
        "max_entry_lag_minutes": max_entry_lag_minutes,
        "event_rows": int(len(frame)),
        "aligned_rows": int(frame["price"].notna().sum()) if not frame.empty else 0,
    }
    if frame.empty:
        return result

    for bars in (1, 4, 7):
        col = f"fwd_return_{bars}bar"
        x = frame[["event_score", col]].dropna()
        key = f"{bars}bar"
        result[f"n_{key}"] = int(len(x))
        result[f"corr_event_score_{key}"] = (
            float(x["event_score"].corr(x[col])) if len(x) >= 3 else None
        )
        if len(x):
            score_sign = np.sign(x["event_score"].to_numpy())
            return_sign = np.sign(x[col].to_numpy())
            result[f"directional_hit_rate_{key}"] = float(np.mean(score_sign == return_sign))
            on = x[x["event_score"] > 0][col]
            off = x[x["event_score"] < 0][col]
            result[f"mean_return_risk_on_{key}"] = float(on.mean()) if len(on) else None
            result[f"mean_return_risk_off_{key}"] = float(off.mean()) if len(off) else None
        else:
            result[f"directional_hit_rate_{key}"] = None
            result[f"mean_return_risk_on_{key}"] = None
            result[f"mean_return_risk_off_{key}"] = None

    result["median_entry_lag_minutes"] = (
        float(frame["entry_lag_minutes"].dropna().median())
        if frame["entry_lag_minutes"].notna().any()
        else None
    )
    if "us2y_confirmation" in frame.columns:
        valid = frame["us2y_confirmation"].dropna()
        result["us2y_confirmation_rows"] = int(len(valid))
        result["us2y_confirmation_rate"] = float(valid.mean()) if len(valid) else None
    return result


def parse_asset_arg(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--asset must be SYMBOL=/path/to/file")
    symbol, path = value.split("=", 1)
    if not symbol.strip() or not path.strip():
        raise argparse.ArgumentTypeError("--asset must be SYMBOL=/path/to/file")
    return symbol.strip().upper(), Path(path).expanduser()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Prediction-market -> asset lead/lag audit v0")
    p.add_argument("--prediction", required=True)
    p.add_argument("--asset", action="append", required=True, type=parse_asset_arg)
    p.add_argument("--us2y")
    p.add_argument("--min-abs-delta-1h", type=float, default=0.05)
    p.add_argument(
        "--near-session-max-lag-minutes",
        type=float,
        default=90.0,
        help="Primary near-session audit: first asset bar must be within this many minutes.",
    )
    p.add_argument("--output-dir", required=True)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    prediction = _read_table(Path(args.prediction))
    events = build_event_hours(prediction, min_abs_delta_1h=args.min_abs_delta_1h)
    rates = load_us2y(Path(args.us2y)) if args.us2y else None
    events = attach_us2y(events, rates)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    events.to_parquet(out_dir / "prediction_event_hours.parquet", index=False)

    summaries = []
    for symbol, path in args.asset:
        asset = load_asset_history(path, symbol)
        aligned = align_asset(events, asset)
        aligned["session_bucket"] = np.where(
            aligned["entry_lag_minutes"].notna()
            & (aligned["entry_lag_minutes"] <= args.near_session_max_lag_minutes),
            "NEAR_SESSION",
            "OFF_HOURS_OR_UNALIGNED",
        )
        aligned.to_parquet(out_dir / f"leadlag_{symbol}.parquet", index=False)
        summaries.append(
            {
                "symbol": symbol,
                "all_aligned": summarize_aligned(aligned, symbol),
                "near_session": summarize_aligned(
                    aligned,
                    symbol,
                    max_entry_lag_minutes=args.near_session_max_lag_minutes,
                ),
            }
        )

    payload = {
        "status": "READY",
        "research_only": True,
        "prediction_event_hours": int(len(events)),
        "min_abs_delta_1h": args.min_abs_delta_1h,
        "near_session_max_lag_minutes": args.near_session_max_lag_minutes,
        "asset_results": summaries,
        "us2y_status": "AVAILABLE" if rates is not None else "NOT_PROVIDED",
        "horizon_semantics": {
            "1bar": "next asset bar close / aligned entry bar close - 1",
            "4bar": "four asset bars after aligned entry",
            "7bar": "seven asset bars after aligned entry; approximately one US cash session for 1h bars",
        },
        "production_promotion": False,
        "r51_mutated": False,
    }
    (out_dir / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
