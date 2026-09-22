from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

from engine.market_data.snapshot import atomic_json, write_snapshot
from engine.features_v2.compare import compare_legacy_rsi if False else None
from engine.features_v2.talib_features import compare_legacy_rsi
from .registry import FEATURE_SET, registry_payload
from .talib_features import build_talib_features


REQUIRED_FETCH_KEYS = {"yf_spy", "yf_btc"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build isolated TA-Lib V2.002 research features")
    p.add_argument("--input-dir")
    p.add_argument("--output-dir", required=True)
    return p.parse_args()


def _safe_symbol(symbol: str) -> str:
    safe = "".join(c.lower() if c.isalnum() else "_" for c in symbol).strip("_")
    while "__" in safe:
        safe = safe.replace("__", "_")
    return safe or "unknown"


def main() -> int:
    env_file = Path(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env")).expanduser()
    if env_file.exists():
        load_dotenv(env_file, override=True)

    args = parse_args()
    data_root = Path(os.environ.get("KALMAN_DATA_ROOT", "/opt/kalman/data")).expanduser()
    market_root = Path(
        os.environ.get("KALMAN_MARKET_V2_OUTPUT_DIR", str(data_root / "Market_Data" / "v2"))
    ).expanduser()
    input_dir = Path(args.input_dir or market_root / "raw" / "yfinance").expanduser()
    output_dir = Path(args.output_dir).expanduser()

    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(output_dir / "feature_registry.json", registry_payload())

    source_files = sorted(input_dir.glob("*.parquet"))
    if not source_files:
        status = {
            "status": "FAIL",
            "feature_set": FEATURE_SET,
            "shadow_only": True,
            "production_writes": False,
            "error": "no yfinance snapshots found",
        }
        atomic_json(output_dir / "features_v2_002_run_status.json", status)
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 2

    assets: dict[str, Any] = {}
    required_failures: list[str] = []
    output_symbols: set[str] = set()

    for source_path in source_files:
        fetch_key = source_path.stem
        required = fetch_key in REQUIRED_FETCH_KEYS
        try:
            frame = pd.read_parquet(source_path)
            symbols = frame["symbol"].dropna().astype(str).unique().tolist()
            if len(symbols) != 1:
                raise ValueError(f"expected one symbol, found {symbols}")
            symbol = symbols[0]
            safe_symbol = _safe_symbol(symbol)
            if safe_symbol in output_symbols:
                raise ValueError(f"duplicate feature output symbol: {safe_symbol}")
            output_symbols.add(safe_symbol)

            features = build_talib_features(frame)
            comparison = compare_legacy_rsi(frame, features)
            manifest = write_snapshot(
                features,
                output_dir / "talib" / f"{safe_symbol}.parquet",
                metadata={
                    "feature_set": FEATURE_SET,
                    "fetch_key": fetch_key,
                    "symbol": symbol,
                    "source_snapshot": str(source_path),
                    "shadow_only": True,
                    "point_in_time": True,
                    "sparse_gap_policy": "FINITE_OBSERVATION_SEQUENCE_NO_PRICE_IMPUTATION",
                    "legacy_rsi_comparison": comparison,
                },
            )
            assets[fetch_key] = {
                "status": "READY",
                "required": required,
                "symbol": symbol,
                "rows": int(len(features)),
                "rsi_valid_rows": int(features["talib_v2_rsi14"].notna().sum()),
                "legacy_rsi_comparison": comparison,
                "manifest": manifest,
            }
        except Exception as exc:
            assets[fetch_key] = {
                "status": "FAIL",
                "required": required,
                "source_path": str(source_path),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            if required:
                required_failures.append(fetch_key)

    status = {
        "status": "FAIL" if required_failures else "READY",
        "feature_set": FEATURE_SET,
        "shadow_only": True,
        "production_writes": False,
        "built_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "required_failures": required_failures,
        "assets": assets,
    }
    atomic_json(output_dir / "features_v2_002_run_status.json", status)
    print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    return 2 if required_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
