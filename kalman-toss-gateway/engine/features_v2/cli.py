from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

from engine.market_data.snapshot import atomic_json, write_snapshot
from .registry import FEATURE_SET, registry_payload
from .talib_features import build_talib_features, compare_legacy_rsi


ASSETS = {
    "SPY": "yf_spy.parquet",
    "BTC-USD": "yf_btc.parquet",
    "KOSPI": "yf_kospi.parquet",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build TA-Lib Market Tools V2 features")
    p.add_argument("--input-dir")
    p.add_argument("--output-dir")
    return p.parse_args()


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
    output_dir = Path(
        args.output_dir
        or os.environ.get(
            "KALMAN_FEATURES_V2_OUTPUT_DIR",
            str(data_root / "Market_Features" / "v2"),
        )
    ).expanduser()

    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(output_dir / "feature_registry.json", registry_payload())

    assets: dict[str, Any] = {}
    required_failures: list[str] = []

    for symbol, filename in ASSETS.items():
        required = symbol in {"SPY", "BTC-USD"}
        source_path = input_dir / filename
        if not source_path.exists():
            assets[symbol] = {
                "status": "MISSING",
                "required": required,
                "source_path": str(source_path),
            }
            if required:
                required_failures.append(symbol)
            continue

        try:
            frame = pd.read_parquet(source_path)
            features = build_talib_features(frame)
            comparison = compare_legacy_rsi(frame, features)
            safe_symbol = symbol.replace("/", "_").replace("-", "_").lower()
            manifest = write_snapshot(
                features,
                output_dir / "talib" / f"{safe_symbol}.parquet",
                metadata={
                    "feature_set": FEATURE_SET,
                    "symbol": symbol,
                    "source_snapshot": str(source_path),
                    "shadow_only": True,
                    "point_in_time": True,
                    "legacy_rsi_comparison": comparison,
                },
            )
            assets[symbol] = {
                "status": "READY",
                "required": required,
                "rows": int(len(features)),
                "legacy_rsi_comparison": comparison,
                "manifest": manifest,
            }
        except Exception as exc:
            assets[symbol] = {
                "status": "FAIL",
                "required": required,
                "source_path": str(source_path),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            if required:
                required_failures.append(symbol)

    status_name = "FAIL" if required_failures else (
        "DEGRADED" if any(x.get("status") != "READY" for x in assets.values()) else "READY"
    )
    status = {
        "status": status_name,
        "feature_set": FEATURE_SET,
        "shadow_only": True,
        "production_writes": False,
        "built_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "required_failures": required_failures,
        "assets": assets,
    }
    atomic_json(output_dir / "features_v2_run_status.json", status)
    print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    return 2 if required_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
