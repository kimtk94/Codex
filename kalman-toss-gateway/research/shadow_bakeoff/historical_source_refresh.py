from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import stat
from dataclasses import dataclass
from datetime import time as dtime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from research.model_v2.build_historical_feature_matrix import (
    HISTORICAL_NUMERIC_FEATURES,
)


@dataclass(frozen=True)
class MappingSpec:
    indicator_id: str
    source_candidates: tuple[str, ...]
    timezone: str
    same_day_complete_after: str | None
    required_anchor: bool = False


@dataclass(frozen=True)
class FormulaChoice:
    feature: str
    formula: str
    score: float
    overlap: int


def _utc(values: Any) -> pd.Series:
    return pd.to_datetime(values, utc=True, errors="coerce")


def _timestamp(value: Any) -> pd.Timestamp:
    x = pd.Timestamp(value)
    if x.tzinfo is None:
        return x.tz_localize("UTC")
    return x.tz_convert("UTC")


def _parse_clock(value: str) -> dtime:
    hh, mm = str(value).strip().split(":", 1)
    return dtime(hour=int(hh), minute=int(mm))


def _event_complete(
    event_time: pd.Timestamp,
    *,
    now: pd.Timestamp,
    timezone: str,
    same_day_complete_after: str | None,
) -> bool:
    event = _timestamp(event_time)
    current = _timestamp(now).tz_convert(ZoneInfo(timezone))
    event_date = event.date()
    local_date = current.date()
    if event_date < local_date:
        return True
    if event_date > local_date:
        return False
    if same_day_complete_after is None:
        return False
    return current.time().replace(tzinfo=None) >= _parse_clock(same_day_complete_after)


def _wilder_average(values: pd.Series, period: int) -> pd.Series:
    x = pd.to_numeric(values, errors="coerce").astype(float)
    out = pd.Series(np.nan, index=x.index, dtype=float)
    if len(x) <= period:
        return out
    seed = x.iloc[1 : period + 1].mean()
    if not np.isfinite(seed):
        return out
    out.iloc[period] = seed
    prev = float(seed)
    for i in range(period + 1, len(x)):
        value = x.iloc[i]
        if not np.isfinite(value):
            out.iloc[i] = np.nan
            continue
        prev = ((period - 1) * prev + float(value)) / period
        out.iloc[i] = prev
    return out


def _rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = _wilder_average(gain, period)
    avg_loss = _wilder_average(loss, period)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    out = out.where(~((avg_loss == 0.0) & (avg_gain > 0.0)), 100.0)
    return out


def _rsi_ewm(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()
    avg_loss = loss.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - (100.0 / (1.0 + rs))
    out = out.where(~((avg_loss == 0.0) & (avg_gain > 0.0)), 100.0)
    return out


def _true_range(frame: pd.DataFrame) -> pd.Series:
    high = pd.to_numeric(frame["high"], errors="coerce")
    low = pd.to_numeric(frame["low"], errors="coerce")
    close = pd.to_numeric(frame["close"], errors="coerce")
    prev = close.shift(1)
    return pd.concat(
        [
            high - low,
            (high - prev).abs(),
            (low - prev).abs(),
        ],
        axis=1,
    ).max(axis=1)


def _candidate_formulas(frame: pd.DataFrame, feature: str) -> dict[str, pd.Series]:
    close = pd.to_numeric(frame["close"], errors="coerce").astype(float)
    ret1 = close.pct_change(1, fill_method=None)
    logret1 = np.log(close / close.shift(1))
    out: dict[str, pd.Series] = {}

    def pct(period: int) -> pd.Series:
        return close.pct_change(period, fill_method=None)

    def diff(period: int) -> pd.Series:
        return close.diff(period)

    if feature in {"CHG_1", "CHG_5", "CHG_20"}:
        period = int(feature.split("_")[1])
        out = {
            f"pct_{period}": pct(period),
            f"pct_{period}_x100": pct(period) * 100.0,
            f"diff_{period}": diff(period),
        }
    elif feature in {"CHG_1_BP", "CHG_5_BP"}:
        period = int(feature.split("_")[1])
        out = {
            f"diff_{period}_x100": diff(period) * 100.0,
            f"pct_{period}_x10000": pct(period) * 10000.0,
            f"diff_{period}": diff(period),
        }
    elif feature.startswith("Z") and feature[1:].isdigit():
        period = int(feature[1:])
        mean = close.rolling(period, min_periods=period).mean()
        out = {
            f"z{period}_ddof1": (close - mean)
            / close.rolling(period, min_periods=period).std(ddof=1),
            f"z{period}_ddof0": (close - mean)
            / close.rolling(period, min_periods=period).std(ddof=0),
        }
    elif feature == "CHANGE_VOL20":
        out = {
            "change_vol20_ret_ann": ret1.rolling(20, min_periods=20).std(ddof=1)
            * math.sqrt(252.0),
            "change_vol20_ret": ret1.rolling(20, min_periods=20).std(ddof=1),
            "change_vol20_diff": close.diff().rolling(20, min_periods=20).std(ddof=1),
            "change_vol20_diff_ddof0": close.diff()
            .rolling(20, min_periods=20)
            .std(ddof=0),
            "change_vol20_pct100": (ret1 * 100.0)
            .rolling(20, min_periods=20)
            .std(ddof=1),
        }
    elif feature == "RET_4H":
        out = {}
    elif feature in {"RET_1D", "RET_5D", "RET_20D", "RET_60D"}:
        period = int(feature.split("_")[1][:-1])
        out = {
            f"ret_{period}": pct(period),
            f"logret_{period}": np.log(close / close.shift(period)),
            f"ret_{period}_x100": pct(period) * 100.0,
        }
    elif feature in {"MA20_DIST", "MA50_DIST", "MA60_DIST"}:
        period = int(feature[2 : feature.index("_")])
        ma = close.rolling(period, min_periods=period).mean()
        out = {
            f"ma{period}_ratio": close / ma - 1.0,
            f"ma{period}_ratio_x100": (close / ma - 1.0) * 100.0,
            f"ma{period}_diff": close - ma,
        }
    elif feature == "RSI14":
        out = {
            "rsi14_wilder": _rsi_wilder(close, 14),
            "rsi14_ewm": _rsi_ewm(close, 14),
        }
    elif feature == "RV20":
        out = {
            "rv20_ret_ann_ddof1": ret1.rolling(20, min_periods=20).std(ddof=1)
            * math.sqrt(252.0),
            "rv20_ret_ann_ddof0": ret1.rolling(20, min_periods=20).std(ddof=0)
            * math.sqrt(252.0),
            "rv20_log_ann_ddof1": logret1.rolling(20, min_periods=20).std(ddof=1)
            * math.sqrt(252.0),
            "rv20_log_ann_ddof0": logret1.rolling(20, min_periods=20).std(ddof=0)
            * math.sqrt(252.0),
            "rv20_ret_ddof1": ret1.rolling(20, min_periods=20).std(ddof=1),
        }
    elif feature == "ATR14_PCT":
        tr = _true_range(frame)
        atr_wilder = _wilder_average(tr, 14)
        atr_ewm = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
        atr_roll = tr.rolling(14, min_periods=14).mean()
        out = {
            "atr14_wilder_pct": atr_wilder / close,
            "atr14_ewm_pct": atr_ewm / close,
            "atr14_roll_pct": atr_roll / close,
            "atr14_wilder_pct_x100": atr_wilder / close * 100.0,
        }
    return out


def _normalized_mae(target: pd.Series, pred: pd.Series) -> tuple[float, int]:
    pair = pd.DataFrame(
        {
            "target": pd.to_numeric(target, errors="coerce"),
            "pred": pd.to_numeric(pred, errors="coerce"),
        }
    ).replace([np.inf, -np.inf], np.nan).dropna()
    if pair.empty:
        return math.inf, 0
    scale = float(np.nanmedian(np.abs(pair["target"].to_numpy(dtype=float))))
    scale = max(scale, 1e-8)
    mae = float(np.nanmedian(np.abs(pair["target"] - pair["pred"])))
    return mae / scale, int(len(pair))


def infer_formula_choices(
    raw_indicator: pd.DataFrame,
    feature_indicator: pd.DataFrame,
    *,
    min_points: int,
    max_error: float,
) -> dict[str, FormulaChoice]:
    raw_x = raw_indicator.copy()
    raw_x["event_time"] = _utc(raw_x["event_time"])
    raw_x = (
        raw_x.dropna(subset=["event_time"])
        .sort_values("event_time")
        .drop_duplicates("event_time", keep="last")
        .reset_index(drop=True)
    )

    feat_x = feature_indicator.copy()
    feat_x["event_time"] = _utc(feat_x["event_time"])
    feat_x = (
        feat_x.dropna(subset=["event_time"])
        .sort_values("event_time")
        .drop_duplicates("event_time", keep="last")
        .set_index("event_time")
    )
    raw_indexed = raw_x.set_index("event_time", drop=False)

    choices: dict[str, FormulaChoice] = {}
    for feature in HISTORICAL_NUMERIC_FEATURES:
        if feature not in feat_x.columns:
            continue
        target = pd.to_numeric(feat_x[feature], errors="coerce")
        if int(target.notna().sum()) < min_points:
            continue

        candidates = _candidate_formulas(raw_x, feature)
        scored: list[tuple[float, int, str]] = []
        for name, series in candidates.items():
            pred = pd.Series(
                pd.to_numeric(series, errors="coerce").to_numpy(),
                index=raw_x["event_time"],
            )
            common = target.index.intersection(pred.index)
            if len(common) < min_points:
                continue
            score, overlap = _normalized_mae(
                target.loc[common].tail(252),
                pred.loc[common].tail(252),
            )
            if overlap >= min_points:
                scored.append((score, overlap, name))

        if not scored:
            raise RuntimeError(
                f"no formula candidates with enough overlap for {feature}"
            )
        score, overlap, name = min(scored, key=lambda item: item[0])
        if not np.isfinite(score) or score > max_error:
            raise RuntimeError(
                f"feature parity failed for {feature}: "
                f"best={name} normalized_mae={score:.6f} "
                f"> {max_error:.6f}"
            )
        choices[feature] = FormulaChoice(
            feature=feature,
            formula=name,
            score=float(score),
            overlap=int(overlap),
        )

    if not choices:
        raise RuntimeError("no historical numeric feature formulas inferred")
    return choices


def _formula_by_name(
    raw_indicator: pd.DataFrame,
    feature: str,
    formula: str,
) -> pd.Series:
    candidates = _candidate_formulas(raw_indicator, feature)
    if formula not in candidates:
        raise KeyError(f"{feature}:{formula}")
    return pd.to_numeric(candidates[formula], errors="coerce")


def _mode_delay_seconds(
    frame: pd.DataFrame,
    *,
    event_col: str = "event_time",
    available_col: str = "available_time",
) -> float:
    event = _utc(frame[event_col])
    available = _utc(frame[available_col])
    seconds = (available - event).dt.total_seconds()
    seconds = seconds[np.isfinite(seconds) & (seconds >= 0)]
    if seconds.empty:
        return 0.0
    rounded = seconds.round().astype("int64")
    mode = rounded.mode()
    return float(mode.iloc[0] if not mode.empty else rounded.median())


def _resolve_current_source(
    market_root: Path,
    mapping: MappingSpec,
) -> Path | None:
    for rel in mapping.source_candidates:
        path = market_root / rel
        if path.is_file():
            return path
    return None


def _normalize_current(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"current snapshot missing columns: {sorted(missing)}")
    x = frame.copy()
    x["event_time"] = _utc(x["timestamp"])
    for col in ("open", "high", "low", "close", "volume"):
        if col in x.columns:
            x[col] = pd.to_numeric(x[col], errors="coerce")
    return (
        x.dropna(subset=["event_time", "close"])
        .sort_values("event_time")
        .drop_duplicates("event_time", keep="last")
        .reset_index(drop=True)
    )


def _validate_price_overlap(
    historical: pd.DataFrame,
    current: pd.DataFrame,
    *,
    min_points: int,
    max_relative_error: float,
) -> dict[str, Any]:
    left = historical[["event_time", "close"]].copy()
    left["event_time"] = _utc(left["event_time"])
    left["close"] = pd.to_numeric(left["close"], errors="coerce")
    right = current[["event_time", "close"]].copy()
    right["close"] = pd.to_numeric(right["close"], errors="coerce")
    pair = left.merge(right, on="event_time", how="inner", suffixes=("_hist", "_cur"))
    pair = pair.dropna().tail(30)
    if len(pair) < min_points:
        raise RuntimeError(
            f"insufficient source-overlap rows: {len(pair)} < {min_points}"
        )
    denom = pair["close_hist"].abs().replace(0.0, np.nan)
    rel = ((pair["close_cur"] - pair["close_hist"]).abs() / denom).dropna()
    if len(rel) < min_points:
        raise RuntimeError("source-overlap close comparison is empty")
    median_rel = float(rel.median())
    max_rel = float(rel.max())
    if median_rel > max_relative_error:
        raise RuntimeError(
            f"source continuity failed: median relative close error "
            f"{median_rel:.6f} > {max_relative_error:.6f}"
        )
    return {
        "overlap_rows": int(len(rel)),
        "median_relative_close_error": median_rel,
        "max_relative_close_error": max_rel,
    }


def _blank_like_row(template: pd.Series, columns: list[str]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    dynamic = {
        "event_time",
        "available_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "raw_value",
        "source_updated_at",
        "is_complete",
        "is_stale",
        "quality_flag",
        "RAW_VALUE",
        *HISTORICAL_NUMERIC_FEATURES,
    }
    for col in columns:
        if col in dynamic:
            row[col] = np.nan
        else:
            row[col] = template.get(col, np.nan)
    return row


def _append_indicator(
    raw: pd.DataFrame,
    features: pd.DataFrame,
    current: pd.DataFrame,
    mapping: MappingSpec,
    *,
    now: pd.Timestamp,
    parity_min_points: int,
    max_parity_error: float,
    source_overlap_min_points: int,
    max_source_close_relative_error: float,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    hist_raw = raw.loc[
        raw["indicator_id"].astype(str) == mapping.indicator_id
    ].copy()
    hist_feat = features.loc[
        features["indicator_id"].astype(str) == mapping.indicator_id
    ].copy()
    if hist_raw.empty:
        raise RuntimeError(f"historical raw indicator missing: {mapping.indicator_id}")
    if hist_feat.empty:
        raise RuntimeError(
            f"historical feature indicator missing: {mapping.indicator_id}"
        )

    hist_raw["event_time"] = _utc(hist_raw["event_time"])
    hist_feat["event_time"] = _utc(hist_feat["event_time"])
    old_max = pd.Timestamp(hist_raw["event_time"].max())

    continuity = _validate_price_overlap(
        hist_raw,
        current,
        min_points=source_overlap_min_points,
        max_relative_error=max_source_close_relative_error,
    )

    current = current.loc[
        current["event_time"].map(
            lambda x: _event_complete(
                pd.Timestamp(x),
                now=now,
                timezone=mapping.timezone,
                same_day_complete_after=mapping.same_day_complete_after,
            )
        )
    ].copy()
    new_current = current.loc[current["event_time"] > old_max].copy()

    report: dict[str, Any] = {
        "indicator_id": mapping.indicator_id,
        "required_anchor": mapping.required_anchor,
        "old_max_event_time": old_max.isoformat(),
        "source_max_event_time": (
            None
            if current.empty
            else pd.Timestamp(current["event_time"].max()).isoformat()
        ),
        "new_raw_rows": int(len(new_current)),
        "new_feature_rows": 0,
        "source_continuity": continuity,
        "formula_parity": {},
    }
    if new_current.empty:
        report["status"] = "NO_NEW_COMPLETED_ROWS"
        report["new_max_event_time"] = old_max.isoformat()
        return raw, features, report

    raw_delay = _mode_delay_seconds(hist_raw)
    feature_delay = _mode_delay_seconds(hist_feat)

    raw_template = hist_raw.sort_values("event_time").iloc[-1]
    raw_rows: list[dict[str, Any]] = []
    for _, src in new_current.iterrows():
        row = _blank_like_row(raw_template, list(raw.columns))
        event = pd.Timestamp(src["event_time"])
        row["event_time"] = event
        row["available_time"] = event + pd.Timedelta(seconds=raw_delay)
        row["indicator_id"] = mapping.indicator_id
        if "timeframe" in row:
            row["timeframe"] = "1D"
        for col in ("open", "high", "low", "close", "volume"):
            if col in raw.columns and col in src.index:
                row[col] = src[col]
        if "raw_value" in raw.columns:
            row["raw_value"] = src["close"]
        if "source" in raw.columns and "source" in src.index:
            row["source"] = src["source"]
        if "source_updated_at" in raw.columns:
            retrieved = src.get("retrieved_at")
            row["source_updated_at"] = (
                _timestamp(retrieved)
                if retrieved is not None and not pd.isna(retrieved)
                else now
            )
        if "retrieved_at" in raw.columns and "retrieved_at" in src.index:
            row["retrieved_at"] = src["retrieved_at"]
        if "is_complete" in raw.columns:
            row["is_complete"] = True
        if "is_stale" in raw.columns:
            row["is_stale"] = False
        if "quality_flag" in raw.columns:
            row["quality_flag"] = "HIST_REFRESH_V1"
        raw_rows.append(row)

    new_raw_frame = pd.DataFrame(raw_rows, columns=raw.columns)
    raw_out = pd.concat([raw, new_raw_frame], ignore_index=True)

    combined_indicator = raw_out.loc[
        raw_out["indicator_id"].astype(str) == mapping.indicator_id
    ].copy()
    combined_indicator["event_time"] = _utc(combined_indicator["event_time"])
    combined_indicator = (
        combined_indicator.sort_values("event_time")
        .drop_duplicates("event_time", keep="last")
        .reset_index(drop=True)
    )

    choices = infer_formula_choices(
        hist_raw,
        hist_feat,
        min_points=parity_min_points,
        max_error=max_parity_error,
    )
    report["formula_parity"] = {
        key: {
            "formula": value.formula,
            "normalized_mae": value.score,
            "overlap": value.overlap,
        }
        for key, value in choices.items()
    }

    feature_template = hist_feat.sort_values("event_time").iloc[-1]
    feature_rows: list[dict[str, Any]] = []
    feature_values: dict[str, pd.Series] = {
        feature: _formula_by_name(
            combined_indicator,
            feature,
            choice.formula,
        )
        for feature, choice in choices.items()
    }
    by_event = combined_indicator["event_time"].reset_index(drop=True)

    for _, src in new_current.iterrows():
        event = pd.Timestamp(src["event_time"])
        matches = np.flatnonzero((by_event == event).to_numpy())
        if len(matches) != 1:
            raise RuntimeError(
                f"cannot locate unique combined row for {mapping.indicator_id} {event}"
            )
        idx = int(matches[0])
        row = _blank_like_row(feature_template, list(features.columns))
        row["event_time"] = event
        row["available_time"] = event + pd.Timedelta(seconds=feature_delay)
        row["indicator_id"] = mapping.indicator_id
        if "timeframe" in row:
            row["timeframe"] = "1D"
        if "RAW_VALUE" in features.columns:
            row["RAW_VALUE"] = src["close"]
        if "source" in features.columns:
            row["source"] = f"DERIVED:{mapping.indicator_id}:HIST_REFRESH_V1"
        if "quality_flag" in features.columns:
            row["quality_flag"] = "HIST_REFRESH_V1"
        for feature, values in feature_values.items():
            if feature in features.columns:
                row[feature] = values.iloc[idx]
        feature_rows.append(row)

    new_feature_frame = pd.DataFrame(feature_rows, columns=features.columns)
    features_out = pd.concat([features, new_feature_frame], ignore_index=True)

    report["new_feature_rows"] = int(len(new_feature_frame))
    report["status"] = "ADVANCED"
    report["new_max_event_time"] = pd.Timestamp(
        new_current["event_time"].max()
    ).isoformat()
    return raw_out, features_out, report


def _validate_output(
    old_raw: pd.DataFrame,
    old_features: pd.DataFrame,
    raw_out: pd.DataFrame,
    features_out: pd.DataFrame,
) -> None:
    if list(raw_out.columns) != list(old_raw.columns):
        raise RuntimeError("raw schema changed")
    if list(features_out.columns) != list(old_features.columns):
        raise RuntimeError("feature schema changed")
    if len(raw_out) < len(old_raw) or len(features_out) < len(old_features):
        raise RuntimeError("refresh unexpectedly removed rows")

    for name, frame, keys in (
        ("raw", raw_out, ["indicator_id", "timeframe", "event_time"]),
        ("features", features_out, ["indicator_id", "timeframe", "event_time"]),
    ):
        probe = frame[keys].copy()
        probe["event_time"] = _utc(probe["event_time"])
        if probe.duplicated(keys).any():
            dup = probe.loc[probe.duplicated(keys, keep=False), keys].head(5)
            raise RuntimeError(
                f"{name} duplicate keys after refresh: {dup.to_dict('records')}"
            )


def refresh_frames(
    raw: pd.DataFrame,
    features: pd.DataFrame,
    *,
    source_frames: dict[str, pd.DataFrame],
    mappings: list[MappingSpec],
    now: pd.Timestamp,
    parity_min_points: int = 30,
    max_parity_error: float = 0.03,
    source_overlap_min_points: int = 5,
    max_source_close_relative_error: float = 0.01,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    raw_out = raw.copy()
    features_out = features.copy()
    reports: list[dict[str, Any]] = []

    for mapping in mappings:
        source = source_frames.get(mapping.indicator_id)
        if source is None:
            reports.append(
                {
                    "indicator_id": mapping.indicator_id,
                    "required_anchor": mapping.required_anchor,
                    "status": "SOURCE_MISSING",
                }
            )
            if mapping.required_anchor:
                continue
            continue

        try:
            current = _normalize_current(source)
            raw_out, features_out, report = _append_indicator(
                raw_out,
                features_out,
                current,
                mapping,
                now=now,
                parity_min_points=parity_min_points,
                max_parity_error=max_parity_error,
                source_overlap_min_points=source_overlap_min_points,
                max_source_close_relative_error=max_source_close_relative_error,
            )
            reports.append(report)
        except Exception as exc:
            reports.append(
                {
                    "indicator_id": mapping.indicator_id,
                    "required_anchor": mapping.required_anchor,
                    "status": "FAIL",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    required_failures = [
        item
        for item in reports
        if item.get("required_anchor")
        and item.get("status") in {"FAIL", "SOURCE_MISSING"}
    ]
    if required_failures:
        raise RuntimeError(
            "required anchor refresh failed: "
            + json.dumps(required_failures, ensure_ascii=False, default=str)
        )

    _validate_output(raw, features, raw_out, features_out)
    return raw_out, features_out, {
        "status": "READY",
        "indicators": reports,
        "new_raw_rows": int(len(raw_out) - len(raw)),
        "new_feature_rows": int(len(features_out) - len(features)),
    }


def _load_mapping(path: Path) -> list[MappingSpec]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("indicators")
    if not isinstance(items, list) or not items:
        raise ValueError("mapping config requires non-empty indicators list")
    out: list[MappingSpec] = []
    for item in items:
        candidates = item.get("source_candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ValueError(
                f"source_candidates missing for {item.get('indicator_id')}"
            )
        out.append(
            MappingSpec(
                indicator_id=str(item["indicator_id"]),
                source_candidates=tuple(str(x) for x in candidates),
                timezone=str(item["timezone"]),
                same_day_complete_after=(
                    None
                    if item.get("same_day_complete_after") in {None, ""}
                    else str(item["same_day_complete_after"])
                ),
                required_anchor=bool(item.get("required_anchor", False)),
            )
        )
    return out


def _atomic_write_pair(
    raw_out: pd.DataFrame,
    features_out: pd.DataFrame,
    *,
    raw_path: Path,
    feature_path: Path,
    backup_dir: Path,
) -> dict[str, str]:
    backup_dir.mkdir(parents=True, exist_ok=False)
    raw_backup = backup_dir / raw_path.name
    feature_backup = backup_dir / feature_path.name
    shutil.copy2(raw_path, raw_backup)
    shutil.copy2(feature_path, feature_backup)

    raw_tmp = raw_path.with_suffix(raw_path.suffix + f".refresh.{os.getpid()}.tmp")
    feat_tmp = feature_path.with_suffix(
        feature_path.suffix + f".refresh.{os.getpid()}.tmp"
    )
    try:
        raw_out.to_parquet(raw_tmp, index=False)
        features_out.to_parquet(feat_tmp, index=False)
        raw_mode = stat.S_IMODE(raw_path.stat().st_mode)
        feat_mode = stat.S_IMODE(feature_path.stat().st_mode)
        os.chmod(raw_tmp, raw_mode)
        os.chmod(feat_tmp, feat_mode)

        # Validate persisted schemas before replacing either canonical file.
        raw_probe = pd.read_parquet(raw_tmp, columns=list(raw_out.columns))
        feat_probe = pd.read_parquet(feat_tmp, columns=list(features_out.columns))
        if len(raw_probe) != len(raw_out) or len(feat_probe) != len(features_out):
            raise RuntimeError("persisted row-count validation failed")

        os.replace(raw_tmp, raw_path)
        try:
            os.replace(feat_tmp, feature_path)
        except Exception:
            shutil.copy2(raw_backup, raw_path)
            raise
    except Exception:
        raw_tmp.unlink(missing_ok=True)
        feat_tmp.unlink(missing_ok=True)
        raise

    return {
        "raw_backup": str(raw_backup),
        "feature_backup": str(feature_backup),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Advance validated historical integrated price sources from current "
            "Market Data V2 snapshots without changing the prospective seed"
        )
    )
    p.add_argument("--raw", required=True)
    p.add_argument("--features", required=True)
    p.add_argument("--market-root", required=True)
    p.add_argument("--mapping", required=True)
    p.add_argument("--output-status")
    p.add_argument("--backup-root")
    p.add_argument("--now")
    p.add_argument("--parity-min-points", type=int, default=30)
    p.add_argument("--max-parity-error", type=float, default=0.03)
    p.add_argument("--source-overlap-min-points", type=int, default=5)
    p.add_argument("--max-source-close-relative-error", type=float, default=0.01)
    p.add_argument("--apply", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    raw_path = Path(args.raw).expanduser()
    feature_path = Path(args.features).expanduser()
    market_root = Path(args.market_root).expanduser()
    mapping_path = Path(args.mapping).expanduser()

    for path in (raw_path, feature_path, mapping_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    if not market_root.is_dir():
        raise FileNotFoundError(market_root)

    mappings = _load_mapping(mapping_path)
    source_frames: dict[str, pd.DataFrame] = {}
    source_paths: dict[str, str | None] = {}
    for mapping in mappings:
        path = _resolve_current_source(market_root, mapping)
        source_paths[mapping.indicator_id] = None if path is None else str(path)
        if path is not None:
            source_frames[mapping.indicator_id] = pd.read_parquet(path)

    raw = pd.read_parquet(raw_path)
    features = pd.read_parquet(feature_path)
    now = (
        pd.Timestamp.now(tz="UTC")
        if not args.now
        else _timestamp(args.now)
    )

    raw_out, features_out, summary = refresh_frames(
        raw,
        features,
        source_frames=source_frames,
        mappings=mappings,
        now=now,
        parity_min_points=max(5, int(args.parity_min_points)),
        max_parity_error=max(0.0, float(args.max_parity_error)),
        source_overlap_min_points=max(2, int(args.source_overlap_min_points)),
        max_source_close_relative_error=max(
            0.0,
            float(args.max_source_close_relative_error),
        ),
    )

    payload: dict[str, Any] = {
        **summary,
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "now": now.isoformat(),
        "raw_path": str(raw_path),
        "feature_path": str(feature_path),
        "market_root": str(market_root),
        "mapping": str(mapping_path),
        "source_paths": source_paths,
        "research_only": True,
        "prospective_seed_unchanged": True,
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
        "production_write": False,
    }

    if args.apply and (
        payload["new_raw_rows"] > 0 or payload["new_feature_rows"] > 0
    ):
        stamp = pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%SZ")
        backup_root = (
            Path(args.backup_root).expanduser()
            if args.backup_root
            else raw_path.parent / "_refresh_backups"
        )
        payload["backups"] = _atomic_write_pair(
            raw_out,
            features_out,
            raw_path=raw_path,
            feature_path=feature_path,
            backup_dir=backup_root / stamp,
        )
        payload["write_status"] = "APPLIED"
    elif args.apply:
        payload["write_status"] = "NO_CHANGES"
    else:
        payload["write_status"] = "DRY_RUN_ONLY"

    if args.output_status:
        status_path = Path(args.output_status).expanduser()
        status_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = status_path.with_suffix(status_path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, status_path)

    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
