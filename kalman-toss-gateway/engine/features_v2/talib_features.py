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


def _scatter_talib(
    size: int,
    mask: np.ndarray,
    values: np.ndarray | tuple[np.ndarray, ...],
) -> np.ndarray | tuple[np.ndarray, ...]:
    """Scatter TA-Lib output computed on finite observations back to source rows."""
    if isinstance(values, tuple):
        return tuple(_scatter_talib(size, mask, value) for value in values)
    out = np.full(size, np.nan, dtype=float)
    out[mask] = np.asarray(values, dtype=float)
    return out


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
    size = len(x)

    out = pd.DataFrame({
        "timestamp": pd.to_datetime(x["timestamp"], errors="coerce"),
        "symbol": x["symbol"].astype(str),
    })

    # TA-Lib propagates NaN values through many indicators.  Market snapshots
    # such as VIX can contain sparse missing sessions, so compute indicators on
    # the finite observation sequence and scatter results back to source rows.
    # This preserves point-in-time ordering without inventing/filling prices.
    close_mask = np.isfinite(close_arr)
    if int(close_mask.sum()) >= 2:
        close_valid = close_arr[close_mask]
        out["talib_v2_rsi14"] = _scatter_talib(
            size,
            close_mask,
            talib.RSI(close_valid, timeperiod=14),
        )
        macd, macd_signal, macd_hist = _scatter_talib(
            size,
            close_mask,
            talib.MACD(
                close_valid,
                fastperiod=12,
                slowperiod=26,
                signalperiod=9,
            ),
        )
        out["talib_v2_macd"] = macd
        out["talib_v2_macd_signal"] = macd_signal
        out["talib_v2_macd_hist"] = macd_hist
        out["talib_v2_roc10"] = _scatter_talib(
            size,
            close_mask,
            talib.ROC(close_valid, timeperiod=10),
        )
        out["talib_v2_obv"] = _scatter_talib(
            size,
            close_mask,
            talib.OBV(close_valid, volume_arr[close_mask]),
        )
        upper, middle, lower = _scatter_talib(
            size,
            close_mask,
            talib.BBANDS(
                close_valid,
                timeperiod=20,
                nbdevup=2,
                nbdevdn=2,
                matype=0,
            ),
        )
    else:
        out["talib_v2_rsi14"] = np.nan
        out["talib_v2_macd"] = np.nan
        out["talib_v2_macd_signal"] = np.nan
        out["talib_v2_macd_hist"] = np.nan
        out["talib_v2_roc10"] = np.nan
        out["talib_v2_obv"] = np.nan
        upper = np.full(size, np.nan, dtype=float)
        middle = np.full(size, np.nan, dtype=float)
        lower = np.full(size, np.nan, dtype=float)

    ohlc_mask = np.isfinite(high_arr) & np.isfinite(low_arr) & np.isfinite(close_arr)
    if int(ohlc_mask.sum()) >= 2:
        high_valid = high_arr[ohlc_mask]
        low_valid = low_arr[ohlc_mask]
        close_ohlc_valid = close_arr[ohlc_mask]
        out["talib_v2_adx14"] = _scatter_talib(
            size,
            ohlc_mask,
            talib.ADX(high_valid, low_valid, close_ohlc_valid, timeperiod=14),
        )
        out["talib_v2_atr14"] = _scatter_talib(
            size,
            ohlc_mask,
            talib.ATR(high_valid, low_valid, close_ohlc_valid, timeperiod=14),
        )
        out["talib_v2_natr14"] = _scatter_talib(
            size,
            ohlc_mask,
            talib.NATR(high_valid, low_valid, close_ohlc_valid, timeperiod=14),
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


def compare_legacy_rsi(frame: pd.DataFrame, features: pd.DataFrame) -> dict[str, Any]:
    """Compare RSI implementations after canonical timestamp alignment.

    The feature builder sorts raw input by timestamp, so comparing against the
    original row order can create false disagreements when a source arrives in
    reverse or otherwise non-canonical order.  Align on timestamps explicitly
    and always emit enough diagnostics to explain an empty overlap.
    """
    raw = frame[["timestamp", "close"]].copy()
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], errors="coerce", utc=True)
    raw["close"] = pd.to_numeric(raw["close"], errors="coerce").astype(float)
    raw = (
        raw.dropna(subset=["timestamp"])
        .sort_values("timestamp")
        .drop_duplicates("timestamp", keep="last")
        .reset_index(drop=True)
    )
    raw["legacy"] = _legacy_rsi(raw["close"], 14)

    modern = features[["timestamp", "talib_v2_rsi14"]].copy()
    modern["timestamp"] = pd.to_datetime(modern["timestamp"], errors="coerce", utc=True)
    modern["talib"] = pd.to_numeric(
        modern["talib_v2_rsi14"], errors="coerce"
    ).astype(float)
    modern = (
        modern.dropna(subset=["timestamp"])
        .sort_values("timestamp")
        .drop_duplicates("timestamp", keep="last")
        [["timestamp", "talib"]]
        .reset_index(drop=True)
    )

    aligned = raw[["timestamp", "close", "legacy"]].merge(
        modern,
        on="timestamp",
        how="inner",
        validate="one_to_one",
    )
    pair = aligned.dropna(subset=["legacy", "talib"]).copy()

    diagnostics = {
        "raw_rows": int(len(frame)),
        "raw_timestamp_rows": int(len(raw)),
        "close_valid_rows": int(raw["close"].notna().sum()),
        "legacy_valid_rows": int(raw["legacy"].notna().sum()),
        "talib_valid_rows": int(modern["talib"].notna().sum()),
        "timestamp_overlap_rows": int(len(aligned)),
        "overlap_rows": int(len(pair)),
    }

    if pair.empty:
        return {
            "status": "INSUFFICIENT_DATA",
            **diagnostics,
            "reason": (
                "no timestamp-aligned rows where both legacy and TA-Lib RSI are finite"
            ),
        }

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
        **diagnostics,
        "mean_absolute_difference": float(diff.abs().mean()),
        "max_absolute_difference": float(diff.abs().max()),
        "mean_signed_difference": float(diff.mean()),
        "correlation": None if corr is None or not np.isfinite(corr) else float(corr),
        "threshold_zone_disagreement_ratio": float((legacy_zone != talib_zone).mean()),
        "first_overlap_timestamp": pair["timestamp"].min().isoformat(),
        "last_overlap_timestamp": pair["timestamp"].max().isoformat(),
    }
