from __future__ import annotations

import numpy as np
import pandas as pd

from research.quant_stack.historical_v3_4_allocator_regime_gate import (
    _blend_alpha_for_risk_cap,
    _compare_selected_to_benchmarks,
    _portfolio_vol,
    _rank_dev,
    build_gate_targets,
)


def test_risk_cap_blend_respects_predicted_vol_budget() -> None:
    columns = ["US", "KR", "BTC"]
    cov = pd.DataFrame(
        np.diag([0.04, 0.09, 0.25]),
        index=columns,
        columns=columns,
    )
    ew = pd.Series([1 / 3, 1 / 3, 1 / 3], index=columns)
    ms = pd.Series([0.0, 0.0, 1.0], index=columns)

    alpha, ew_vol, ms_vol, blend_vol = _blend_alpha_for_risk_cap(
        ew,
        ms,
        cov,
        risk_cap_ratio=1.20,
        fallback=False,
    )

    assert 0.0 < alpha < 1.0
    assert ms_vol > 1.20 * ew_vol
    assert blend_vol <= 1.20 * ew_vol + 1e-10


def test_fallback_forces_equal_weight_alpha_zero() -> None:
    columns = ["US", "KR", "BTC"]
    cov = pd.DataFrame(
        np.eye(3) * 0.04,
        index=columns,
        columns=columns,
    )
    ew = pd.Series([1 / 3, 1 / 3, 1 / 3], index=columns)
    ms = pd.Series([0.8, 0.1, 0.1], index=columns)

    alpha, _, _, blend_vol = _blend_alpha_for_risk_cap(
        ew,
        ms,
        cov,
        risk_cap_ratio=1.50,
        fallback=True,
    )
    assert alpha == 0.0
    assert np.isclose(blend_vol, _portfolio_vol(ew, cov))


def _targets(
    dates: pd.DatetimeIndex,
    weights: dict[str, float],
    *,
    method: str,
    status: str = "READY",
) -> pd.DataFrame:
    rows = []
    for effective in dates:
        lookback_end = effective - pd.Timedelta(days=1)
        lookback_start = lookback_end - pd.Timedelta(days=179)
        for sleeve, weight in weights.items():
            rows.append(
                {
                    "decision_ts": lookback_end,
                    "effective_ts": effective,
                    "sleeve": sleeve,
                    "target_weight": weight,
                    "method": method,
                    "lookback_start": lookback_start,
                    "lookback_end": lookback_end,
                    "observations": 180,
                    "source": "TEST",
                    "optimization_status": status,
                    "fallback_reason": (
                        "test fallback" if status != "READY" else None
                    ),
                    "annualization_days": 365,
                }
            )
    return pd.DataFrame(rows)


def test_build_gate_targets_weights_sum_to_one() -> None:
    idx = pd.date_range(
        "2024-01-01",
        periods=500,
        freq="D",
        tz="UTC",
    )
    t = np.arange(len(idx), dtype=float)
    returns = pd.DataFrame(
        {
            "US": 0.0004 + 0.003 * np.sin(t / 8),
            "KR": 0.0003 + 0.004 * np.cos(t / 10),
            "BTC": 0.0007 + 0.009 * np.sin(t / 6),
        },
        index=idx,
    )
    dates = pd.DatetimeIndex(
        [
            pd.Timestamp("2024-10-01", tz="UTC"),
            pd.Timestamp("2024-11-01", tz="UTC"),
        ]
    )
    ew = _targets(
        dates,
        {"US": 1 / 3, "KR": 1 / 3, "BTC": 1 / 3},
        method="equal_weight",
    )
    ms = _targets(
        dates,
        {"US": 0.1, "KR": 0.1, "BTC": 0.8},
        method="max_sharpe",
    )

    targets, audit = build_gate_targets(
        returns,
        ew,
        ms,
        gate_name="risk_cap_120",
    )

    sums = targets.groupby("effective_ts")["target_weight"].sum()
    assert np.allclose(sums.to_numpy(dtype=float), 1.0, atol=1e-8)
    assert (audit["alpha_max_sharpe"] >= 0.0).all()
    assert (audit["alpha_max_sharpe"] <= 1.0).all()
    assert (audit["blend_to_equal_vol_ratio"] <= 1.20 + 1e-8).all()


def test_dev_ranking_excludes_static_benchmarks() -> None:
    frame = pd.DataFrame(
        [
            {
                "gate_name": "static_equal_weight",
                "sharpe": 2.0,
                "max_drawdown": -0.1,
                "total_return": 1.0,
                "traded_notional_ratio_total": 1.0,
            },
            {
                "gate_name": "static_max_sharpe",
                "sharpe": 1.9,
                "max_drawdown": -0.1,
                "total_return": 1.1,
                "traded_notional_ratio_total": 2.0,
            },
            {
                "gate_name": "risk_cap_120",
                "sharpe": 1.2,
                "max_drawdown": -0.2,
                "total_return": 0.8,
                "traded_notional_ratio_total": 1.5,
            },
            {
                "gate_name": "risk_cap_130",
                "sharpe": 1.3,
                "max_drawdown": -0.2,
                "total_return": 0.9,
                "traded_notional_ratio_total": 1.8,
            },
        ]
    )

    ranked = _rank_dev(frame)
    assert ranked.iloc[0]["gate_name"] == "risk_cap_130"
    assert not ranked["gate_name"].str.startswith("static_").any()


def test_recent_comparison_requires_risk_adjusted_improvement() -> None:
    recent = pd.DataFrame(
        [
            {
                "gate_name": "static_equal_weight",
                "sharpe": 1.40,
                "total_return": 0.90,
                "max_drawdown": -0.19,
            },
            {
                "gate_name": "static_max_sharpe",
                "sharpe": 1.10,
                "total_return": 1.05,
                "max_drawdown": -0.30,
            },
            {
                "gate_name": "risk_cap_120",
                "sharpe": 1.36,
                "total_return": 0.95,
                "max_drawdown": -0.22,
            },
        ]
    )

    result = _compare_selected_to_benchmarks(
        recent,
        "risk_cap_120",
    )
    assert result["sharpe_pass"]
    assert result["drawdown_pass"]
    assert result["return_pass"]
    assert result["recent_gate_pass"]
