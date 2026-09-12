from __future__ import annotations

import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.quant_stack.contracts import BacktestConfig
from research.quant_stack.native_ledger import map_next_bar, run_backtest
from research.quant_stack.portfolio import inverse_volatility
from research.quant_stack.walk_forward import generate_walk_forward_folds


def test_walk_forward_has_purge_gap():
    idx = pd.date_range("2017-01-02", periods=900, freq="B", tz="UTC")
    folds = generate_walk_forward_folds(
        idx,
        train_observations=504,
        valid_observations=63,
        test_observations=126,
        purge_observations=5,
    )
    assert folds
    first = folds[0]
    assert pd.Timestamp(first.valid_start) > pd.Timestamp(first.train_end)
    assert pd.Timestamp(first.test_start) > pd.Timestamp(first.valid_end)


def test_next_bar_is_strictly_after_signal():
    prices = pd.DataFrame(
        {
            "symbol": ["A", "A", "A"],
            "ts": pd.to_datetime(
                ["2026-09-10T13:30:00Z", "2026-09-10T14:30:00Z", "2026-09-10T15:30:00Z"]
            ),
            "open": [100.0, 101.0, 102.0],
            "close": [100.5, 101.5, 102.5],
        }
    )
    signals = pd.DataFrame(
        {
            "symbol": ["A"],
            "signal_ts": pd.to_datetime(["2026-09-10T14:30:00Z"]),
            "signal": ["BUY"],
            "entry_allowed": [True],
        }
    )
    mapped = map_next_bar(signals, prices)
    assert len(mapped) == 1
    assert mapped.iloc[0]["fill_ts"] == pd.Timestamp("2026-09-10T15:30:00Z")


def test_backtest_buy_then_sell():
    prices = pd.DataFrame(
        {
            "symbol": ["A"] * 4,
            "ts": pd.to_datetime(
                [
                    "2026-09-10T13:30:00Z",
                    "2026-09-10T14:30:00Z",
                    "2026-09-10T15:30:00Z",
                    "2026-09-10T16:30:00Z",
                ]
            ),
            "open": [100.0, 101.0, 102.0, 103.0],
            "close": [100.0, 101.0, 102.0, 103.0],
        }
    )
    signals = pd.DataFrame(
        {
            "symbol": ["A", "A"],
            "signal_ts": pd.to_datetime(["2026-09-10T13:30:00Z", "2026-09-10T15:30:00Z"]),
            "signal": ["BUY", "SELL"],
            "entry_allowed": [True, True],
        }
    )
    result = run_backtest(
        signals,
        prices,
        BacktestConfig(
            initial_cash=10_000.0,
            position_fraction=1.0,
            max_open_positions=1,
            commission_bps=0.0,
            slippage_bps=0.0,
            max_hold_bars=None,
        ),
    )
    assert len(result.trades) == 1
    assert result.trades.iloc[0]["entry_price"] == 101.0
    assert result.trades.iloc[0]["exit_price"] == 103.0
    assert result.metrics["trade_count"] == 1


def test_inverse_volatility_prefers_lower_vol_asset():
    returns = pd.DataFrame(
        {
            "low": [0.001, 0.002, 0.001, 0.002],
            "high": [0.01, -0.02, 0.03, -0.01],
        }
    )
    weights = inverse_volatility(returns)
    assert weights["low"] > weights["high"]
    assert abs(float(weights.sum()) - 1.0) < 1e-12
