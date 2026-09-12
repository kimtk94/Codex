from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


HISTORICAL_NUMERIC_FEATURES = [
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

RAW_REQUIRED = {
    "event_time",
    "available_time",
    "market",
    "indicator_id",
    "timeframe",
    "open",
    "high",
    "low",
    "close",
}

FEATURE_REQUIRED = {
    "event_time",
    "available_time",
    "market",
    "indicator_id",
    "timeframe",
    "feature_family",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build 2017+ Kalman historical US/KR/BTC feature matrices"
    )
    p.add_argument("--raw-parquet", required=True)
    p.add_argument("--feature-parquet", required=True)
    p.add_argument("--spec", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--start-date", default="2017-01-01")
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


def _utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, errors="coerce")


def _normalize_group(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text == "COMMON":
        return "COMMON"
    return text


def validate_input_schema(raw: pd.DataFrame, features: pd.DataFrame) -> None:
    missing_raw = RAW_REQUIRED.difference(raw.columns)
    missing_features = FEATURE_REQUIRED.difference(features.columns)
    if missing_raw:
        raise ValueError(f"historical raw missing columns: {sorted(missing_raw)}")
    if missing_features:
        raise ValueError(
            f"historical features missing columns: {sorted(missing_features)}"
        )

    numeric_present = [
        column for column in HISTORICAL_NUMERIC_FEATURES if column in features.columns
    ]
    if not numeric_present:
        raise ValueError("historical features contain no supported numeric features")


def build_anchor_prices(
    raw: pd.DataFrame,
    *,
    indicator_id: str,
    start_date: str,
) -> pd.DataFrame:
    x = raw.loc[
        (raw["indicator_id"].astype(str) == str(indicator_id))
        & (raw["timeframe"].astype(str).str.upper() == "1D")
    ].copy()
    if x.empty:
        raise RuntimeError(f"anchor indicator unavailable: {indicator_id}")

    x["timestamp"] = _utc(x["event_time"])
    for column in ("open", "close"):
        x[column] = pd.to_numeric(x[column], errors="coerce")

    start = pd.Timestamp(start_date, tz="UTC")
    x = x.loc[x["timestamp"].notna() & (x["timestamp"] >= start)]
    x = (
        x.dropna(subset=["timestamp", "open", "close"])
        .sort_values(["timestamp", "available_time"])
        .drop_duplicates("timestamp", keep="last")
    )
    if x.empty:
        raise RuntimeError(f"anchor indicator has no rows from {start_date}: {indicator_id}")

    return x[["timestamp", "open", "close"]].reset_index(drop=True)


def _effective_anchor_positions(
    available_times: pd.Series,
    anchor_index: pd.DatetimeIndex,
) -> np.ndarray:
    available = pd.DatetimeIndex(_utc(available_times))
    anchor_ns = anchor_index.asi8
    available_ns = available.asi8
    return np.searchsorted(anchor_ns, available_ns, side="left")


def align_indicator_block(
    indicator_features: pd.DataFrame,
    *,
    anchor_index: pd.DatetimeIndex,
    max_ffill: int,
    lag_observations: int,
) -> pd.DataFrame:
    numeric_columns = [
        c for c in HISTORICAL_NUMERIC_FEATURES if c in indicator_features.columns
    ]
    if not numeric_columns:
        return pd.DataFrame(index=anchor_index)

    x = indicator_features.copy()
    x["available_time"] = _utc(x["available_time"])
    x = x.loc[x["available_time"].notna()].sort_values(
        ["available_time", "event_time"]
    )
    if x.empty:
        return pd.DataFrame(index=anchor_index)

    positions = _effective_anchor_positions(x["available_time"], anchor_index)
    valid = positions < len(anchor_index)
    x = x.loc[valid].copy()
    positions = positions[valid]
    if x.empty:
        return pd.DataFrame(index=anchor_index)

    x["effective_anchor"] = anchor_index[positions]
    values = x[["effective_anchor", *numeric_columns]].copy()
    for column in numeric_columns:
        values[column] = pd.to_numeric(values[column], errors="coerce")

    values = (
        values.sort_values("effective_anchor")
        .groupby("effective_anchor", as_index=True)[numeric_columns]
        .last()
        .reindex(anchor_index)
    )
    values = values.ffill(limit=max(0, int(max_ffill)))
    if lag_observations:
        values = values.shift(max(0, int(lag_observations)))
    return values


def build_feature_panel(
    features: pd.DataFrame,
    *,
    anchor_index: pd.DatetimeIndex,
    include_groups: set[str],
    group_lag_observations: dict[str, int],
    max_ffill: int,
) -> tuple[pd.DataFrame, dict[str, str]]:
    x = features.copy()
    x["market_group"] = x["market"].map(_normalize_group)
    x = x.loc[x["market_group"].isin(include_groups)].copy()

    blocks: list[pd.DataFrame] = []
    feature_groups: dict[str, str] = {}

    for indicator_id, block in x.groupby("indicator_id", sort=True):
        group = _normalize_group(block["market_group"].iloc[0])
        lag = int(group_lag_observations.get(group, 0))
        aligned = align_indicator_block(
            block,
            anchor_index=anchor_index,
            max_ffill=max_ffill,
            lag_observations=lag,
        )
        if aligned.empty:
            continue

        prefix = str(indicator_id).lower()
        renamed = {
            column: f"{prefix}__{column.lower()}"
            for column in aligned.columns
        }
        aligned = aligned.rename(columns=renamed)
        blocks.append(aligned)
        feature_groups[prefix] = group

    if not blocks:
        raise RuntimeError("no historical feature blocks aligned to anchor")
    return pd.concat(blocks, axis=1).sort_index(), feature_groups


def add_group_aggregates(
    features: pd.DataFrame,
    *,
    feature_groups: dict[str, str],
) -> pd.DataFrame:
    out = pd.DataFrame(index=features.index)
    aggregate_metrics = [
        "chg_1",
        "chg_5",
        "chg_20",
        "z20",
        "z60",
        "ret_1d",
        "ret_5d",
        "ret_20d",
        "ma20_dist",
        "ma50_dist",
        "rsi14",
        "rv20",
        "atr14_pct",
    ]

    for group in sorted(set(feature_groups.values())):
        indicator_prefixes = [
            prefix for prefix, value in feature_groups.items() if value == group
        ]
        for metric in aggregate_metrics:
            columns = [
                f"{prefix}__{metric}"
                for prefix in indicator_prefixes
                if f"{prefix}__{metric}" in features.columns
            ]
            if not columns:
                continue

            values = features[columns]
            base = f"group_{group.lower()}__{metric}"
            out[f"{base}__median"] = values.median(axis=1, skipna=True)
            out[f"{base}__coverage"] = values.notna().sum(axis=1) / len(columns)
            out[f"{base}__positive_ratio"] = (
                (values > 0).where(values.notna()).mean(axis=1)
            )

    return out


def build_market_historical_matrix(
    raw: pd.DataFrame,
    features: pd.DataFrame,
    *,
    market_name: str,
    market_spec: dict[str, Any],
    start_date: str,
    max_ffill: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    anchor_indicator = str(market_spec["historical_anchor_indicator_id"])
    anchor_prices = build_anchor_prices(
        raw,
        indicator_id=anchor_indicator,
        start_date=start_date,
    )
    anchor_index = pd.DatetimeIndex(anchor_prices["timestamp"])

    include_groups = {
        _normalize_group(value) for value in market_spec["include_groups"]
    }
    lag_policy = {
        _normalize_group(key): int(value)
        for key, value in market_spec.get("group_lag_observations", {}).items()
    }

    panel, feature_groups = build_feature_panel(
        features,
        anchor_index=anchor_index,
        include_groups=include_groups,
        group_lag_observations=lag_policy,
        max_ffill=max_ffill,
    )
    aggregates = add_group_aggregates(panel, feature_groups=feature_groups)
    panel = pd.concat([panel, aggregates], axis=1)

    close = pd.Series(
        pd.to_numeric(anchor_prices["close"], errors="coerce").to_numpy(),
        index=anchor_index,
        dtype=float,
    )
    horizon = int(market_spec["horizon_observations"])
    threshold = float(market_spec.get("positive_return_threshold", 0.0))
    target_return = close.shift(-horizon) / close - 1.0
    target_label = (target_return > threshold).astype(float)
    target_label = target_label.where(target_return.notna())

    matrix = panel.copy()
    matrix.insert(0, "anchor_close", close)
    matrix.insert(0, "as_of", anchor_index)
    matrix["target_forward_return"] = target_return
    matrix["target_label"] = target_label
    matrix = matrix.reset_index(drop=True)

    feature_columns = [
        c
        for c in matrix.columns
        if c
        not in {
            "as_of",
            "anchor_close",
            "target_forward_return",
            "target_label",
        }
    ]
    manifest = {
        "market": market_name,
        "symbol": market_spec["symbol"],
        "anchor_key": market_spec["anchor_key"],
        "historical_anchor_indicator_id": anchor_indicator,
        "horizon_observations": horizon,
        "positive_return_threshold": threshold,
        "include_groups": sorted(include_groups),
        "group_lag_observations": lag_policy,
        "max_ffill_observations": int(max_ffill),
        "rows": int(len(matrix)),
        "labeled_rows": int(matrix["target_label"].notna().sum()),
        "min_as_of": pd.Timestamp(matrix["as_of"].min()).isoformat(),
        "max_as_of": pd.Timestamp(matrix["as_of"].max()).isoformat(),
        "feature_columns": feature_columns,
        "feature_count": int(len(feature_columns)),
        "feature_groups": feature_groups,
        "availability_policy": "FIRST_ANCHOR_AT_OR_AFTER_AVAILABLE_TIME",
        "research_only": True,
        "live_execution": False,
        "neon_write": False,
        "toss_execution": False,
    }
    return matrix, anchor_prices, manifest


def main() -> int:
    args = parse_args()
    raw_path = Path(args.raw_parquet).expanduser()
    feature_path = Path(args.feature_parquet).expanduser()
    spec_path = Path(args.spec).expanduser()
    output_dir = Path(args.output_dir).expanduser()

    raw = pd.read_parquet(raw_path)
    features = pd.read_parquet(feature_path)
    validate_input_schema(raw, features)

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)

    status: dict[str, Any] = {
        "status": "READY",
        "dataset_version": spec["dataset_version"],
        "model_version": spec["version"],
        "feature_set": spec["feature_set"],
        "start_date": args.start_date,
        "raw_parquet": str(raw_path),
        "feature_parquet": str(feature_path),
        "raw_sha256": sha256_file(raw_path),
        "feature_sha256": sha256_file(feature_path),
        "research_only": True,
        "live_execution": False,
        "neon_write": False,
        "toss_execution": False,
        "markets": {},
    }

    for market_name, market_spec in spec["markets"].items():
        try:
            matrix, anchor_prices, manifest = build_market_historical_matrix(
                raw,
                features,
                market_name=market_name,
                market_spec=market_spec,
                start_date=args.start_date,
                max_ffill=int(spec.get("max_ffill_observations", 3)),
            )

            matrix_path = output_dir / f"{market_name.lower()}_matrix.parquet"
            anchor_path = output_dir / f"{market_name.lower()}_anchor_prices.parquet"
            matrix_sha = atomic_parquet(matrix, matrix_path)
            anchor_sha = atomic_parquet(anchor_prices, anchor_path)

            manifest["dataset_version"] = spec["dataset_version"]
            manifest["model_version"] = spec["version"]
            manifest["feature_set"] = spec["feature_set"]
            manifest["matrix_path"] = str(matrix_path)
            manifest["matrix_sha256"] = matrix_sha
            manifest["input_files"] = {
                str(anchor_path): {
                    "sha256": anchor_sha,
                    "kind": "raw",
                    "fetch_key": str(market_spec["anchor_key"]),
                    "group": market_name,
                    "source": "HISTORICAL_INTEGRATED_RAW",
                },
                str(raw_path): {
                    "sha256": status["raw_sha256"],
                    "kind": "historical_raw_source",
                },
                str(feature_path): {
                    "sha256": status["feature_sha256"],
                    "kind": "historical_feature_source",
                },
            }

            lineage_payload = {
                "dataset_version": spec["dataset_version"],
                "market": market_name,
                "matrix_sha256": matrix_sha,
                "anchor_sha256": anchor_sha,
                "raw_sha256": status["raw_sha256"],
                "feature_sha256": status["feature_sha256"],
                "availability_policy": manifest["availability_policy"],
            }
            manifest["lineage_sha256"] = hashlib.sha256(
                json.dumps(lineage_payload, sort_keys=True).encode("utf-8")
            ).hexdigest()
            manifest["built_at"] = pd.Timestamp.now(tz="UTC").isoformat()

            atomic_json(
                output_dir / f"{market_name.lower()}_matrix_manifest.json",
                manifest,
            )
            status["markets"][market_name] = {
                "status": "READY",
                "rows": int(len(matrix)),
                "labeled_rows": int(matrix["target_label"].notna().sum()),
                "feature_count": int(manifest["feature_count"]),
                "min_as_of": manifest["min_as_of"],
                "max_as_of": manifest["max_as_of"],
                "lineage_sha256": manifest["lineage_sha256"],
            }
        except Exception as exc:
            status["status"] = "FAIL"
            status["markets"][market_name] = {
                "status": "FAIL",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    atomic_json(output_dir / "historical_feature_matrix_run_status.json", status)
    print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    return 0 if status["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
