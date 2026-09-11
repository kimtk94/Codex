from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd


OHLCV_COLUMNS = [
    "timestamp",
    "market",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "currency",
    "source",
    "source_asof",
    "retrieved_at",
    "is_adjusted",
]

MACRO_COLUMNS = [
    "timestamp",
    "series_id",
    "value",
    "source",
    "source_asof",
    "retrieved_at",
    "frequency",
    "unit",
]

_NUMERIC_OHLCV = ["open", "high", "low", "close", "adj_close", "volume"]


def naive_datetime_index(values: object) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(pd.to_datetime(values, errors="coerce"))
    if idx.tz is not None:
        idx = idx.tz_convert(None)
    return idx


def canonicalize_ohlcv(
    frame: pd.DataFrame,
    *,
    symbol: str,
    market: str,
    currency: str,
    source: str,
    column_map: Mapping[str, str] | None = None,
    adjusted: bool = False,
    retrieved_at: str | None = None,
) -> pd.DataFrame:
    """Normalize provider OHLCV output to the Kalman V2 canonical schema."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    raw = frame.copy()
    if column_map:
        raw = raw.rename(columns=dict(column_map))

    raw.index = naive_datetime_index(raw.index)
    raw = raw.loc[~raw.index.isna()].sort_index()
    raw = raw.loc[~raw.index.duplicated(keep="last")]

    out = pd.DataFrame(index=raw.index)
    for col in _NUMERIC_OHLCV:
        if col in raw.columns:
            out[col] = pd.to_numeric(raw[col], errors="coerce")
        else:
            out[col] = np.nan

    out.insert(0, "symbol", symbol)
    out.insert(0, "market", market)
    out.insert(0, "timestamp", out.index)
    out["currency"] = currency
    out["source"] = source
    out["source_asof"] = out["timestamp"]
    out["retrieved_at"] = retrieved_at or pd.Timestamp.now(tz="UTC").isoformat()
    out["is_adjusted"] = bool(adjusted)

    out = out.reset_index(drop=True)
    return out[OHLCV_COLUMNS]


def validate_canonical_ohlcv(frame: pd.DataFrame) -> list[str]:
    issues: list[str] = []
    missing = [c for c in OHLCV_COLUMNS if c not in frame.columns]
    if missing:
        issues.append(f"missing_columns={missing}")
        return issues

    if frame.empty:
        issues.append("empty_frame")
        return issues

    ts = pd.to_datetime(frame["timestamp"], errors="coerce")
    if ts.isna().any():
        issues.append("invalid_timestamp")
    if ts.duplicated().any():
        issues.append("duplicate_timestamp")

    close = pd.to_numeric(frame["close"], errors="coerce")
    if close.notna().sum() == 0:
        issues.append("close_all_missing")

    return issues
