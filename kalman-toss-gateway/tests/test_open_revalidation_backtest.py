from __future__ import annotations

import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.quant_stack.open_revalidation_backtest import (
    POLICIES,
    _effective_bar_close,
    extract_revalidation_features,
    policy_trigger,
)


def _bars() -> pd.DataFrame:
    rows = [
        # Entry day, EDT (UTC-4)
        ("2025-09-15T19:29:00Z", 100.0, 100.0),  # 15:29 ET, entry fill proxy
        ("2025-09-15T19:59:00Z", 101.0, 101.0),  # 15:59 ET, prior close
        # Next session
        ("2025-09-16T13:30:00Z", 99.0, 99.1),   # 09:30 ET
        ("2025-09-16T13:35:00Z", 98.5, 98.6),   # 09:35 ET
        ("2025-09-16T13:45:00Z", 98.0, 98.1),   # 09:45 ET
        ("2025-09-16T15:29:00Z", 97.0, 97.0),   # 11:29 ET, fixed4 fill proxy
    ]
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime([x[0] for x in rows], utc=True),
            "open": [x[1] for x in rows],
            "high": [max(x[1], x[2]) for x in rows],
            "low": [min(x[1], x[2]) for x in rows],
            "close": [x[2] for x in rows],
            "volume": [1000] * len(rows),
            "trade_count": [10] * len(rows),
            "vwap": [x[2] for x in rows],
        }
    )


def test_final_regular_session_bucket_is_truncated_at_1600_et():
    # 19:30 UTC = 15:30 ET during DST. A nominal +60m close would be 16:30 ET,
    # but the regular session ends at 16:00 ET.
    got = _effective_bar_close("2025-09-15T19:30:00Z")
    assert got == pd.Timestamp("2025-09-15T20:00:00Z")


def test_extract_revalidation_features_uses_completed_entry_and_open_prices():
    features = extract_revalidation_features(
        _bars(),
        entry_timestamp="2025-09-15T18:30:00Z",  # 14:30 ET bar start -> 15:30 close
        exit_timestamp="2025-09-16T14:30:00Z",   # 10:30 ET bar start -> 11:30 close
    )
    assert features is not None
    assert abs(features["entry_price_iex"] - 100.0) < 1e-12
    assert abs(features["prev_close_price_iex"] - 101.0) < 1e-12
    assert abs(features["open_0_price_iex"] - 99.0) < 1e-12
    assert abs(features["open_5_price_iex"] - 98.5) < 1e-12
    assert abs(features["open_15_price_iex"] - 98.0) < 1e-12
    assert abs(features["fixed4_exit_price_iex"] - 97.0) < 1e-12
    assert features["position_return_prev_close"] > 0
    assert features["position_return_open"] < 0
    assert features["open_momentum_5m"] < 0


def test_open_flip_and_confirmation_policies_trigger_without_lookahead():
    features = extract_revalidation_features(
        _bars(),
        entry_timestamp="2025-09-15T18:30:00Z",
        exit_timestamp="2025-09-16T14:30:00Z",
    )
    assert features is not None
    policies = {p.name: p for p in POLICIES}
    assert policy_trigger(policies["OPEN_FLIP_0M"], features)
    assert policy_trigger(policies["OPEN_FLIP_5M_CONFIRM"], features)
    assert policy_trigger(policies["OPEN_NEG_15M_CONFIRM"], features)


def test_giveback_policy_requires_large_prior_profit():
    features = dict(
        position_return_prev_close=0.006,
        position_return_open=0.001,
        position_return_5m=-0.002,
        position_return_15m=-0.003,
        overnight_gap_return=-0.005,
        open_momentum_5m=-0.003,
        open_momentum_15m=-0.004,
        giveback_prev_close_to_5m=0.008,
    )
    policies = {p.name: p for p in POLICIES}
    assert policy_trigger(policies["OPEN_GIVEBACK_5M"], features)

    features["position_return_prev_close"] = 0.004
    assert not policy_trigger(policies["OPEN_GIVEBACK_5M"], features)
