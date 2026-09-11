from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


STATIONARY_METRICS = [
    "ret1",
    "ret5",
    "ret20",
    "vol20",
    "z20",
    "ma20_gap",
    "ma50_gap",
    "rsi_centered",
    "macd_pct",
    "macd_hist_pct",
    "adx01",
    "atr_pct",
    "natr01",
    "roc10_01",
    "bb_pctb",
    "obv_z20",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build Kalman V2 US/KR/BTC feature matrices")
    p.add_argument("--market-root", required=True)
    p.add_argument("--feature-root", required=True)
    p.add_argument("--universe", required=True)
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


def _safe_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)


def _rolling_z(series: pd.Series, window: int = 20) -> pd.Series:
    mean = series.rolling(window, min_periods=window).mean()
    std = series.rolling(window, min_periods=window).std()
    return (series - mean) / std.replace(0, np.nan)


def _timestamp_index(frame: pd.DataFrame) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"], errors="coerce"))
    if idx.tz is not None:
        idx = idx.tz_convert(None)
    return idx.normalize()


def build_talib_map(feature_root: Path) -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    talib_dir = feature_root / "talib"
    if not talib_dir.exists():
        return mapping

    for metadata_path in talib_dir.glob("*.metadata.json"):
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        fetch_key = str(payload.get("fetch_key") or "").strip()
        parquet_path = metadata_path.with_name(
            metadata_path.name.replace(".metadata.json", ".parquet")
        )
        if fetch_key and parquet_path.exists():
            mapping[fetch_key] = parquet_path
    return mapping


def asset_feature_frame(
    raw: pd.DataFrame,
    *,
    fetch_key: str,
    talib: pd.DataFrame | None = None,
    annualizer: int = 252,
) -> pd.DataFrame:
    required = {"timestamp", "close"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"{fetch_key}: raw snapshot missing {sorted(missing)}")

    x = raw.copy()
    x.index = _timestamp_index(x)
    x = x.loc[~x.index.isna()].sort_index()
    x = x.loc[~x.index.duplicated(keep="last")]

    close = _safe_numeric(x["close"])
    ret1 = close.pct_change(fill_method=None)
    ma20 = close.rolling(20, min_periods=20).mean()
    ma50 = close.rolling(50, min_periods=50).mean()

    out = pd.DataFrame(index=x.index)
    out["ret1"] = ret1
    out["ret5"] = close.pct_change(5, fill_method=None)
    out["ret20"] = close.pct_change(20, fill_method=None)
    out["vol20"] = ret1.rolling(20, min_periods=20).std() * np.sqrt(annualizer)
    out["z20"] = _rolling_z(close, 20)
    out["ma20_gap"] = close / ma20.replace(0, np.nan) - 1.0
    out["ma50_gap"] = close / ma50.replace(0, np.nan) - 1.0

    if talib is not None and not talib.empty:
        t = talib.copy()
        t.index = _timestamp_index(t)
        t = t.loc[~t.index.isna()].sort_index()
        t = t.loc[~t.index.duplicated(keep="last")]
        t = t.reindex(out.index)

        rsi = _safe_numeric(t.get("talib_v2_rsi14", pd.Series(index=t.index, dtype=float)))
        macd = _safe_numeric(t.get("talib_v2_macd", pd.Series(index=t.index, dtype=float)))
        macd_hist = _safe_numeric(
            t.get("talib_v2_macd_hist", pd.Series(index=t.index, dtype=float))
        )
        adx = _safe_numeric(t.get("talib_v2_adx14", pd.Series(index=t.index, dtype=float)))
        atr = _safe_numeric(t.get("talib_v2_atr14", pd.Series(index=t.index, dtype=float)))
        natr = _safe_numeric(t.get("talib_v2_natr14", pd.Series(index=t.index, dtype=float)))
        roc = _safe_numeric(t.get("talib_v2_roc10", pd.Series(index=t.index, dtype=float)))
        pctb = _safe_numeric(t.get("talib_v2_bb_pctb", pd.Series(index=t.index, dtype=float)))
        obv = _safe_numeric(t.get("talib_v2_obv", pd.Series(index=t.index, dtype=float)))

        out["rsi_centered"] = (rsi - 50.0) / 50.0
        out["macd_pct"] = macd / close.replace(0, np.nan)
        out["macd_hist_pct"] = macd_hist / close.replace(0, np.nan)
        out["adx01"] = adx / 100.0
        out["atr_pct"] = atr / close.replace(0, np.nan)
        out["natr01"] = natr / 100.0
        out["roc10_01"] = roc / 100.0
        out["bb_pctb"] = pctb
        out["obv_z20"] = _rolling_z(obv, 20)
    else:
        for col in STATIONARY_METRICS[7:]:
            out[col] = np.nan

    out = out[STATIONARY_METRICS]
    return out.rename(columns={c: f"{fetch_key}__{c}" for c in out.columns})


def group_aggregate_features(
    frame: pd.DataFrame,
    *,
    feature_groups: dict[str, str],
) -> pd.DataFrame:
    out = pd.DataFrame(index=frame.index)
    metrics = [
        "ret1",
        "ret5",
        "ret20",
        "vol20",
        "ma20_gap",
        "ma50_gap",
        "rsi_centered",
        "natr01",
        "bb_pctb",
    ]

    for group in sorted(set(feature_groups.values())):
        group_keys = [key for key, value in feature_groups.items() if value == group]
        for metric in metrics:
            columns = [
                f"{key}__{metric}"
                for key in group_keys
                if f"{key}__{metric}" in frame.columns
            ]
            if not columns:
                continue
            values = frame[columns]
            prefix = f"group_{group.lower()}__{metric}"
            out[f"{prefix}__median"] = values.median(axis=1, skipna=True)
            out[f"{prefix}__coverage"] = values.notna().sum(axis=1) / len(columns)
            if metric in {
                "ret1",
                "ret5",
                "ret20",
                "ma20_gap",
                "ma50_gap",
                "rsi_centered",
            }:
                out[f"{prefix}__positive_ratio"] = (
                    (values > 0).where(values.notna()).mean(axis=1)
                )
    return out


def build_market_matrix(
    *,
    market_name: str,
    market_spec: dict[str, Any],
    universe: dict[str, Any],
    market_root: Path,
    feature_root: Path,
    max_ffill: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    yfinance_assets = {
        str(item["key"]): item
        for item in universe["assets"]
        if str(item.get("provider", "")).lower() == "yfinance"
    }
    anchor_key = str(market_spec["anchor_key"])
    if anchor_key not in yfinance_assets:
        raise ValueError(f"{market_name}: anchor {anchor_key} not in yfinance universe")

    anchor_path = market_root / "raw" / "yfinance" / f"{anchor_key}.parquet"
    if not anchor_path.exists():
        raise FileNotFoundError(anchor_path)

    anchor_raw = pd.read_parquet(anchor_path)
    anchor_index = _timestamp_index(anchor_raw)
    anchor_close = pd.Series(
        _safe_numeric(anchor_raw["close"]).to_numpy(),
        index=anchor_index,
        dtype=float,
    )
    anchor_close = anchor_close.loc[~anchor_close.index.duplicated(keep="last")].sort_index()
    anchor_index = anchor_close.dropna().index
    if len(anchor_index) < 50:
        raise RuntimeError(f"{market_name}: insufficient anchor observations")

    talib_map = build_talib_map(feature_root)
    include_groups = {str(x).upper() for x in market_spec["include_groups"]}
    lag_policy = {
        str(k).upper(): int(v)
        for k, v in market_spec.get("group_lag_observations", {}).items()
    }

    aligned_parts: list[pd.DataFrame] = []
    feature_groups: dict[str, str] = {}
    input_files: dict[str, dict[str, Any]] = {}

    for fetch_key, asset in yfinance_assets.items():
        group = str(asset.get("group") or "UNGROUPED").upper()
        if group not in include_groups:
            continue
        raw_path = market_root / "raw" / "yfinance" / f"{fetch_key}.parquet"
        if not raw_path.exists():
            continue

        raw = pd.read_parquet(raw_path)
        talib_path = talib_map.get(fetch_key)
        talib = pd.read_parquet(talib_path) if talib_path else None
        annualizer = 365 if str(asset.get("kind")).lower() == "crypto" else 252
        block = asset_feature_frame(
            raw,
            fetch_key=fetch_key,
            talib=talib,
            annualizer=annualizer,
        )
        block = block.reindex(anchor_index).ffill(limit=max_ffill)
        lag = max(0, int(lag_policy.get(group, 1)))
        if lag:
            block = block.shift(lag)

        aligned_parts.append(block)
        feature_groups[fetch_key] = group
        input_files[str(raw_path)] = {
            "sha256": sha256_file(raw_path),
            "kind": "raw",
            "fetch_key": fetch_key,
            "group": group,
        }
        if talib_path:
            input_files[str(talib_path)] = {
                "sha256": sha256_file(talib_path),
                "kind": "talib",
                "fetch_key": fetch_key,
                "group": group,
            }

    if not aligned_parts:
        raise RuntimeError(f"{market_name}: no aligned feature blocks")

    features = pd.concat(aligned_parts, axis=1).sort_index()
    aggregates = group_aggregate_features(features, feature_groups=feature_groups)
    features = pd.concat([features, aggregates], axis=1)

    close = anchor_close.reindex(anchor_index)
    horizon = int(market_spec["horizon_observations"])
    threshold = float(market_spec.get("positive_return_threshold", 0.0))
    target_return = close.shift(-horizon) / close - 1.0
    target_label = (target_return > threshold).astype(float)
    target_label = target_label.where(target_return.notna())

    matrix = features.copy()
    matrix.insert(0, "anchor_close", close)
    matrix.insert(0, "as_of", matrix.index)
    matrix["target_forward_return"] = target_return
    matrix["target_label"] = target_label
    matrix = matrix.reset_index(drop=True)

    manifest = {
        "market": market_name,
        "symbol": market_spec["symbol"],
        "anchor_key": anchor_key,
        "horizon_observations": horizon,
        "positive_return_threshold": threshold,
        "include_groups": sorted(include_groups),
        "group_lag_observations": lag_policy,
        "max_ffill_observations": max_ffill,
        "rows": int(len(matrix)),
        "feature_columns": [
            c
            for c in matrix.columns
            if c not in {
                "as_of",
                "anchor_close",
                "target_forward_return",
                "target_label",
            }
        ],
        "feature_count": int(
            len(matrix.columns)
            - len(
                {
                    "as_of",
                    "anchor_close",
                    "target_forward_return",
                    "target_label",
                }
            )
        ),
        "feature_groups": feature_groups,
        "input_files": input_files,
    }
    return matrix, manifest


def main() -> int:
    args = parse_args()
    market_root = Path(args.market_root).expanduser()
    feature_root = Path(args.feature_root).expanduser()
    universe_path = Path(args.universe).expanduser()
    spec_path = Path(args.spec).expanduser()
    output_dir = Path(args.output_dir).expanduser()

    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)

    status: dict[str, Any] = {
        "status": "READY",
        "dataset_version": spec["dataset_version"],
        "model_version": spec["version"],
        "shadow_only": True,
        "markets": {},
    }

    for market_name, market_spec in spec["markets"].items():
        try:
            matrix, manifest = build_market_matrix(
                market_name=market_name,
                market_spec=market_spec,
                universe=universe,
                market_root=market_root,
                feature_root=feature_root,
                max_ffill=int(spec.get("max_ffill_observations", 3)),
            )
            matrix_path = output_dir / f"{market_name.lower()}_matrix.parquet"
            matrix_sha = atomic_parquet(matrix, matrix_path)
            lineage_payload = {
                "dataset_version": spec["dataset_version"],
                "market": market_name,
                "spec_sha256": sha256_file(spec_path),
                "universe_sha256": sha256_file(universe_path),
                "matrix_sha256": matrix_sha,
                "inputs": {
                    path: meta["sha256"]
                    for path, meta in sorted(manifest["input_files"].items())
                },
            }
            lineage_hash = hashlib.sha256(
                json.dumps(lineage_payload, sort_keys=True).encode("utf-8")
            ).hexdigest()
            manifest.update(
                {
                    "dataset_version": spec["dataset_version"],
                    "model_version": spec["version"],
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

    atomic_json(output_dir / "feature_matrix_run_status.json", status)
    print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    return 0 if status["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
