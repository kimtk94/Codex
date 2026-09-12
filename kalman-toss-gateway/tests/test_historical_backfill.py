from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.quant_stack.contracts import ExperimentSpec, Mode
from research.quant_stack.historical_backfill import run_historical_backfill
from research.model_v2.build_historical_feature_matrix import (
    align_indicator_block,
    build_market_historical_matrix,
)


def _synthetic_matrix(rows: int = 900) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    idx = pd.date_range("2017-01-02", periods=rows, freq="B", tz="UTC")
    latent = rng.normal(size=rows)
    target = (latent + rng.normal(scale=0.35, size=rows) > 0).astype(float)

    frame = pd.DataFrame(
        {
            "as_of": idx,
            "anchor_close": 100.0 + np.cumsum(rng.normal(scale=0.5, size=rows)),
            "f1": latent + rng.normal(scale=0.1, size=rows),
            "f2": latent * 0.5 + rng.normal(scale=0.2, size=rows),
            "f3": rng.normal(size=rows),
            "f4": rng.normal(size=rows),
            "f5": rng.normal(size=rows),
            "f6": rng.normal(size=rows),
            "target_forward_return": np.where(target > 0, 0.01, -0.01),
            "target_label": target,
        }
    )
    return frame


def test_historical_backfill_is_prospective_only():
    matrix = _synthetic_matrix()
    result = run_historical_backfill(
        matrix,
        market_name="US",
        market_spec={
            "symbol": "SPY",
            "horizon_observations": 5,
        },
        global_spec={
            "feature_set": "test_features",
            "version": "test_model",
            "minimum_feature_coverage": 0.8,
            "maximum_features": 6,
            "candidate_c": [0.01, 0.1],
            "threshold_grid": [0.50, 0.55, 0.60],
        },
        experiment_spec=ExperimentSpec(
            experiment_name="synthetic",
            market="US",
            feature_version="test_features",
            model_version="test_model",
            start_date="2017-01-01",
            mode=Mode.BACKTEST,
        ),
        train_observations=300,
        valid_observations=60,
        test_observations=100,
        purge_observations=5,
    )

    assert not result.model_output.empty
    assert set(result.strategy_signal["signal"]).issubset({"BUY", "SELL", "HOLD"})
    assert len(result.fold_metrics) >= 2

    for item in result.fold_metrics:
        fold = item["fold"]
        assert pd.Timestamp(fold["train_end"]) < pd.Timestamp(fold["valid_start"])
        assert pd.Timestamp(fold["valid_end"]) < pd.Timestamp(fold["test_start"])


def test_signal_output_has_no_duplicate_timestamp():
    matrix = _synthetic_matrix()
    result = run_historical_backfill(
        matrix,
        market_name="BTC",
        market_spec={
            "symbol": "BTC-USD",
            "horizon_observations": 7,
        },
        global_spec={
            "feature_set": "test_features",
            "version": "test_model",
            "minimum_feature_coverage": 0.8,
            "maximum_features": 6,
            "candidate_c": [0.1],
            "threshold_grid": [0.50, 0.55],
        },
        experiment_spec=ExperimentSpec(
            experiment_name="synthetic_btc",
            market="BTC",
            feature_version="test_features",
            model_version="test_model",
            start_date="2017-01-01",
            mode=Mode.BACKTEST,
        ),
        train_observations=300,
        valid_observations=60,
        test_observations=100,
        purge_observations=7,
    )

    assert not result.model_output.duplicated(["market", "symbol", "as_of"]).any()



def test_historical_feature_availability_is_prospective_only():
    anchors = pd.DatetimeIndex(
        pd.to_datetime(
            [
                "2020-01-01T00:00:00Z",
                "2020-01-02T00:00:00Z",
                "2020-01-03T00:00:00Z",
                "2020-01-04T00:00:00Z",
            ],
            utc=True,
        )
    )
    features = pd.DataFrame(
        {
            "event_time": pd.to_datetime(
                ["2020-01-02T00:00:00Z"],
                utc=True,
            ),
            "available_time": pd.to_datetime(
                ["2020-01-02T12:00:00Z"],
                utc=True,
            ),
            "RET_1D": [0.25],
        }
    )

    aligned = align_indicator_block(
        features,
        anchor_index=anchors,
        max_ffill=1,
        lag_observations=0,
    )

    assert np.isnan(aligned.loc[anchors[1], "RET_1D"])
    assert aligned.loc[anchors[2], "RET_1D"] == 0.25
    assert aligned.loc[anchors[3], "RET_1D"] == 0.25


def test_historical_market_matrix_builds_2017_anchor_rows():
    dates = pd.date_range("2017-01-01", periods=20, freq="D", tz="UTC")
    raw = pd.DataFrame(
        {
            "event_time": dates,
            "available_time": dates,
            "market": ["US"] * len(dates),
            "indicator_id": ["US_SPY"] * len(dates),
            "timeframe": ["1D"] * len(dates),
            "open": np.arange(100, 120, dtype=float),
            "high": np.arange(101, 121, dtype=float),
            "low": np.arange(99, 119, dtype=float),
            "close": np.arange(100, 120, dtype=float),
        }
    )
    features = pd.DataFrame(
        {
            "event_time": dates,
            "available_time": dates,
            "market": ["US"] * len(dates),
            "indicator_id": ["US_SPY"] * len(dates),
            "timeframe": ["1D"] * len(dates),
            "feature_family": ["PRICE"] * len(dates),
            "RET_1D": np.linspace(0.0, 0.19, len(dates)),
            "Z20": np.linspace(-1.0, 1.0, len(dates)),
        }
    )

    matrix, anchor, manifest = build_market_historical_matrix(
        raw,
        features,
        market_name="US",
        market_spec={
            "anchor_key": "yf_spy",
            "historical_anchor_indicator_id": "US_SPY",
            "symbol": "SPY",
            "horizon_observations": 5,
            "positive_return_threshold": 0.0,
            "include_groups": ["US"],
            "group_lag_observations": {"US": 0},
        },
        start_date="2017-01-01",
        max_ffill=3,
    )

    assert len(matrix) == 20
    assert len(anchor) == 20
    assert matrix["target_label"].notna().sum() == 15
    assert manifest["historical_anchor_indicator_id"] == "US_SPY"
    assert manifest["availability_policy"] == (
        "FIRST_ANCHOR_AT_OR_AFTER_AVAILABLE_TIME"
    )
    assert "us_spy__ret_1d" in matrix.columns
