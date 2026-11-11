from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _resolve_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    root = (os.environ.get("KALMAN_MARKET_DATA_ROOT") or "").strip()
    if root:
        return Path(root).expanduser() / path.name
    return path


def load_hourly_bars_from_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"t", "o", "c"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"hourly market data missing columns: {sorted(missing)}")

    out = frame.copy()
    out["ts"] = pd.to_datetime(out["t"], utc=True, errors="coerce").astype(
        "datetime64[ns, UTC]"
    )
    out["open"] = pd.to_numeric(out["o"], errors="coerce")
    out["close"] = pd.to_numeric(out["c"], errors="coerce")
    out = out.dropna(subset=["ts", "open", "close"])
    out = out[(out["open"] > 0) & (out["close"] > 0)]
    return (
        out.sort_values("ts")
        .drop_duplicates("ts", keep="last")
        .reset_index(drop=True)
    )


def load_hourly_bars(path: Path) -> pd.DataFrame:
    return load_hourly_bars_from_frame(pd.read_parquet(path))


def compute_symbol_reaction(
    bars: pd.DataFrame,
    *,
    event_at: pd.Timestamp,
    surprise_score: float | None,
    horizons_bars: list[int],
    max_entry_lag_minutes: float,
) -> dict[str, Any]:
    if bars.empty:
        return {"status": "NO_BARS"}

    event_ts = pd.Timestamp(event_at)
    if event_ts.tzinfo is None:
        event_ts = event_ts.tz_localize("UTC")
    else:
        event_ts = event_ts.tz_convert("UTC")
    event_ts = event_ts.as_unit("ns")

    ts_values = bars["ts"].array
    idx = int(ts_values.searchsorted(event_ts, side="left"))
    if idx >= len(bars):
        return {"status": "WAITING_FOR_ENTRY_BAR"}

    entry = bars.iloc[idx]
    entry_ts = pd.Timestamp(entry["ts"])
    lag_minutes = (entry_ts - event_ts).total_seconds() / 60.0
    if lag_minutes < 0 or lag_minutes > float(max_entry_lag_minutes):
        return {
            "status": "ENTRY_LAG_EXCEEDED",
            "entry_ts": entry_ts.isoformat(),
            "entry_lag_minutes": float(lag_minutes),
        }

    entry_open = float(entry["open"])
    reactions: dict[str, Any] = {}
    for horizon in sorted({int(x) for x in horizons_bars if int(x) >= 1}):
        end_idx = idx + horizon - 1
        key = f"{horizon}bar"
        if end_idx >= len(bars):
            reactions[key] = {
                "status": "WAITING_HORIZON",
                "return": None,
                "signed_confirmation_return": None,
                "direction_confirmed": None,
            }
            continue

        end = bars.iloc[end_idx]
        raw_return = float(end["close"]) / entry_open - 1.0
        signed = (
            -float(np.sign(float(surprise_score))) * raw_return
            if surprise_score is not None and float(surprise_score) != 0
            else None
        )
        reactions[key] = {
            "status": "READY",
            "end_ts": pd.Timestamp(end["ts"]).isoformat(),
            "return": raw_return,
            "signed_confirmation_return": signed,
            "direction_confirmed": (
                bool(signed > 0) if signed is not None else None
            ),
        }

    return {
        "status": "READY",
        "entry_ts": entry_ts.isoformat(),
        "entry_lag_minutes": float(lag_minutes),
        "entry_open": entry_open,
        "reactions": reactions,
    }


def compute_equity_confirmation(
    config: dict[str, Any],
    *,
    event_at: Any,
    surprise_score: float | None,
) -> dict[str, Any]:
    spec = config.get("equity_confirmation") or {}
    if not spec.get("enabled", False):
        return {
            "status": "DISABLED",
            "shadow_only": True,
            "symbols": {},
        }
    if event_at is None:
        return {
            "status": "NO_EVENT_ANCHOR",
            "shadow_only": True,
            "symbols": {},
        }

    horizons = [int(x) for x in spec.get("horizons_bars", [1, 4, 7])]
    max_lag = float(spec.get("max_entry_lag_minutes", 90))
    results: dict[str, Any] = {}
    required_failures: list[str] = []

    for symbol, raw_symbol_spec in (spec.get("symbols") or {}).items():
        symbol_spec = raw_symbol_spec or {}
        required = bool(symbol_spec.get("required", False))
        path_text = str(symbol_spec.get("path") or "").strip()
        source = str(symbol_spec.get("source") or "")
        if not path_text:
            results[str(symbol)] = {
                "status": "UNCONFIGURED",
                "required": required,
                "source": source,
            }
            if required:
                required_failures.append(str(symbol))
            continue

        path = _resolve_path(path_text)
        if not path.exists():
            results[str(symbol)] = {
                "status": (
                    "MISSING_REQUIRED_DATA" if required else "UNAVAILABLE_OPTIONAL"
                ),
                "required": required,
                "source": source,
                "path": str(path),
            }
            if required:
                required_failures.append(str(symbol))
            continue

        try:
            bars = load_hourly_bars(path)
            result = compute_symbol_reaction(
                bars,
                event_at=pd.Timestamp(event_at),
                surprise_score=surprise_score,
                horizons_bars=horizons,
                max_entry_lag_minutes=max_lag,
            )
            results[str(symbol)] = {
                **result,
                "required": required,
                "source": source,
                "path": str(path),
            }
        except Exception as exc:
            results[str(symbol)] = {
                "status": "ERROR",
                "required": required,
                "source": source,
                "path": str(path),
                "error": f"{type(exc).__name__}: {exc}",
            }
            if required:
                required_failures.append(str(symbol))

    return {
        "status": (
            "DEGRADED_REQUIRED_DATA"
            if required_failures
            else "READY"
        ),
        "shadow_only": True,
        "quality": "REGULAR_SESSION_1H_POST_EVENT_PROXY",
        "event_at": pd.Timestamp(event_at).isoformat(),
        "surprise_score": surprise_score,
        "max_entry_lag_minutes": max_lag,
        "required_failures": required_failures,
        "symbols": results,
        "trade_execution": False,
    }
