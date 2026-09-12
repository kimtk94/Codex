from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.quant_stack.portfolio_targets import (
    build_rolling_portfolio_targets,
    portfolio_equity_from_targets,
)


def _returns() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    idx = pd.date_range("2024-01-01", periods=500, freq="D", tz="UTC")
    common = rng.normal(0.0003, 0.007, size=len(idx))
    return pd.DataFrame(
        {
            "US": common + rng.normal(0.0002, 0.004, len(idx)),
            "KR": common * 0.6 + rng.normal(0.0001, 0.006, len(idx)),
            "BTC": common * 1.5 + rng.normal(0.0005, 0.015, len(idx)),
        },
        index=idx,
    )


def test_hrp_targets_are_long_only_and_sum_to_one():
    returns = _returns()
    targets = build_rolling_portfolio_targets(
        returns,
        method="hrp",
        lookback_days=180,
        min_observations=90,
        rebalance_frequency="M",
    )
    assert not targets.empty
    assert set(targets["source"]) == {"PYPFOPT"}

    for _, group in targets.groupby("effective_ts"):
        assert (group["target_weight"] >= 0).all()
        assert abs(float(group["target_weight"].sum()) - 1.0) < 1e-8
        assert (group["decision_ts"] < group["effective_ts"]).all()


def test_portfolio_equity_uses_effective_weights_only():
    returns = _returns()
    targets = build_rolling_portfolio_targets(
        returns,
        method="hrp",
        lookback_days=120,
        min_observations=60,
        rebalance_frequency="M",
    )
    equity = portfolio_equity_from_targets(returns, targets)
    assert not equity.empty
    assert equity["ts"].min() >= targets["effective_ts"].min()
    assert (equity["equity"] > 0).all()
