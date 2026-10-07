from __future__ import annotations

import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.quant_stack.r5_execution_stress import simulate_trade


def frame(rows):
    return pd.DataFrame(rows)


def test_intrabar_stop_fills_at_stop_before_slippage():
    f = frame([
        {"expected_seq": 1, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "quote_volume": 1_000_000},
        {"expected_seq": 2, "open": 100.0, "high": 101.0, "low": 96.0, "close": 98.0, "quote_volume": 1_000_000},
        {"expected_seq": 3, "open": 98.0, "high": 99.0, "low": 97.0, "close": 98.0, "quote_volume": 1_000_000},
    ])
    got = simulate_trade(f, entry_seq=1, exit_seq=3, stop_pct=-0.03, slippage_bps=0, cost_bps=0)
    assert got is not None
    assert got["exit_reason"] == "STOP_INTRABAR"
    assert got["exit_fill"] == 97.0
    assert abs(got["net_return"] + 0.03) < 1e-12


def test_gap_through_stop_uses_open_not_stop_price():
    f = frame([
        {"expected_seq": 1, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "quote_volume": 1_000_000},
        {"expected_seq": 2, "open": 90.0, "high": 92.0, "low": 88.0, "close": 91.0, "quote_volume": 1_000_000},
        {"expected_seq": 3, "open": 91.0, "high": 93.0, "low": 90.0, "close": 92.0, "quote_volume": 1_000_000},
    ])
    got = simulate_trade(f, entry_seq=1, exit_seq=3, stop_pct=-0.03, slippage_bps=0, cost_bps=0)
    assert got is not None
    assert got["exit_reason"] == "STOP_GAP_THROUGH"
    assert got["gap_through"] is True
    assert got["exit_fill"] == 90.0
    assert abs(got["net_return"] + 0.10) < 1e-12


def test_slippage_applies_to_entry_and_exit():
    f = frame([
        {"expected_seq": 1, "open": 100.0, "high": 105.0, "low": 99.0, "close": 104.0, "quote_volume": 1_000_000},
        {"expected_seq": 2, "open": 104.0, "high": 106.0, "low": 103.0, "close": 105.0, "quote_volume": 1_000_000},
    ])
    got = simulate_trade(f, entry_seq=1, exit_seq=2, stop_pct=-0.99, slippage_bps=10, cost_bps=10)
    assert got is not None
    expected_entry = 100.0 * 1.001
    expected_exit = 105.0 * 0.999
    expected = expected_exit / expected_entry - 1.0 - 0.001
    assert abs(got["net_return"] - expected) < 1e-12
