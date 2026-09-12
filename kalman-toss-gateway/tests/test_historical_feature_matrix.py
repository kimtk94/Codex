from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.model_v2.build_historical_feature_matrix import (
    ANCHOR_INDICATOR_BY_KEY,
    HISTORICAL_DATASET_VERSION,
    HISTORICAL_FEATURE_SET,
    build_all,
    build_market_matrix,
    historical_spec,
)


def _days(n=900):
    return pd.date_range("2016-12-01", periods=n, freq="D", tz="UTC")


def _raw_frame():
    days = _days()
    rows = []
    anchors = {
        "US_SPY": 100.0,
        "KR_KOSPI": 2000.0,
        "BTC_BTCUSD": 1000.0,
    }
    for indicator, base in anchors.items():
        for i, ts in enumerate(days):
            close = base + i * 0.5 + np.sin(i / 13.0)
            rows.append(
                {
                    "event_time": ts,
                    "available_time": ts,
                    "market": indicator.split("_", 1)[0],
                    "indicator_id": indicator,
                    "timeframe": "1D",
                    "open": close * 0.999,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "volume": 1000 + i,
                }
            )
    return pd.DataFrame(rows)


def _feature_frame():
    days = _days()
    definitions = [
        ("US", "US_SPY", 1.0),
        ("US", "US_QQQ", 1.2),
        ("KR", "KR_KOSPI", 2.0),
        ("COMMON", "COMMON_DXY", 3.0),
        ("BTC", "BTC_BTCUSD", 4.0),
    ]
    rows = []
    for market, indicator, scale in definitions:
        for i, ts in enumerate(days):
            value = scale + i * 0.001
            rows.append(
                {
                    "event_time": ts,
                    "available_time": ts,
                    "market": market,
                    "indicator_id": indicator,
                    "timeframe": "1D",
                    "feature_family": "PRICE",
                    "RAW_VALUE": value,
                    "CHG_1": i / 10000.0,
                    "CHG_5": i / 9000.0,
                    "CHG_20": i / 8000.0,
                    "Z20": np.sin(i / 20.0),
                    "RET_1D": i / 10000.0,
                    "RET_5D": i / 9000.0,
                    "RET_20D": i / 8000.0,
                    "MA20_DIST": np.sin(i / 30.0),
                    "MA50_DIST": np.sin(i / 50.0),
                    "RSI14": 50 + 10 * np.sin(i / 14.0),
                    "RV20": 0.2,
                    "ATR14_PCT": 0.01,
                }
            )
    return pd.DataFrame(rows)


def _spec():
    return {
        "version": "model",
        "feature_set": "current",
        "dataset_version": "current_data",
        "max_ffill_observations": 3,
        "minimum_feature_coverage": 0.80,
        "maximum_features": 96,
        "candidate_c": [0.01, 0.1, 1.0],
        "threshold_grid": [0.50, 0.55, 0.60, 0.65],
        "markets": {
            "US": {
                "anchor_key": "yf_spy",
                "symbol": "SPY",
                "horizon_observations": 5,
                "positive_return_threshold": 0.0,
                "include_groups": ["US", "COMMON", "BTC", "KR"],
                "group_lag_observations": {"US": 0, "COMMON": 0, "BTC": 1, "KR": 0},
                "strategy_version": "US",
            },
            "KR": {
                "anchor_key": "yf_kospi",
                "symbol": "KOSPI",
                "horizon_observations": 5,
                "positive_return_threshold": 0.0,
                "include_groups": ["KR", "COMMON", "US", "BTC"],
                "group_lag_observations": {"KR": 0, "COMMON": 1, "US": 1, "BTC": 0},
                "strategy_version": "KR",
            },
            "BTC": {
                "anchor_key": "yf_btc",
                "symbol": "BTC-USD",
                "horizon_observations": 7,
                "positive_return_threshold": 0.0,
                "include_groups": ["BTC", "COMMON", "US", "KR"],
                "group_lag_observations": {"BTC": 0, "COMMON": 1, "US": 1, "KR": 0},
                "strategy_version": "BTC",
            },
        },
    }


def test_historical_spec_is_explicitly_not_current_v2_feature_parity():
    derived = historical_spec(_spec())
    assert derived["feature_set"] == HISTORICAL_FEATURE_SET
    assert derived["dataset_version"] == HISTORICAL_DATASET_VERSION
    assert derived["historical_reconstruction"]["exact_current_v2_feature_parity"] is False


def test_build_market_matrix_uses_historical_anchor_and_lag(tmp_path):
    raw = _raw_frame()
    features = _feature_frame()
    raw_path = tmp_path / "raw.parquet"
    feature_path = tmp_path / "features.parquet"
    raw.to_parquet(raw_path, index=False)
    features.to_parquet(feature_path, index=False)

    matrix, manifest = build_market_matrix(
        market_name="US",
        market_spec=_spec()["markets"]["US"],
        historical_raw=raw,
        historical_features=features,
        output_dir=tmp_path,
        max_ffill=3,
        raw_source_path=raw_path,
        feature_source_path=feature_path,
    )

    assert len(matrix) == 900
    assert matrix["target_label"].notna().sum() == 895
    assert pd.to_datetime(matrix["as_of"], utc=True).min().year == 2016
    assert manifest["historical_anchor_indicator"] == ANCHOR_INDICATOR_BY_KEY["yf_spy"]
    assert manifest["feature_schema"] == HISTORICAL_FEATURE_SET

    anchor_path = tmp_path / "us_anchor_raw.parquet"
    assert anchor_path.exists()
    anchor = pd.read_parquet(anchor_path)
    assert {"timestamp", "open", "close"}.issubset(anchor.columns)

    # BTC is lagged one observation for the US model.
    btc_col = "BTC_BTCUSD__RAW_VALUE"
    source = features.loc[
        features["indicator_id"].eq("BTC_BTCUSD"), "RAW_VALUE"
    ].reset_index(drop=True)
    assert pd.isna(matrix.loc[0, btc_col])
    assert matrix.loc[1, btc_col] == source.iloc[0]


def test_build_all_writes_three_2017_ready_matrices(tmp_path):
    raw_path = tmp_path / "raw.parquet"
    feature_path = tmp_path / "features.parquet"
    spec_path = tmp_path / "spec.json"
    output_dir = tmp_path / "out"

    _raw_frame().to_parquet(raw_path, index=False)
    _feature_frame().to_parquet(feature_path, index=False)
    spec_path.write_text(json.dumps(_spec()), encoding="utf-8")

    status = build_all(
        historical_raw_path=raw_path,
        historical_feature_path=feature_path,
        spec_path=spec_path,
        output_dir=output_dir,
    )
    assert status["status"] == "READY"
    for market in ("US", "KR", "BTC"):
        assert status["markets"][market]["status"] == "READY"
        assert status["markets"][market]["labeled_rows"] > 700
        assert (output_dir / f"{market.lower()}_matrix.parquet").exists()
        assert (output_dir / f"{market.lower()}_matrix_manifest.json").exists()

    assert (output_dir / "historical_model_v2_spec.json").exists()
