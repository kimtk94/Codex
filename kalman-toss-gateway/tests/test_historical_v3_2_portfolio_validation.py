from __future__ import annotations

import numpy as np
import pandas as pd

from research.quant_stack.historical_v3_2_portfolio_validation import (
    corrected_portfolio_metrics,
    portfolio_equity_with_costs,
    select_champions,
)


def _returns() -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=4, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "US": [0.01, 0.00, 0.01, 0.00],
            "BTC": [0.00, 0.02, 0.00, 0.02],
        },
        index=idx,
    )


def _targets() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "effective_ts": pd.Timestamp("2026-01-01", tz="UTC"),
                "sleeve": "US",
                "target_weight": 0.5,
            },
            {
                "effective_ts": pd.Timestamp("2026-01-01", tz="UTC"),
                "sleeve": "BTC",
                "target_weight": 0.5,
            },
            {
                "effective_ts": pd.Timestamp("2026-01-03", tz="UTC"),
                "sleeve": "US",
                "target_weight": 0.25,
            },
            {
                "effective_ts": pd.Timestamp("2026-01-03", tz="UTC"),
                "sleeve": "BTC",
                "target_weight": 0.75,
            },
        ]
    )


def test_corrected_metrics_keep_true_initial_equity() -> None:
    equity = portfolio_equity_with_costs(
        _returns(),
        _targets(),
        initial_equity=1_000_000.0,
        rebalance_cost_bps=0.0,
    )
    metrics = corrected_portfolio_metrics(
        equity,
        initial_equity=1_000_000.0,
        annualization_days=365,
    )
    assert metrics["initial_equity"] == 1_000_000.0
    assert np.isclose(
        metrics["total_return"],
        metrics["ending_equity"] / 1_000_000.0 - 1.0,
    )


def test_rebalance_cost_uses_traded_notional_l1() -> None:
    equity = portfolio_equity_with_costs(
        _returns(),
        _targets(),
        initial_equity=1_000_000.0,
        rebalance_cost_bps=10.0,
        charge_initial_allocation=True,
    )
    first = equity.iloc[0]
    third = equity.iloc[2]

    # Initial allocation from cash to fully invested sleeves trades 100% notional.
    assert np.isclose(first["traded_notional_ratio"], 1.0)
    assert np.isclose(first["rebalance_cost_rate"], 0.001)

    # 50/50 -> 25/75: abs(delta) sums to 50%.
    assert np.isclose(third["traded_notional_ratio"], 0.5)
    assert np.isclose(third["half_l1_turnover"], 0.25)
    assert np.isclose(third["rebalance_cost_rate"], 0.0005)


def test_balanced_champion_prefers_lower_vol_inside_95pct_sharpe_band() -> None:
    comparison = pd.DataFrame(
        [
            {
                "status": "READY",
                "champion_eligible": True,
                "method": "equal_weight",
                "sharpe": 0.62,
                "cagr": 0.065,
                "max_drawdown": -0.28,
                "annualized_volatility": 0.112,
                "historical_cvar_95": 0.0145,
            },
            {
                "status": "READY",
                "champion_eligible": True,
                "method": "hrp",
                "sharpe": 0.603,
                "cagr": 0.050,
                "max_drawdown": -0.279,
                "annualized_volatility": 0.087,
                "historical_cvar_95": 0.0115,
            },
            {
                "status": "READY",
                "champion_eligible": True,
                "method": "cvar_minrisk",
                "sharpe": 0.56,
                "cagr": 0.047,
                "max_drawdown": -0.27,
                "annualized_volatility": 0.088,
                "historical_cvar_95": 0.0118,
            },
        ]
    )
    champions = select_champions(comparison)
    assert champions["overall_champion"]["method"] == "equal_weight"
    assert champions["balanced_champion"]["method"] == "hrp"
    assert champions["defensive_champion"]["method"] == "cvar_minrisk"
