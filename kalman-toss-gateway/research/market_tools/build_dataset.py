from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_FILES = {
    "SPY": ("yf_spy.parquet", "spy.parquet"),
    "BTC-USD": ("yf_btc.parquet", "btc_usd.parquet"),
    "KOSPI": ("yf_kospi.parquet", "kospi.parquet"),
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build fixed Market Tools V2 research dataset")
    p.add_argument("--symbol", required=True, choices=sorted(DEFAULT_FILES))
    p.add_argument("--market-root", required=True)
    p.add_argument("--feature-root", required=True)
    p.add_argument("--output", required=True)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    market_name, feature_name = DEFAULT_FILES[args.symbol]
    price_path = Path(args.market_root) / "raw" / "yfinance" / market_name
    feature_path = Path(args.feature_root) / "talib" / feature_name

    if not price_path.exists():
        raise FileNotFoundError(price_path)
    if not feature_path.exists():
        raise FileNotFoundError(feature_path)

    price = pd.read_parquet(price_path)
    feature = pd.read_parquet(feature_path)

    price["timestamp"] = pd.to_datetime(price["timestamp"], errors="raise")
    feature["timestamp"] = pd.to_datetime(feature["timestamp"], errors="raise")

    merged = price.merge(
        feature.drop(columns=["symbol"], errors="ignore"),
        on="timestamp",
        how="inner",
        validate="one_to_one",
    )
    merged = merged.sort_values("timestamp").reset_index(drop=True)
    merged["research_symbol"] = args.symbol
    merged["dataset_point_in_time"] = True

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".tmp")
    merged.to_parquet(tmp, index=False)
    tmp.replace(output)
    print(f"WROTE {output} rows={len(merged)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
