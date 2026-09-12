from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ANCHOR_INDICATOR_BY_KEY = {
    "yf_spy": "US_SPY",
    "yf_kospi": "KR_KOSPI",
    "yf_btc": "BTC_BTCUSD",
}

HISTORICAL_FEATURE_COLUMNS = [
    "RAW_VALUE",
    "CHG_1",
    "CHG_5",
    "CHG_20",
    "CHG_1_BP",
    "CHG_5_BP",
    "Z20",
    "Z60",
    "Z252",
    "CHANGE_VOL20",
    "RET_4H",
    "RET_1D",
    "RET_5D",
    "RET_20D",
    "RET_60D",
    "MA20_DIST",
    "MA50_DIST",
    "MA60_DIST",
    "RSI14",
    "RV20",
    "ATR14_PCT",
]

HISTORICAL_FEATURE_SET = "multimarket_historical_v0_3"
HISTORICAL_DATASET_VERSION = "kalman_historical_feature_matrix_v0_3"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build 2017-present Kalman matrices from consolidated historical backfill"
    )
    p.add_argument("--historical-raw", required=True)
    p.add_argument("--historical-features", required=True)
    p.add_argument("--spec", required=True)
    p.add_argument("--output-dir", required=True)
    return p.parse_args()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def atomic_parquet(frame: pd.DataFrame, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(tmp, index=False)
    checksum = sha256_file(tmp)
    os.replace(tmp, path)
    return checksum


def normalize_market(value: Any) -> str:
    text = str(value or "").strip().upper()
    return "COMMON" if text == "COMMON" else text


def normalized_day(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, errors="coerce").dt.normalize()


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)


def _daily_rows(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if "timeframe" in out.columns:
        out = out.loc[out["timeframe"].astype(str).str.upper().eq("1D")].copy()
    out["event_day"] = normalized_day(out["event_time"])
    return out.loc[out["event_day"].notna()].copy()


def anchor_raw_frame(
    historical_raw: pd.DataFrame,
    *,
    indicator_id: str,
) -> pd.DataFrame:
    raw = _daily_rows(historical_raw)
    raw = raw.loc[raw["indicator_id"].astype(str).eq(indicator_id)].copy()
    if raw.empty:
        raise RuntimeError(f"historical raw anchor not found: {indicator_id}")

    required = {"event_day", "open", "close"}
    missing = required.difference(raw.columns)
    if missing:
        raise ValueError(f"{indicator_id}: historical raw missing {sorted(missing)}")

    raw["open"] = numeric(raw["open"])
    raw["close"] = numeric(raw["close"])
    raw = (
        raw.sort_values(["event_day", "available_time"] if "available_time" in raw.columns else ["event_day"])
        .drop_duplicates("event_day", keep="last")
        .dropna(subset=["event_day", "open", "close"])
    )
    if len(raw) < 700:
        raise RuntimeError(
            f"{indicator_id}: historical anchor has only {len(raw)} usable daily rows"
        )

    return pd.DataFrame(
        {
            "timestamp": raw["event_day"].to_numpy(),
            "open": raw["open"].to_numpy(dtype=float),
            "close": raw["close"].to_numpy(dtype=float),
        }
    ).sort_values("timestamp").reset_index(drop=True)


def historical_feature_blocks(
    historical_features: pd.DataFrame,
    *,
    anchor_index: pd.DatetimeIndex,
    include_groups: set[str],
    group_lags: dict[str, int],
    max_ffill: int,
) -> tuple[pd.DataFrame, dict[str, str]]:
    features = _daily_rows(historical_features)
    features["market_group"] = features["market"].map(normalize_market)
    features = features.loc[features["market_group"].isin(include_groups)].copy()
    if features.empty:
        raise RuntimeError("no historical features match requested market groups")

    available_metrics = [
        col
        for col in HISTORICAL_FEATURE_COLUMNS
        if col in features.columns and features[col].notna().any()
    ]
    if not available_metrics:
        raise RuntimeError("historical feature parquet has no supported numeric features")

    parts: list[pd.DataFrame] = []
    groups: dict[str, str] = {}

    for indicator_id, group_frame in features.groupby("indicator_id", sort=True):
        indicator = str(indicator_id)
        market_group = normalize_market(group_frame["market_group"].iloc[-1])
        block = group_frame[["event_day", *available_metrics]].copy()
        for metric in available_metrics:
            block[metric] = numeric(block[metric])

        block = (
            block.sort_values("event_day")
            .drop_duplicates("event_day", keep="last")
            .set_index("event_day")
            .sort_index()
        )
        useful = [
            metric for metric in available_metrics if block[metric].notna().any()
        ]
        if not useful:
            continue

        block = block[useful].rename(
            columns={metric: f"{indicator}__{metric}" for metric in useful}
        )
        block = block.reindex(anchor_index).ffill(limit=max_ffill)

        lag = max(0, int(group_lags.get(market_group, 1)))
        if lag:
            block = block.shift(lag)

        parts.append(block)
        groups[indicator] = market_group

    if not parts:
        raise RuntimeError("no usable historical feature blocks")

    matrix = pd.concat(parts, axis=1)
    matrix = matrix.loc[:, ~matrix.columns.duplicated()]
    return matrix, groups


def group_aggregate_features(
    frame: pd.DataFrame,
    *,
    indicator_groups: dict[str, str],
) -> pd.DataFrame:
    out = pd.DataFrame(index=frame.index)
    metrics = [
        "CHG_1",
        "CHG_5",
        "CHG_20",
        "Z20",
        "RET_1D",
        "RET_5D",
        "RET_20D",
        "MA20_DIST",
        "MA50_DIST",
        "RSI14",
        "RV20",
        "ATR14_PCT",
    ]

    for group in sorted(set(indicator_groups.values())):
        indicators = [
            indicator
            for indicator, value in indicator_groups.items()
            if value == group
        ]
        for metric in metrics:
            cols = [
                f"{indicator}__{metric}"
                for indicator in indicators
                if f"{indicator}__{metric}" in frame.columns
            ]
            if not cols:
                continue
            values = frame[cols]
            prefix = f"group_{group.lower()}__{metric}"
            out[f"{prefix}__median"] = values.median(axis=1, skipna=True)
            out[f"{prefix}__coverage"] = values.notna().sum(axis=1) / len(cols)
            if metric not in {"RV20", "ATR14_PCT"}:
                out[f"{prefix}__positive_ratio"] = (
                    (values > 0).where(values.notna()).mean(axis=1)
                )
    return out


def build_market_matrix(
    *,
    market_name: str,
    market_spec: dict[str, Any],
    historical_raw: pd.DataFrame,
    historical_features: pd.DataFrame,
    output_dir: Path,
    max_ffill: int,
    raw_source_path: Path,
    feature_source_path: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    anchor_key = str(market_spec["anchor_key"])
    if anchor_key not in ANCHOR_INDICATOR_BY_KEY:
        raise ValueError(f"unsupported historical anchor key: {anchor_key}")
    anchor_indicator = ANCHOR_INDICATOR_BY_KEY[anchor_key]

    anchor_raw = anchor_raw_frame(
        historical_raw,
        indicator_id=anchor_indicator,
    )
    anchor_index = pd.DatetimeIndex(
        pd.to_datetime(anchor_raw["timestamp"], utc=True, errors="raise")
    )
    anchor_close = pd.Series(
        pd.to_numeric(anchor_raw["close"], errors="coerce").to_numpy(),
        index=anchor_index,
        dtype=float,
    )

    include_groups = {
        normalize_market(value)
        for value in market_spec["include_groups"]
    }
    group_lags = {
        normalize_market(key): int(value)
        for key, value in market_spec.get("group_lag_observations", {}).items()
    }

    features, indicator_groups = historical_feature_blocks(
        historical_features,
        anchor_index=anchor_index,
        include_groups=include_groups,
        group_lags=group_lags,
        max_ffill=max_ffill,
    )
    aggregates = group_aggregate_features(
        features,
        indicator_groups=indicator_groups,
    )
    features = pd.concat([features, aggregates], axis=1)

    horizon = int(market_spec["horizon_observations"])
    threshold = float(market_spec.get("positive_return_threshold", 0.0))
    target_return = anchor_close.shift(-horizon) / anchor_close - 1.0
    target_label = (target_return > threshold).astype(float)
    target_label = target_label.where(target_return.notna())

    matrix = features.copy()
    matrix.insert(0, "anchor_close", anchor_close)
    matrix.insert(0, "as_of", matrix.index)
    matrix["target_forward_return"] = target_return
    matrix["target_label"] = target_label
    matrix = matrix.reset_index(drop=True)

    market_lower = market_name.lower()
    anchor_path = output_dir / f"{market_lower}_anchor_raw.parquet"
    anchor_sha = atomic_parquet(anchor_raw, anchor_path)

    raw_sha = sha256_file(raw_source_path)
    feature_sha = sha256_file(feature_source_path)
    manifest = {
        "market": market_name,
        "symbol": market_spec["symbol"],
        "anchor_key": anchor_key,
        "historical_anchor_indicator": anchor_indicator,
        "horizon_observations": horizon,
        "positive_return_threshold": threshold,
        "include_groups": sorted(include_groups),
        "group_lag_observations": group_lags,
        "max_ffill_observations": max_ffill,
        "rows": int(len(matrix)),
        "feature_columns": [
            col
            for col in matrix.columns
            if col not in {
                "as_of",
                "anchor_close",
                "target_forward_return",
                "target_label",
            }
        ],
        "feature_count": int(len(matrix.columns) - 4),
        "feature_groups": indicator_groups,
        "feature_schema": HISTORICAL_FEATURE_SET,
        "research_only": True,
        "input_files": {
            str(anchor_path): {
                "sha256": anchor_sha,
                "kind": "raw",
                "fetch_key": anchor_key,
                "group": market_name,
                "generated_from": str(raw_source_path),
            },
            str(raw_source_path): {
                "sha256": raw_sha,
                "kind": "historical_raw",
                "fetch_key": "*",
                "group": "MULTIMARKET",
            },
            str(feature_source_path): {
                "sha256": feature_sha,
                "kind": "historical_features",
                "fetch_key": "*",
                "group": "MULTIMARKET",
            },
        },
    }
    return matrix, manifest


def historical_spec(base_spec: dict[str, Any]) -> dict[str, Any]:
    spec = json.loads(json.dumps(base_spec))
    spec["version"] = f"{base_spec['version']}_hist_v0_3"
    spec["feature_set"] = HISTORICAL_FEATURE_SET
    spec["dataset_version"] = HISTORICAL_DATASET_VERSION
    spec["historical_reconstruction"] = {
        "source": "Market_Data/Market_Features historical_2017 consolidated parquet",
        "exact_current_v2_feature_parity": False,
        "reason": (
            "historical consolidated schema differs from current TA-Lib snapshot; "
            "model training/threshold semantics remain Model V2"
        ),
    }
    return spec


def build_all(
    *,
    historical_raw_path: Path,
    historical_feature_path: Path,
    spec_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    historical_raw_path = historical_raw_path.expanduser()
    historical_feature_path = historical_feature_path.expanduser()
    spec_path = spec_path.expanduser()
    output_dir = output_dir.expanduser()

    for path in (historical_raw_path, historical_feature_path, spec_path):
        if not path.exists():
            raise FileNotFoundError(path)

    raw = pd.read_parquet(historical_raw_path)
    features = pd.read_parquet(historical_feature_path)
    required_raw = {"event_time", "indicator_id", "timeframe", "open", "close"}
    required_features = {"event_time", "market", "indicator_id", "timeframe"}
    if required_raw.difference(raw.columns):
        raise ValueError(
            f"historical raw missing columns: {sorted(required_raw.difference(raw.columns))}"
        )
    if required_features.difference(features.columns):
        raise ValueError(
            "historical features missing columns: "
            f"{sorted(required_features.difference(features.columns))}"
        )

    base_spec = json.loads(spec_path.read_text(encoding="utf-8"))
    derived_spec = historical_spec(base_spec)
    output_dir.mkdir(parents=True, exist_ok=True)
    derived_spec_path = output_dir / "historical_model_v2_spec.json"
    atomic_json(derived_spec_path, derived_spec)

    status: dict[str, Any] = {
        "status": "READY",
        "dataset_version": HISTORICAL_DATASET_VERSION,
        "feature_set": HISTORICAL_FEATURE_SET,
        "model_version": derived_spec["version"],
        "research_only": True,
        "historical_raw": str(historical_raw_path),
        "historical_features": str(historical_feature_path),
        "derived_spec": str(derived_spec_path),
        "markets": {},
    }

    for market_name, market_spec in derived_spec["markets"].items():
        try:
            matrix, manifest = build_market_matrix(
                market_name=market_name,
                market_spec=market_spec,
                historical_raw=raw,
                historical_features=features,
                output_dir=output_dir,
                max_ffill=int(derived_spec.get("max_ffill_observations", 3)),
                raw_source_path=historical_raw_path,
                feature_source_path=historical_feature_path,
            )
            matrix_path = output_dir / f"{market_name.lower()}_matrix.parquet"
            matrix_sha = atomic_parquet(matrix, matrix_path)

            lineage_payload = {
                "dataset_version": HISTORICAL_DATASET_VERSION,
                "market": market_name,
                "spec_sha256": sha256_file(derived_spec_path),
                "matrix_sha256": matrix_sha,
                "historical_raw_sha256": sha256_file(historical_raw_path),
                "historical_features_sha256": sha256_file(historical_feature_path),
            }
            lineage_hash = hashlib.sha256(
                json.dumps(lineage_payload, sort_keys=True).encode("utf-8")
            ).hexdigest()
            manifest.update(
                {
                    "dataset_version": HISTORICAL_DATASET_VERSION,
                    "model_version": derived_spec["version"],
                    "matrix_path": str(matrix_path),
                    "matrix_sha256": matrix_sha,
                    "lineage_sha256": lineage_hash,
                    "built_at": pd.Timestamp.now(tz="UTC").isoformat(),
                }
            )
            atomic_json(
                output_dir / f"{market_name.lower()}_matrix_manifest.json",
                manifest,
            )
            status["markets"][market_name] = {
                "status": "READY",
                "rows": int(len(matrix)),
                "labeled_rows": int(matrix["target_label"].notna().sum()),
                "min_as_of": pd.to_datetime(matrix["as_of"], utc=True).min().isoformat(),
                "max_as_of": pd.to_datetime(matrix["as_of"], utc=True).max().isoformat(),
                "feature_count": manifest["feature_count"],
                "lineage_sha256": lineage_hash,
            }
        except Exception as exc:
            status["status"] = "FAIL"
            status["markets"][market_name] = {
                "status": "FAIL",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    atomic_json(output_dir / "historical_matrix_run_status.json", status)
    return status


def main() -> int:
    args = parse_args()
    status = build_all(
        historical_raw_path=Path(args.historical_raw),
        historical_feature_path=Path(args.historical_features),
        spec_path=Path(args.spec),
        output_dir=Path(args.output_dir),
    )
    print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    return 0 if status["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
