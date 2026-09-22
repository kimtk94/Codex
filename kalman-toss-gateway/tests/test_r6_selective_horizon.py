from __future__ import annotations

import numpy as np
import pandas as pd

from research.r6_selective_horizon import mdd, metrics, sim


def test_mdd_positive_path_is_zero():
    assert mdd([0.01, 0.02, 0.03]) == 0.0


def test_fixed_non_overlap():
    frame = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=8, freq="h", tz="UTC"),
        "expected_seq": range(8),
        "fold": ["F"] * 8,
        "symbol": ["X"] * 8,
        "net_ret_4b": [0.01] * 8,
    })
    out = sim(frame, h=4)
    assert out["expected_seq"].tolist() == [0, 4]


def test_metrics_profit_factor_and_drawdown():
    frame = pd.DataFrame({"net_return": [0.02, -0.01, 0.03, -0.005]})
    out = metrics(frame)
    assert out["trades"] == 4
    assert np.isclose(out["win_rate"], 0.5)
    assert out["profit_factor"] > 1
    assert out["max_drawdown"] <= 0
