from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.model_v2.build_historical_feature_matrix import (
    align_indicator_block,
    build_market_historical_matrix,
    validate_input_schema,
)


def test_available_time_maps_to_next_anchor_without_lookahead():
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
            "event_time": pd.to_datetime(["2020-01-02T00:00:00Z"], utc=True),
            "available_time": pd.to_datetime(["2020-01-02T12:00:00Z"], utc=True),
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


def test_group_lag_is_applied_after_availability_alignment():
    anchors = pd.DatetimeIndex(
        pd.date_range("2020-01-01", periods=4, freq="D", tz="UTC")
    )
    features = pd.DataFrame(
        {
            "event_time": [anchors[0]],
            "available_time": [anchors[0]],
            "RET_1D": [0.1],
        }
    )
    aligned = align_indicator_block(
        features,
        anchor_index=anchors,
        max_ffill=3,
        lag_observations=1,
    )
    assert np.isnan(aligned.loc[anchors[0], "RET_1D"])
    assert aligned.loc[anchors[1], "RET_1D"] == 0.1


def test_market_matrix_uses_historical_anchor_and_forward_label():
    dates = pd.date_range("2017-01-01", periods=12, freq="D", tz="UTC")
    raw = pd.DataFrame(
        {
            "event_time": dates,
            "available_time": dates,
            "market": ["US"] * len(dates),
            "indicator_id": ["US_SPY"] * len(dates),
            "timeframe": ["1D"] * len(dates),
            "open": np.arange(100, 112, dtype=float),
            "high": np.arange(101, 113, dtype=float),
            "low": np.arange(99, 111, dtype=float),
            "close": np.arange(100, 112, dtype=float),
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
            "RET_1D": np.linspace(0.0, 0.11, len(dates)),
            "Z20": np.linspace(-1.0, 1.0, len(dates)),
        }
    )
    validate_input_schema(raw, features)

    market_spec = {
        "anchor_key": "yf_spy",
        "historical_anchor_indicator_id": "US_SPY",
        "symbol": "SPY",
        "horizon_observations": 2,
        "positive_return_threshold": 0.0,
        "include_groups": ["US"],
        "group_lag_observations": {"US": 0},
    }
    matrix, anchor, manifest = build_market_historical_matrix(
        raw,
        features,
        market_name="US",
        market_spec=market_spec,
        start_date="2017-01-01",
        max_ffill=3,
    )

    assert len(matrix) == 12
    assert len(anchor) == 12
    assert manifest["historical_anchor_indicator_id"] == "US_SPY"
    assert manifest["availability_policy"] == "FIRST_ANCHOR_AT_OR_AFTER_AVAILABLE_TIME"
    assert matrix["target_label"].notna().sum() == 10
    assert "us_spy__ret_1d" in matrix.columns
    assert bool((matrix.loc[:9, "target_label"] == 1.0).all())
