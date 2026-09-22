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


def _diagnostic_talib_rsi_from_finite_observations(
    close: pd.Series,
    *,
    period: int = 14,
) -> pd.Series:
    """Diagnostic-only RSI recovery that does not alter stored feature outputs."""
    try:
        import talib
    except ImportError:
        return pd.Series(np.nan, index=close.index, dtype=float)

    values = pd.to_numeric(close, errors="coerce").to_numpy(dtype=float)
    mask = np.isfinite(values)
    out = np.full(len(values), np.nan, dtype=float)
    if int(mask.sum()) <= period:
        return pd.Series(out, index=close.index, dtype=float)

    out[mask] = talib.RSI(values[mask], timeperiod=period)
    return pd.Series(out, index=close.index, dtype=float)


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
    feature_talib_valid_rows = int(aligned["talib"].notna().sum())
    diagnostic_repair_applied = False

    if feature_talib_valid_rows == 0 and int(aligned["close"].notna().sum()) > 14:
        aligned["talib_diagnostic"] = _diagnostic_talib_rsi_from_finite_observations(
            aligned["close"],
            period=14,
        )
        diagnostic_repair_applied = bool(
            aligned["talib_diagnostic"].notna().any()
        )
    else:
        aligned["talib_diagnostic"] = aligned["talib"]

    pair = aligned.dropna(subset=["legacy", "talib_diagnostic"]).copy()
    pair["talib_feature"] = pair["talib"]
    pair["talib"] = pair["talib_diagnostic"]
    pair = pair.drop(columns=["talib_diagnostic"])

    diagnostics = {
        "raw_rows": int(len(frame)),
        "raw_timestamp_rows": int(len(raw)),
        "close_valid_rows": int(raw["close"].notna().sum()),
        "legacy_valid_rows": int(raw["legacy"].notna().sum()),
        "feature_talib_valid_rows": feature_talib_valid_rows,
        "talib_valid_rows": int(pair["talib"].notna().sum()),
        "timestamp_overlap_rows": int(len(aligned)),
        "overlap_rows": int(len(pair)),
        "diagnostic_repair_applied": diagnostic_repair_applied,
        "feature_output_unchanged": True,
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
        "status": (
            "FEATURE_GAP_DIAGNOSED"
            if diagnostic_repair_applied
            else "READY"
        ),
        **diagnostics,
        "mean_absolute_difference": float(diff.abs().mean()),
        "max_absolute_difference": float(diff.abs().max()),
        "mean_signed_difference": float(diff.mean()),
        "correlation": None if corr is None or not np.isfinite(corr) else float(corr),
        "threshold_zone_disagreement_ratio": float((legacy_zone != talib_zone).mean()),
        "first_overlap_timestamp": pair["timestamp"].min().isoformat(),
        "last_overlap_timestamp": pair["timestamp"].max().isoformat(),
    }
