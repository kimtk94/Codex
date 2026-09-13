from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.quant_stack.historical_v2_candidate import (
    _buy_hold_equity,
    generate_inner_folds,
    generate_outer_folds,
    robust_select_features,
)


def _spec() -> dict:
    return {
        "minimum_feature_coverage": 0.80,
        "maximum_features": 32,
        "excluded_feature_suffixes": ["__coverage"],
        "near_zero_variance_threshold": 1e-12,
        "max_pairwise_feature_correlation": 0.95,
        "stability_blocks": 4,
    }


def _frame(rows: int = 900) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    as_of = pd.date_range("2018-01-01", periods=rows, freq="B", tz="UTC")
    signal = rng.normal(size=rows)
    target = (signal + rng.normal(scale=0.7, size=rows) > 0).astype(int)

    frame = pd.DataFrame(
        {
            "as_of": as_of,
            "anchor_close": 100.0 + np.cumsum(rng.normal(scale=0.5, size=rows)),
            "target_forward_return": rng.normal(scale=0.01, size=rows),
            "target_label": target,
            "signal": signal,
            "signal_duplicate": signal * 1.000001,
            "junk__coverage": np.linspace(0.80, 1.0, rows),
            "constant": 1.0,
        }
    )
    for i in range(60):
        frame[f"noise_{i:02d}"] = rng.normal(size=rows)
    return frame


def test_v2_selector_drops_coverage_constant_and_redundant_duplicate():
    selected, diagnostics = robust_select_features(_frame(), spec=_spec())

    assert 5 <= len(selected) <= 32
    assert "junk__coverage" not in selected
    assert "constant" not in selected
    assert not ({"signal", "signal_duplicate"} <= set(selected))

    diag = {row["feature"]: row for row in diagnostics}
    redundant = diag.get("signal_duplicate") or diag.get("signal")
    assert redundant is not None


def test_outer_fold_keeps_purge_gap_before_test():
    frame = _frame(1400)
    folds = generate_outer_folds(
        frame["as_of"],
        development_observations=756,
        test_observations=126,
        purge_observations=5,
    )
    assert folds
    first = folds[0]
    assert pd.Timestamp(first.test_start) > pd.Timestamp(first.development_end)
    development_end_i = frame.index[frame["as_of"] == pd.Timestamp(first.development_end)][0]
    test_start_i = frame.index[frame["as_of"] == pd.Timestamp(first.test_start)][0]
    assert test_start_i - development_end_i == 6


def test_inner_fold_keeps_purge_gap_before_validation():
    frame = _frame(756)
    folds = generate_inner_folds(
        frame,
        train_observations=504,
        validation_observations=63,
        purge_observations=5,
    )
    assert len(folds) >= 3
    first = folds[0]
    train_end_i = frame.index[frame["as_of"] == pd.Timestamp(first.train_end)][0]
    valid_start_i = frame.index[frame["as_of"] == pd.Timestamp(first.validation_start)][0]
    assert valid_start_i - train_end_i == 6


def test_buy_hold_equity_preserves_true_initial_cash_baseline():
    ts = pd.date_range("2024-01-01", periods=10, freq="D", tz="UTC")
    prices = pd.DataFrame(
        {
            "symbol": ["A"] * len(ts),
            "ts": ts,
            "open": np.linspace(100.0, 109.0, len(ts)),
            "close": np.linspace(100.5, 109.5, len(ts)),
        }
    )
    equity = _buy_hold_equity(
        prices,
        initial_cash=1_000_000.0,
        position_fraction=0.10,
        commission_bps=5.0,
        slippage_bps=5.0,
    )
    assert float(equity.iloc[0]["equity"]) == 1_000_000.0
    assert int(equity.iloc[0]["open_positions"]) == 0
    assert len(equity) == len(prices) + 1
