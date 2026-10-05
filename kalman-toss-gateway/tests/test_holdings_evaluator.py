from decimal import Decimal

from engine.holdings_evaluator import _classification, _update_unmanaged_review_state


def test_managed_top2_is_model_supported_hold():
    action, flags = _classification(
        managed={"state": "OPEN", "exit_pending_reason": None},
        support_rank=1,
        pnl_rate=Decimal("-0.001"),
        stop_loss=Decimal("-0.03"),
        take_profit=Decimal("0.20"),
    )
    assert action == "HOLD_MODEL_SUPPORTED"
    assert "MODEL_TOP1" in flags


def test_managed_outside_top2_remains_under_exit_rules():
    action, flags = _classification(
        managed={"state": "OPEN", "exit_pending_reason": None},
        support_rank=None,
        pnl_rate=Decimal("0.005"),
        stop_loss=Decimal("-0.03"),
        take_profit=Decimal("0.20"),
    )
    assert action == "HOLD_MANAGED_EXIT_RULES"
    assert "OUTSIDE_CURRENT_TOP2" in flags


def test_unmanaged_positive_outside_top2_is_no_add_review():
    action, flags = _classification(
        managed=None,
        support_rank=None,
        pnl_rate=Decimal("0.006"),
        stop_loss=Decimal("-0.03"),
        take_profit=Decimal("0.20"),
    )
    assert action == "UNMANAGED_HOLD_NO_ADD_REVIEW"
    assert "UNMANAGED_BROKER_HOLDING" in flags


def test_unmanaged_loss_outside_top2_is_exit_review():
    action, flags = _classification(
        managed=None,
        support_rank=None,
        pnl_rate=Decimal("-0.01"),
        stop_loss=Decimal("-0.03"),
        take_profit=Decimal("0.20"),
    )
    assert action == "UNMANAGED_EXIT_REVIEW"
    assert "UNREALIZED_LOSS" in flags


def test_managed_exit_pending_has_priority_over_model_support():
    action, flags = _classification(
        managed={"state": "OPEN", "exit_pending_reason": "PROFIT_TO_LOSS_FLIP"},
        support_rank=2,
        pnl_rate=Decimal("-0.002"),
        stop_loss=Decimal("-0.03"),
        take_profit=Decimal("0.20"),
    )
    assert action == "MANAGED_EXIT_PENDING"
    assert "EXIT_PENDING:PROFIT_TO_LOSS_FLIP" in flags


def test_unmanaged_profit_flip_requires_two_negative_observations():
    base = dict(
        stop_loss=Decimal("-0.03"),
        take_profit=Decimal("0.20"),
        flip_enabled=True,
        arm_pct=Decimal("0.002"),
        trigger_pct=Decimal("-0.002"),
        recovery_pct=Decimal("0"),
        confirm_observations=2,
    )
    armed = _update_unmanaged_review_state(
        previous=None,
        pnl_rate=Decimal("0.006"),
        now="t1",
        **base,
    )
    assert armed["profit_flip_armed"] is True
    assert armed["strong_sell_review_reason"] is None

    first = _update_unmanaged_review_state(
        previous=armed,
        pnl_rate=Decimal("-0.003"),
        now="t2",
        **base,
    )
    assert first["profit_flip_negative_count"] == 1
    assert first["strong_sell_review_reason"] is None

    second = _update_unmanaged_review_state(
        previous=first,
        pnl_rate=Decimal("-0.003"),
        now="t3",
        **base,
    )
    assert second["profit_flip_negative_count"] == 2
    assert second["strong_sell_review_reason"] == "PROFIT_TO_LOSS_FLIP"


def test_unmanaged_hard_stop_and_take_profit_are_immediate_reviews():
    base = dict(
        stop_loss=Decimal("-0.03"),
        take_profit=Decimal("0.20"),
        flip_enabled=True,
        arm_pct=Decimal("0.002"),
        trigger_pct=Decimal("-0.002"),
        recovery_pct=Decimal("0"),
        confirm_observations=2,
        now="t",
    )
    stop = _update_unmanaged_review_state(
        previous=None,
        pnl_rate=Decimal("-0.031"),
        **base,
    )
    take = _update_unmanaged_review_state(
        previous=None,
        pnl_rate=Decimal("0.21"),
        **base,
    )
    assert stop["strong_sell_review_reason"] == "STOP_LOSS_3PCT"
    assert take["strong_sell_review_reason"] == "TAKE_PROFIT_20PCT"
