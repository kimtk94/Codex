from __future__ import annotations

import pandas as pd
import pytest

from research.shadow_bakeoff.runner import (
    _assert_research_only_v34,
    _latest_target,
    _rank_forward,
    _stitch_returns,
)


def test_v34_invariants_require_research_only_flags() -> None:
    payload = {
        "status": "COMPLETE",
        "selected_gate": "risk_cap_110",
        "live_execution": False,
        "toss_execution": False,
        "neon_write": False,
    }
    _assert_research_only_v34(payload)

    broken = dict(payload)
    broken["live_execution"] = True
    with pytest.raises(RuntimeError):
        _assert_research_only_v34(broken)


def test_stitch_returns_uses_forward_only_after_seed() -> None:
    idx = pd.date_range("2026-09-08", periods=5, freq="D", tz="UTC")
    hist = pd.DataFrame(
        {
            "US": [0.01, 0.02, 0.03, 0.04, 0.05],
            "KR": [0.01, 0.02, 0.03, 0.04, 0.05],
            "BTC": [0.01, 0.02, 0.03, 0.04, 0.05],
        },
        index=idx,
    )
    fwd_idx = pd.date_range("2026-09-11", periods=3, freq="D", tz="UTC")
    fwd = {
        market: pd.Series([0.99, 0.10, 0.20], index=fwd_idx, name=market)
        for market in ("US", "KR", "BTC")
    }

    out = _stitch_returns(
        historical=hist,
        forward=fwd,
        seed_end=pd.Timestamp("2026-09-11", tz="UTC"),
    )
    assert out.loc[pd.Timestamp("2026-09-11", tz="UTC"), "US"] == 0.04
    assert out.loc[pd.Timestamp("2026-09-12", tz="UTC"), "US"] == 0.10
    assert out.loc[pd.Timestamp("2026-09-13", tz="UTC"), "US"] == 0.20


def test_latest_target_uses_latest_effective_date() -> None:
    targets = pd.DataFrame(
        [
            {"effective_ts": "2026-08-01", "sleeve": "US", "target_weight": 0.5},
            {"effective_ts": "2026-08-01", "sleeve": "KR", "target_weight": 0.3},
            {"effective_ts": "2026-08-01", "sleeve": "BTC", "target_weight": 0.2},
            {"effective_ts": "2026-09-01", "sleeve": "US", "target_weight": 0.2},
            {"effective_ts": "2026-09-01", "sleeve": "KR", "target_weight": 0.4},
            {"effective_ts": "2026-09-01", "sleeve": "BTC", "target_weight": 0.4},
        ]
    )
    latest = _latest_target(targets)
    assert latest == {"US": 0.2, "KR": 0.4, "BTC": 0.4}


def test_rank_forward_waits_when_no_post_seed_metrics() -> None:
    ts = pd.date_range("2026-09-10", periods=2, freq="D", tz="UTC")
    equity = pd.DataFrame(
        {
            "ts": ts,
            "net_portfolio_return": [0.0, 0.0],
            "gross_portfolio_return": [0.0, 0.0],
            "rebalance_cost_rate": [0.0, 0.0],
            "half_l1_turnover": [0.0, 0.0],
            "traded_notional_ratio": [0.0, 0.0],
            "is_rebalance": [False, False],
            "equity": [1_000_000.0, 1_000_000.0],
        }
    )
    results = {
        name: {"latest_target": {"US": 1 / 3, "KR": 1 / 3, "BTC": 1 / 3}, "equity": equity}
        for name in ("A_EQUAL_WEIGHT", "B_STATIC_MAX_SHARPE", "C_RISK_CAP_110")
    }
    rows, status = _rank_forward(
        results,
        seed_end=pd.Timestamp("2026-09-11", tz="UTC"),
    )
    assert status == "WAITING_FOR_FORWARD_DATA"
    assert all(row["status"] == "WAITING_FOR_FORWARD_DATA" for row in rows)


def test_signal_history_duplicate_timestamp_keeps_latest(tmp_path) -> None:
    from research.shadow_bakeoff.forward_scorer import append_signal_history

    path = tmp_path / "signals.parquet"
    base = {
        "market": "US",
        "symbol": "SPY",
        "as_of": "2026-09-11T00:00:00+00:00",
        "entry_allowed": True,
        "model_family": "V2_NESTED_FINAL_REFIT",
    }
    first = {
        **base,
        "run_id": "us-v2-forward-old",
        "signal": "BUY",
        "parameter_hash": "old",
    }
    second = {
        **base,
        "run_id": "us-v2-forward-new",
        "signal": "SELL",
        "entry_allowed": False,
        "parameter_hash": "new",
    }

    append_signal_history(path, first)
    out = append_signal_history(path, second)

    assert len(out) == 1
    assert out.iloc[0]["run_id"] == "us-v2-forward-new"
    assert out.iloc[0]["signal"] == "SELL"


def test_forward_row_quality_gate_rejects_training_or_missing() -> None:
    from research.shadow_bakeoff.forward_scorer import _validate_forward_row

    same = pd.DataFrame(
        [{"as_of": pd.Timestamp("2026-09-11", tz="UTC"), "a": 1.0, "b": 2.0}]
    )
    with pytest.raises(RuntimeError):
        _validate_forward_row(
            same,
            trained_through=pd.Timestamp("2026-09-11", tz="UTC"),
            features=["a", "b"],
        )

    missing = pd.DataFrame(
        [{"as_of": pd.Timestamp("2026-09-12", tz="UTC"), "a": None, "b": 2.0}]
    )
    with pytest.raises(RuntimeError):
        _validate_forward_row(
            missing,
            trained_through=pd.Timestamp("2026-09-11", tz="UTC"),
            features=["a", "b"],
        )
