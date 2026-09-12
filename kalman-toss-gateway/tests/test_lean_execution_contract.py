from __future__ import annotations

import pathlib
import sys

import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.quant_stack.contracts import Mode
from research.quant_stack.lean_execution import (
    ExecutionPolicy,
    ExecutionState,
    PortfolioTargetContract,
    apply_execution_fills,
    cash_constrain_shadow_fills,
    risk_adjust_portfolio_targets,
    run_shadow_rebalance,
)
from research.quant_stack.lean_execution_runner import execution_price_points


def _target(symbol: str, weight: float) -> PortfolioTargetContract:
    return PortfolioTargetContract.build(
        run_id="run-1",
        strategy_version="portfolio-hrp",
        symbol=symbol,
        decision_ts="2026-09-10T00:00:00+00:00",
        effective_ts="2026-09-11T00:00:00+00:00",
        target_weight=weight,
        source="TEST",
    )


def test_portfolio_risk_adjusts_long_only_symbol_and_gross_limits():
    policy = ExecutionPolicy(
        max_symbol_weight=0.60,
        max_gross_weight=1.00,
    )
    adjusted = risk_adjust_portfolio_targets(
        [_target("US", 0.90), _target("KR", -0.20), _target("BTC", 0.60)],
        policy,
    )
    weights = {row.symbol: row.adjusted_weight for row in adjusted}
    assert weights["KR"] == 0.0
    assert abs(weights["US"] - 0.5) < 1e-12
    assert abs(weights["BTC"] - 0.5) < 1e-12
    assert abs(sum(abs(x) for x in weights.values()) - 1.0) < 1e-12


def test_shadow_contract_produces_deterministic_intent_order_fill_chain():
    policy = ExecutionPolicy(
        max_symbol_weight=0.75,
        max_gross_weight=1.0,
        min_order_notional=0.01,
        max_single_order_fraction=0.60,
        max_total_turnover_fraction=2.0,
        slippage_bps=0.0,
        commission_bps=0.0,
    )
    targets = [_target("US", 0.5), _target("KR", 0.5)]
    state = ExecutionState(cash=10_000.0, positions={})
    prices = {"US": 100.0, "KR": 50.0}

    first = run_shadow_rebalance(
        targets,
        state=state,
        planning_prices=prices,
        fill_prices=prices,
        fill_ts="2026-09-11T00:00:00+00:00",
        policy=policy,
        mode=Mode.SHADOW,
    )
    second = run_shadow_rebalance(
        targets,
        state=state,
        planning_prices=prices,
        fill_prices=prices,
        fill_ts="2026-09-11T00:00:00+00:00",
        policy=policy,
        mode=Mode.SHADOW,
    )

    assert len(first.gated_intents) == 2
    assert all(x.status == "APPROVED" for x in first.gated_intents)
    assert len(first.broker_orders) == 2
    assert len(first.fills) == 2
    assert first.state.cash == 0.0
    assert abs(first.state.positions["US"] - 50.0) < 1e-12
    assert abs(first.state.positions["KR"] - 100.0) < 1e-12
    assert [x.intent.intent_id for x in first.gated_intents] == [
        x.intent.intent_id for x in second.gated_intents
    ]
    assert [x.broker_order_id for x in first.broker_orders] == [
        x.broker_order_id for x in second.broker_orders
    ]


def test_live_mode_is_blocked_before_broker_order_creation():
    policy = ExecutionPolicy(
        min_order_notional=0.01,
        allow_live_execution=False,
    )
    cycle = run_shadow_rebalance(
        [_target("US", 0.5), _target("KR", 0.5)],
        state=ExecutionState(cash=10_000.0, positions={}),
        planning_prices={"US": 100.0, "KR": 50.0},
        fill_prices={"US": 101.0, "KR": 51.0},
        fill_ts="2026-09-11T00:00:00+00:00",
        policy=policy,
        mode=Mode.LIVE,
    )
    assert cycle.gated_intents
    assert all(x.status == "REJECTED" for x in cycle.gated_intents)
    assert all(
        x.risk_reason == "LIVE_EXECUTION_DISABLED"
        for x in cycle.gated_intents
    )
    assert cycle.broker_orders == []
    assert cycle.fills == []


def test_risk_reducing_sell_bypasses_entry_notional_cap():
    policy = ExecutionPolicy(
        min_order_notional=0.01,
        max_single_order_fraction=0.05,
        max_total_turnover_fraction=0.05,
    )
    cycle = run_shadow_rebalance(
        [_target("US", 0.0)],
        state=ExecutionState(cash=0.0, positions={"US": 100.0}),
        planning_prices={"US": 100.0},
        fill_prices={"US": 100.0},
        fill_ts="2026-09-11T00:00:00+00:00",
        policy=policy,
        mode=Mode.SHADOW,
    )
    assert len(cycle.gated_intents) == 1
    assert cycle.gated_intents[0].status == "APPROVED"
    assert cycle.gated_intents[0].risk_reason == "RISK_REDUCING_EXIT"
    assert cycle.state.positions == {}
    assert cycle.state.cash == 10_000.0


def test_shadow_fill_cannot_oversell():
    from research.quant_stack.lean_execution import ExecutionFill

    fill = ExecutionFill(
        fill_id="fill-test",
        broker_order_id="bo-test",
        intent_id="oi-test",
        symbol="US",
        side="SELL",
        quantity=2.0,
        fill_price=100.0,
        fee=0.0,
        fill_ts="2026-09-11T00:00:00+00:00",
        broker="SHADOW",
        status="FILLED",
    )
    with pytest.raises(RuntimeError, match="oversell"):
        apply_execution_fills(
            ExecutionState(cash=0.0, positions={"US": 1.0}),
            [fill],
        )


def test_execution_price_points_are_strictly_prospective():
    navs = pd.DataFrame(
        {
            "US": [100.0, 101.0, 102.0],
            "KR": [100.0, 99.0, 100.0],
        },
        index=pd.to_datetime(
            [
                "2026-09-09T00:00:00Z",
                "2026-09-10T00:00:00Z",
                "2026-09-11T00:00:00Z",
            ],
            utc=True,
        ),
    )
    planning_ts, _, fill_ts, _ = execution_price_points(
        navs,
        pd.Timestamp("2026-09-10T00:00:00Z"),
    )
    assert planning_ts == pd.Timestamp("2026-09-09T00:00:00Z")
    assert fill_ts == pd.Timestamp("2026-09-10T00:00:00Z")
    assert planning_ts < fill_ts


def test_gap_up_buy_is_cash_constrained_to_partial_fill():
    policy = ExecutionPolicy(
        max_symbol_weight=1.0,
        max_gross_weight=1.0,
        min_order_notional=0.01,
        max_single_order_fraction=1.0,
        max_total_turnover_fraction=2.0,
        slippage_bps=0.0,
        commission_bps=0.0,
    )
    cycle = run_shadow_rebalance(
        [_target("US", 1.0)],
        state=ExecutionState(cash=10_000.0, positions={}),
        planning_prices={"US": 100.0},
        fill_prices={"US": 125.0},
        fill_ts="2026-09-11T00:00:00+00:00",
        policy=policy,
        mode=Mode.SHADOW,
    )
    assert len(cycle.fills) == 1
    assert cycle.fills[0].status == "PARTIALLY_FILLED"
    assert abs(cycle.fills[0].quantity - 80.0) < 1e-10
    assert cycle.state.cash == 0.0
    assert abs(cycle.state.positions["US"] - 80.0) < 1e-10


def test_cash_constraint_uses_sell_proceeds_before_buys():
    from research.quant_stack.lean_execution import ExecutionFill

    state = ExecutionState(cash=0.0, positions={"US": 1.0})
    fills = [
        ExecutionFill(
            fill_id="buy",
            broker_order_id="bo-buy",
            intent_id="oi-buy",
            symbol="KR",
            side="BUY",
            quantity=2.0,
            fill_price=60.0,
            fee=0.0,
            fill_ts="2026-09-11T00:00:00+00:00",
            broker="SHADOW",
            status="FILLED",
        ),
        ExecutionFill(
            fill_id="sell",
            broker_order_id="bo-sell",
            intent_id="oi-sell",
            symbol="US",
            side="SELL",
            quantity=1.0,
            fill_price=100.0,
            fee=0.0,
            fill_ts="2026-09-11T00:00:00+00:00",
            broker="SHADOW",
            status="FILLED",
        ),
    ]
    constrained = cash_constrain_shadow_fills(state, fills)
    buy = next(fill for fill in constrained if fill.side == "BUY")
    assert buy.status == "PARTIALLY_FILLED"
    assert abs(buy.quantity - (100.0 / 60.0)) < 1e-10
    final_state = apply_execution_fills(state, constrained)
    assert final_state.cash == 0.0
    assert "US" not in final_state.positions
    assert abs(final_state.positions["KR"] - (100.0 / 60.0)) < 1e-10
