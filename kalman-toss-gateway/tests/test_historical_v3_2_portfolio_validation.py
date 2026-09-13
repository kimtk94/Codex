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

    # The sleeves drift before the second rebalance, so turnover must be
    # measured against drifted weights rather than stale 50/50 targets.
    second = equity.iloc[1]
    expected_l1 = (
        abs(0.25 - second["end_weight_US"])
        + abs(0.75 - second["end_weight_BTC"])
    )
    assert np.isclose(third["traded_notional_ratio"], expected_l1)
    assert np.isclose(third["half_l1_turnover"], 0.5 * expected_l1)
    assert np.isclose(
        third["rebalance_cost_rate"],
        expected_l1 * 0.001,
    )


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


def test_weights_drift_between_monthly_targets() -> None:
    equity = portfolio_equity_with_costs(
        _returns(),
        _targets(),
        initial_equity=1_000_000.0,
        rebalance_cost_bps=0.0,
    )
    first = equity.iloc[0]
    second = equity.iloc[1]

    assert first["end_weight_US"] > 0.5
    expected_day2 = second["end_weight_BTC"]  # post-return weight, sanity only
    assert expected_day2 > 0.5

    # Day 2 starts from the drifted day-1 weights, not a hidden daily 50/50 reset.
    day1_us_end = 500_000.0 * 1.01
    day1_btc_end = 500_000.0
    btc_weight_before_day2 = day1_btc_end / (day1_us_end + day1_btc_end)
    expected_gross_day2 = btc_weight_before_day2 * 0.02
    assert np.isclose(
        second["gross_portfolio_return"],
        expected_gross_day2,
    )
    assert not np.isclose(second["gross_portfolio_return"], 0.01)


def test_vectorbt_order_price_array_is_writable_and_uses_close_for_max_hold() -> None:
    from research.quant_stack.historical_v3_2_portfolio_validation import (
        _stateful_vectorbt_orders,
    )

    bars = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0],
            "close": [100.5, 101.5, 102.5],
        }
    )
    event_map = {0: ["BUY"]}
    entries, exits, execution_price, reasons = _stateful_vectorbt_orders(
        event_map,
        bars,
        max_hold_bars=2,
    )

    assert bool(entries[0])
    assert bool(exits[1])
    assert np.isclose(execution_price[0], 100.0)
    assert np.isclose(execution_price[1], 101.5)
    assert reasons[1] == "MAX_HOLD_CLOSE"
