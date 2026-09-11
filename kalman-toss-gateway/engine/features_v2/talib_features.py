from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .registry import FEATURE_SET


def _series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").astype(float)


def _legacy_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Exact formula used by engine.sa_us_btc_features.rsi."""
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    avg_up = up.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_down = down.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_up / avg_down.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def build_talib_features(frame: pd.DataFrame) -> pd.DataFrame:
    try:
        import talib
    except ImportError as exc:
        raise RuntimeError("TA-Lib is not installed in the Market Tools V2 environment") from exc

    required = {"timestamp", "symbol", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"canonical input missing columns: {sorted(missing)}")

    x = frame.copy().sort_values("timestamp").reset_index(drop=True)
    close = _series(x, "close")
    high = _series(x, "high")
    low = _series(x, "low")
    volume = _series(x, "volume").fillna(0.0)

    close_arr = close.to_numpy(dtype=float)
    high_arr = high.to_numpy(dtype=float)
    low_arr = low.to_numpy(dtype=float)
    volume_arr = volume.to_numpy(dtype=float)

    out = pd.DataFrame({
        "timestamp": pd.to_datetime(x["timestamp"], errors="coerce"),
        "symbol": x["symbol"].astype(str),
    })

    out["talib_v2_rsi14"] = talib.RSI(close_arr, timeperiod=14)
    macd, macd_signal, macd_hist = talib.MACD(
        close_arr,
        fastperiod=12,
        slowperiod=26,
        signalperiod=9,
    )
    out["talib_v2_macd"] = macd
    out["talib_v2_macd_signal"] = macd_signal
    out["talib_v2_macd_hist"] = macd_hist

    if high.notna().any() and low.notna().any():
        out["talib_v2_adx14"] = talib.ADX(high_arr, low_arr, close_arr, timeperiod=14)
        out["talib_v2_atr14"] = talib.ATR(high_arr, low_arr, close_arr, timeperiod=14)
        out["talib_v2_natr14"] = talib.NATR(high_arr, low_arr, close_arr, timeperiod=14)
    else:
        out["talib_v2_adx14"] = np.nan
        out["talib_v2_atr14"] = np.nan
        out["talib_v2_natr14"] = np.nan

    out["talib_v2_roc10"] = talib.ROC(close_arr, timeperiod=10)
    out["talib_v2_obv"] = talib.OBV(close_arr, volume_arr)

    upper, middle, lower = talib.BBANDS(
        close_arr,
        timeperiod=20,
        nbdevup=2,
        nbdevdn=2,
        matype=0,
    )
    out["talib_v2_bb_upper"] = upper
    out["talib_v2_bb_mid"] = middle
    out["talib_v2_bb_lower"] = lower
    width = pd.Series(upper - lower).replace(0, np.nan)
    out["talib_v2_bb_pctb"] = (close.reset_index(drop=True) - lower) / width

    out["feature_set"] = FEATURE_SET
    out["point_in_time"] = True
    return out


def compare_legacy_rsi(frame: pd.DataFrame, features: pd.DataFrame) -> dict[str, Any]:
    close = pd.to_numeric(frame["close"], errors="coerce").astype(float)
    legacy = _legacy_rsi(close, 14).reset_index(drop=True)
    modern = pd.to_numeric(features["talib_v2_rsi14"], errors="coerce").reset_index(drop=True)
    pair = pd.DataFrame({"legacy": legacy, "talib": modern}).dropna()

    if pair.empty:
        return {"status": "INSUFFICIENT_DATA", "overlap_rows": 0}

    diff = pair["legacy"] - pair["talib"]
    legacy_zone = pd.cut(
        pair["legacy"],
        bins=[-np.inf, 30, 70, np.inf],
        labels=["oversold", "neutral", "overbought"],
    )
    talib_zone = pd.cut(
        pair["talib"],
        bins=[-np.inf, 30, 70, np.inf],
        labels=["oversold", "neutral", "overbought"],
    )

    corr = pair["legacy"].corr(pair["talib"])
    return {
        "status": "READY",
        "overlap_rows": int(len(pair)),
        "mean_absolute_difference": float(diff.abs().mean()),
        "max_absolute_difference": float(diff.abs().max()),
        "mean_signed_difference": float(diff.mean()),
        "correlation": None if corr is None or not np.isfinite(corr) else float(corr),
        "threshold_zone_disagreement_ratio": float((legacy_zone != talib_zone).mean()),
        "legacy_first_valid_index": int(legacy.first_valid_index())
        if legacy.first_valid_index() is not None
        else None,
        "talib_first_valid_index": int(modern.first_valid_index())
        if modern.first_valid_index() is not None
        else None,
    }
