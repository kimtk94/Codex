from __future__ import annotations

import numpy as np
import pandas as pd

from .registry import FEATURE_SET


def _series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").astype(float)


def _scatter(size: int, mask: np.ndarray, values):
    if isinstance(values, tuple):
        return tuple(_scatter(size, mask, x) for x in values)
    out = np.full(size, np.nan, dtype=float)
    out[mask] = np.asarray(values, dtype=float)
    return out


def build_talib_features(frame: pd.DataFrame) -> pd.DataFrame:
    try:
        import talib
    except ImportError as exc:
        raise RuntimeError("TA-Lib is not installed in the Market Tools environment") from exc

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
    size = len(x)

    out = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(x["timestamp"], errors="coerce"),
            "symbol": x["symbol"].astype(str),
        }
    )

    close_mask = np.isfinite(close_arr)
    if int(close_mask.sum()) >= 40:
        cv = close_arr[close_mask]
        vv = volume_arr[close_mask]
        out["talib_v2_rsi14"] = _scatter(size, close_mask, talib.RSI(cv, timeperiod=14))
        macd, macd_signal, macd_hist = _scatter(
            size,
            close_mask,
            talib.MACD(cv, fastperiod=12, slowperiod=26, signalperiod=9),
        )
        out["talib_v2_macd"] = macd
        out["talib_v2_macd_signal"] = macd_signal
        out["talib_v2_macd_hist"] = macd_hist
        out["talib_v2_roc10"] = _scatter(size, close_mask, talib.ROC(cv, timeperiod=10))
        out["talib_v2_obv"] = _scatter(size, close_mask, talib.OBV(cv, vv))
        upper, middle, lower = _scatter(
            size,
            close_mask,
            talib.BBANDS(cv, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0),
        )
    else:
        for col in (
            "talib_v2_rsi14",
            "talib_v2_macd",
            "talib_v2_macd_signal",
            "talib_v2_macd_hist",
            "talib_v2_roc10",
            "talib_v2_obv",
        ):
            out[col] = np.nan
        upper = middle = lower = np.full(size, np.nan, dtype=float)

    ohlc_mask = np.isfinite(high_arr) & np.isfinite(low_arr) & np.isfinite(close_arr)
    if int(ohlc_mask.sum()) >= 40:
        hv, lv, cv = high_arr[ohlc_mask], low_arr[ohlc_mask], close_arr[ohlc_mask]
        out["talib_v2_adx14"] = _scatter(
            size, ohlc_mask, talib.ADX(hv, lv, cv, timeperiod=14)
        )
        out["talib_v2_atr14"] = _scatter(
            size, ohlc_mask, talib.ATR(hv, lv, cv, timeperiod=14)
        )
        out["talib_v2_natr14"] = _scatter(
            size, ohlc_mask, talib.NATR(hv, lv, cv, timeperiod=14)
        )
    else:
        out["talib_v2_adx14"] = np.nan
        out["talib_v2_atr14"] = np.nan
        out["talib_v2_natr14"] = np.nan

    out["talib_v2_bb_upper"] = upper
    out["talib_v2_bb_mid"] = middle
    out["talib_v2_bb_lower"] = lower
    width = pd.Series(upper - lower, index=out.index).replace(0, np.nan)
    out["talib_v2_bb_pctb"] = (
        close.reset_index(drop=True) - pd.Series(lower, index=out.index)
    ) / width

    out["feature_set"] = FEATURE_SET
    out["point_in_time"] = True
    return out
