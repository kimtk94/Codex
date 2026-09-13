from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.quant_stack.riskfolio_benchmarks import (
    RISKFOLIO_METHODS,
    build_riskfolio_targets,
    riskfolio_weights,
)


def _returns() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    idx = pd.date_range("2024-01-01", periods=320, freq="D", tz="UTC")
    common = rng.normal(0.0002, 0.006, len(idx))
    return pd.DataFrame(
        {
            "US": common + rng.normal(0.0002, 0.004, len(idx)),
            "KR": common * 0.6 + rng.normal(0.0001, 0.005, len(idx)),
            "BTC": common * 1.3 + rng.normal(0.0004, 0.012, len(idx)),
        },
        index=idx,
    )


def test_all_riskfolio_methods_return_long_only_weights():
    returns = _returns().iloc[:180]
    for method in RISKFOLIO_METHODS:
        weights = riskfolio_weights(returns, method=method)
        assert list(weights.index) == list(returns.columns)
        assert (weights >= -1e-10).all()
        assert abs(float(weights.sum()) - 1.0) < 1e-7


def test_riskfolio_targets_are_prospective_only():
    returns = _returns()
    targets = build_riskfolio_targets(
        returns,
        method="cvar_minrisk",
        lookback_days=120,
        min_observations=60,
        rebalance_frequency="M",
    )
    assert not targets.empty
    assert set(targets["source"]) == {"RISKFOLIO"}
    assert (targets["decision_ts"] < targets["effective_ts"]).all()
    for _, group in targets.groupby("effective_ts"):
        assert abs(float(group["target_weight"].sum()) - 1.0) < 1e-7



def test_riskfolio_handles_flat_sleeve_without_failure():
    returns = _returns().iloc[:180].copy()
    returns["US"] = 0.0

    for method in RISKFOLIO_METHODS:
        weights = riskfolio_weights(returns, method=method)
        assert np.isfinite(weights.to_numpy(dtype=float)).all()
        assert (weights >= -1e-10).all()
        assert abs(float(weights.sum()) - 1.0) < 1e-7
        assert float(weights["US"]) == 0.0


def test_riskfolio_handles_perfect_collinearity_without_failure():
    idx = pd.date_range("2024-01-01", periods=180, freq="D", tz="UTC")
    base = np.sin(np.arange(len(idx)) / 9.0) * 0.01
    returns = pd.DataFrame(
        {
            "US": base,
            "KR": base * 2.0,
            "BTC": base * -0.5,
        },
        index=idx,
    )

    for method in RISKFOLIO_METHODS:
        weights = riskfolio_weights(returns, method=method)
        assert np.isfinite(weights.to_numpy(dtype=float)).all()
        assert (weights >= -1e-10).all()
        assert abs(float(weights.sum()) - 1.0) < 1e-7


def test_riskfolio_all_flat_uses_deterministic_equal_weight_fallback():
    idx = pd.date_range("2024-01-01", periods=180, freq="D", tz="UTC")
    returns = pd.DataFrame(
        0.0,
        index=idx,
        columns=["US", "KR", "BTC"],
    )

    for method in RISKFOLIO_METHODS:
        weights = riskfolio_weights(returns, method=method)
        assert weights.attrs["optimization_status"] == "FALLBACK"
        assert np.isfinite(weights.to_numpy(dtype=float)).all()
        assert abs(float(weights.sum()) - 1.0) < 1e-7
        for sleeve in ("US", "KR", "BTC"):
            assert abs(float(weights[sleeve]) - (1.0 / 3.0)) < 1e-7
