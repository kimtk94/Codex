from __future__ import annotations

from decimal import Decimal
import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.live_exit_policy import (
    PROFIT_TO_LOSS_FLIP,
    ProfitFlipState,
    advance_profit_flip,
    choose_exit_reason,
    clear_profit_flip_pending,
    should_clear_profit_flip_pending,
)
from app.managed_positions import ManagedPositionStore
from research.quant_stack.live_policy_replay import (
    MinuteBarIndex,
    ReplayPolicyConfig,
    fractional_window_open,
    iter_live_watch_ticks,
    replay_one_trade,
)


def _cfg() -> ReplayPolicyConfig:
    return ReplayPolicyConfig(
        profit_flip_enabled=True,
        arm_pct=Decimal("0.002"),
        trigger_pct=Decimal("-0.002"),
        recovery_pct=Decimal("0"),
        confirm_observations=2,
        stop_loss=Decimal("-0.03"),
        take_profit=Decimal("0.20"),
        model_rotation_enabled=False,
    )


def test_profit_flip_requires_arm_and_two_consecutive_negative_observations():
    state = ProfitFlipState()
    state = advance_profit_flip(
        state,
        price_return=Decimal("0.003"),
        arm_pct=Decimal("0.002"),
        trigger_pct=Decimal("-0.002"),
        confirm_observations=2,
        observed_at="2026-09-23T00:00:00+00:00",
    )
    assert state.armed is True
    assert state.pending_reason is None

    state = advance_profit_flip(
        state,
        price_return=Decimal("-0.003"),
        arm_pct=Decimal("0.002"),
        trigger_pct=Decimal("-0.002"),
        confirm_observations=2,
        observed_at="2026-09-23T00:30:00+00:00",
    )
    assert state.negative_count == 1
    assert state.pending_reason is None

    state = advance_profit_flip(
        state,
        price_return=Decimal("-0.004"),
        arm_pct=Decimal("0.002"),
        trigger_pct=Decimal("-0.002"),
        confirm_observations=2,
        observed_at="2026-09-23T01:00:00+00:00",
    )
    assert state.negative_count == 2
    assert state.pending_reason == PROFIT_TO_LOSS_FLIP


def test_recovery_clears_pending_but_keeps_peak_and_arm():
    state = ProfitFlipState(
        peak_price_return=Decimal("0.01"),
        armed=True,
        negative_count=2,
        pending_reason=PROFIT_TO_LOSS_FLIP,
        pending_since="2026-09-23T01:00:00+00:00",
    )
    assert should_clear_profit_flip_pending(
        pending_reason=state.pending_reason,
        price_return=Decimal("0.001"),
        recovery_pct=Decimal("0"),
    )
    state = clear_profit_flip_pending(state)
    assert state.armed is True
    assert state.peak_price_return == Decimal("0.01")
    assert state.negative_count == 0
    assert state.pending_reason is None


def test_stop_loss_has_priority_over_pending_profit_flip():
    reason = choose_exit_reason(
        price_return=Decimal("-0.04"),
        stop_loss=Decimal("-0.03"),
        take_profit=Decimal("0.20"),
        model_rotation=False,
        elapsed_buckets=0,
        target_buckets=4,
        pending_exit_reason=PROFIT_TO_LOSS_FLIP,
    )
    assert reason == "STOP_LOSS_3PCT"


def test_pure_profit_flip_contract_matches_managed_position_store(tmp_path):
    store = ManagedPositionStore(tmp_path / "state.sqlite3")
    reserved, row = store.reserve_entry(
        run_id="r1",
        symbol="AMD",
        strategy_version="R5.1",
        signal_as_of="2026-09-23T00:00:00+00:00",
        client_order_id="cid-1",
        target_exit_buckets=4,
    )
    assert reserved and row is not None
    pid = row["position_id"]
    store.mark_open(
        pid,
        entry_status="FILLED",
        filled_quantity=Decimal("1"),
        average_price="100",
    )

    pure = ProfitFlipState()
    for i, ret in enumerate(("0.003", "-0.003", "-0.004")):
        pure = advance_profit_flip(
            pure,
            price_return=Decimal(ret),
            arm_pct=Decimal("0.002"),
            trigger_pct=Decimal("-0.002"),
            confirm_observations=2,
            observed_at=f"synthetic-{i}",
        )
        db = store.observe_price_return(
            pid,
            price_return=Decimal(ret),
            arm_pct=Decimal("0.002"),
            trigger_pct=Decimal("-0.002"),
            confirm_observations=2,
        )
        assert db is not None
        assert Decimal(db["peak_price_return"]) == pure.peak_price_return
        assert bool(int(db["profit_flip_armed"])) == pure.armed
        assert int(db["profit_flip_negative_count"]) == pure.negative_count
        assert db["exit_pending_reason"] == pure.pending_reason


def test_live_watch_schedule_contains_daytime_and_execution_cadence():
    ticks = iter_live_watch_ticks(
        "2025-09-16T00:00:00Z",
        "2025-09-16T14:00:00Z",
    )
    pairs = {(x.timestamp.isoformat(), x.source) for x in ticks}
    assert ("2025-09-16T00:30:00+00:00", "POSITION_WATCH") in pairs
    assert ("2025-09-16T13:25:00+00:00", "EXECUTION_WATCH") in pairs
    assert ("2025-09-16T13:30:00+00:00", "EXECUTION_WATCH") in pairs


def test_fractional_window_proxy_is_dst_safe():
    assert fractional_window_open("2025-09-16T13:30:00Z")
    assert not fractional_window_open("2025-09-16T13:25:00Z")
    assert fractional_window_open("2026-01-15T14:30:00Z")
    assert not fractional_window_open("2026-01-15T14:25:00Z")


def test_minute_index_uses_open_at_tick_without_close_lookahead():
    bars = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2025-09-16T13:30:00Z", "2025-09-16T13:31:00Z"],
                utc=True,
            ),
            "open": [99.0, 98.0],
            "close": [100.0, 97.0],
        }
    )
    idx = MinuteBarIndex(bars)
    point = idx.open_at_or_after("2025-09-16T13:30:00Z")
    assert point is not None and point.price == 99.0
    before = idx.close_before("2025-09-16T13:31:00Z")
    assert before is not None and before.price == 100.0


def test_replay_arms_by_daytime_and_exits_at_first_executable_regular_tick():
    rows = [
        ("2025-09-15T19:59:00Z", 100.0, 100.0),
        ("2025-09-16T00:00:00Z", 101.0, 101.0),
        ("2025-09-16T00:30:00Z", 99.0, 99.0),
        ("2025-09-16T01:00:00Z", 99.0, 99.0),
        ("2025-09-16T13:30:00Z", 98.0, 98.0),
        ("2025-09-16T15:29:00Z", 97.0, 97.0),
    ]
    bars = pd.DataFrame(
        {
            "timestamp": pd.to_datetime([x[0] for x in rows], utc=True),
            "open": [x[1] for x in rows],
            "close": [x[2] for x in rows],
        }
    )
    row = {
        "entry_timestamp": pd.Timestamp("2025-09-15T19:00:00Z"),
        "exit_timestamp": pd.Timestamp("2025-09-16T14:30:00Z"),
    }
    result, _ = replay_one_trade(
        row,
        bars=bars,
        config=_cfg(),
        event_audit="changes",
    )
    assert result["replay_data_ready"] is True
    assert result["profit_flip_arm_at"] == pd.Timestamp("2025-09-16T00:00:00Z")
    assert result["profit_flip_pending_at"] == pd.Timestamp("2025-09-16T01:00:00Z")
    assert result["candidate_exit_triggered"] is True
    assert result["candidate_exit_reason"] == PROFIT_TO_LOSS_FLIP
    assert result["candidate_exit_at"] == pd.Timestamp("2025-09-16T13:30:00Z")
    assert result["candidate_exit_price_vendor"] == 98.0
