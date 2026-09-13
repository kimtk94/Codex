from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.quant_stack.historical_v3_return_regime import (
    _fit_return_model,
    _predict_return,
    _validation_utility,
    build_signals,
    select_return_features,
)


def _spec() -> dict:
    return {
        "minimum_feature_coverage": 0.80,
        "maximum_features": 24,
        "excluded_feature_suffixes": ["__coverage"],
        "near_zero_variance_threshold": 1e-12,
        "max_pairwise_feature_correlation": 0.90,
        "stability_blocks": 4,
    }


def _frame(rows: int = 800) -> pd.DataFrame:
    rng = np.random.default_rng(123)
    signal = rng.normal(size=rows)
    target_return = 0.01 * signal + rng.normal(scale=0.02, size=rows)
    frame = pd.DataFrame(
        {
            "as_of": pd.date_range("2019-01-01", periods=rows, freq="B", tz="UTC"),
            "anchor_close": 100.0 + np.cumsum(rng.normal(scale=0.5, size=rows)),
            "target_forward_return": target_return,
            "target_label": (target_return > 0).astype(int),
            "signal": signal,
            "signal_copy": signal * 1.000001,
            "junk__coverage": np.linspace(0.8, 1.0, rows),
            "constant": 1.0,
        }
    )
    for i in range(50):
        frame[f"noise_{i:02d}"] = rng.normal(size=rows)
    return frame


def test_return_selector_drops_coverage_constant_and_redundant_copy():
    selected, diagnostics = select_return_features(_frame(), spec=_spec())
    assert 5 <= len(selected) <= 24
    assert "junk__coverage" not in selected
    assert "constant" not in selected
    assert not ({"signal", "signal_copy"} <= set(selected))

    diag = {row["feature"]: row for row in diagnostics}
    assert "signal" in diag or "signal_copy" in diag


def test_market_specific_return_models_produce_finite_predictions():
    frame = _frame(700)
    train = frame.iloc[:600]
    test = frame.iloc[600:]
    features, _ = select_return_features(train, spec=_spec())
    candidates = [
        ("RIDGE", {"alpha": 10.0}),
        ("ELASTIC_NET", {"alpha": 0.001, "l1_ratio": 0.25}),
        (
            "HIST_GRADIENT_BOOSTING",
            {
                "learning_rate": 0.03,
                "max_leaf_nodes": 7,
                "l2_regularization": 1.0,
            },
        ),
    ]
    for model_type, params in candidates:
        bundle = _fit_return_model(
            train,
            features,
            model_type=model_type,
            params=params,
        )
        pred = _predict_return(test, features, bundle)
        assert len(pred) == len(test)
        assert np.isfinite(pred).all()


def test_validation_utility_penalizes_turnover():
    actual = np.array([0.02, 0.01, -0.01, 0.015, 0.0, 0.02])
    stable = np.array([1, 1, 0, 0, 1, 1], dtype=bool)
    choppy = np.array([1, 0, 1, 0, 1, 0], dtype=bool)
    a = _validation_utility(
        actual,
        stable,
        horizon=5,
        turnover_penalty=1.0,
        return_proxy_weight=0.0,
    )
    b = _validation_utility(
        actual,
        choppy,
        horizon=5,
        turnover_penalty=1.0,
        return_proxy_weight=0.0,
    )
    assert a["turnover"] < b["turnover"]


def test_build_signals_uses_hysteresis():
    frame = pd.DataFrame(
        {
            "run_id": ["r1", "r2", "r3"],
            "as_of": pd.date_range("2025-01-01", periods=3, freq="D", tz="UTC"),
            "fold_id": [0, 0, 0],
            "predicted_return": [0.03, 0.01, -0.01],
            "regime_probability": [0.70, 0.52, 0.40],
            "entry_return_threshold": [0.02, 0.02, 0.02],
            "regime_probability_gate": [0.60, 0.60, 0.60],
        }
    )
    signals = build_signals(frame, symbol="TEST")
    assert signals["signal"].tolist() == ["BUY", "HOLD", "SELL"]
