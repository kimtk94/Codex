from __future__ import annotations

import numpy as np
import pandas as pd

from research.quant_stack.historical_v3_3_robustness_hybrid import (
    SOURCE_SETS,
    _rebase_window,
    _worst_126d_window,
    choose_recommendation,
    summarize_robustness,
)


def test_hybrid_source_map_is_us_v2_kr_v3_btc_v2() -> None:
    assert SOURCE_SETS["HYBRID_USV2_KRV3_BTCV2"] == {
        "US": "V2",
        "KR": "V3",
        "BTC": "V2",
    }


def test_rebase_window_starts_from_true_initial_equity() -> None:
    idx = pd.date_range("2026-01-01", periods=4, freq="D", tz="UTC")
    equity = pd.DataFrame(
        {
            "ts": idx,
            "net_portfolio_return": [0.01, -0.02, 0.03, 0.00],
            "gross_portfolio_return": [0.01, -0.02, 0.03, 0.00],
            "rebalance_cost_rate": [0.0, 0.0, 0.0, 0.0],
            "half_l1_turnover": [0.0, 0.0, 0.0, 0.0],
            "traded_notional_ratio": [0.0, 0.0, 0.0, 0.0],
            "is_rebalance": [False, False, False, False],
            "equity": [1.0, 1.0, 1.0, 1.0],
        }
    )

    sliced = _rebase_window(
        equity,
        start=idx[1],
        end=idx[3],
    )
    expected = 1_000_000.0 * (1.0 - 0.02) * (1.0 + 0.03)
    assert np.isclose(float(sliced["equity"].iloc[-1]), expected)


def test_worst_126d_window_finds_negative_block() -> None:
    idx = pd.date_range("2020-01-01", periods=300, freq="D", tz="UTC")
    returns = pd.Series(0.001, index=idx)
    returns.iloc[100:226] = -0.01

    start, end = _worst_126d_window(returns)
    assert start == idx[100]
    assert end == idx[225]


def _pairwise_fixture() -> pd.DataFrame:
    rows = []
    periods = ("FULL_COMMON", "RECENT", "WORST_126D", "RISK_OFF_2022")
    for source in SOURCE_SETS:
        for i in range(12):
            for period in periods:
                rows.append(
                    {
                        "source_set": source,
                        "period": period,
                        "max_sharpe_sharpe_win": True,
                        "max_sharpe_return_win": True,
                        "max_sharpe_mdd_win": i < 8,
                        "fallback_ratio_max_sharpe": 0.10,
                        "sharpe_max_sharpe": 0.70 - i * 0.005,
                        "total_return_max_sharpe": 0.50 - i * 0.005,
                        "max_drawdown_max_sharpe": -0.20 - i * 0.001,
                    }
                )
    return pd.DataFrame(rows)


def test_robustness_gate_marks_consistent_max_sharpe_as_robust() -> None:
    result = summarize_robustness(_pairwise_fixture())
    assert set(result["robustness_status"]) == {"ROBUST"}
    assert (result["full_sharpe_win_rate"] == 1.0).all()
    assert (result["median_max_sharpe_fallback_ratio"] == 0.10).all()


def test_recommendation_prefers_best_robust_source() -> None:
    robustness = pd.DataFrame(
        [
            {
                "source_set": "ALL_V2",
                "robustness_status": "ROBUST",
                "median_max_sharpe_sharpe": 0.60,
                "p10_max_sharpe_sharpe": 0.50,
            },
            {
                "source_set": "ALL_V3",
                "robustness_status": "MIXED",
                "median_max_sharpe_sharpe": 0.80,
                "p10_max_sharpe_sharpe": 0.70,
            },
            {
                "source_set": "HYBRID_USV2_KRV3_BTCV2",
                "robustness_status": "ROBUST",
                "median_max_sharpe_sharpe": 0.70,
                "p10_max_sharpe_sharpe": 0.60,
            },
        ]
    )
    base = pd.DataFrame(
        [
            {
                "source_set": "ALL_V2",
                "method": "max_sharpe",
                "sharpe": 0.62,
                "total_return": 0.50,
                "max_drawdown": -0.25,
                "fallback_ratio": 0.10,
            },
            {
                "source_set": "ALL_V3",
                "method": "max_sharpe",
                "sharpe": 0.80,
                "total_return": 0.70,
                "max_drawdown": -0.20,
                "fallback_ratio": 0.10,
            },
            {
                "source_set": "HYBRID_USV2_KRV3_BTCV2",
                "method": "max_sharpe",
                "sharpe": 0.72,
                "total_return": 0.60,
                "max_drawdown": -0.22,
                "fallback_ratio": 0.12,
            },
        ]
    )

    rec = choose_recommendation(
        robustness=robustness,
        base_ranking=base,
    )
    assert rec["recommended_source_set"] == "HYBRID_USV2_KRV3_BTCV2"
    assert rec["recommended_allocator"] == "max_sharpe"
    assert rec["shadow_gate"] == "PASS"
