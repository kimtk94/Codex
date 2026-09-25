from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

PROFIT_TO_LOSS_FLIP = "PROFIT_TO_LOSS_FLIP"


@dataclass(frozen=True)
class ProfitFlipState:
    """Pure representation of the live profit-to-loss guard state."""

    peak_price_return: Decimal | None = None
    armed: bool = False
    negative_count: int = 0
    pending_reason: str | None = None
    pending_since: str | None = None


def validate_profit_flip_parameters(
    *,
    arm_pct: Decimal,
    trigger_pct: Decimal,
    recovery_pct: Decimal,
    confirm_observations: int,
) -> None:
    if arm_pct < 0 or arm_pct > Decimal("0.20"):
        raise RuntimeError("AUTO_TRADE_PROFIT_FLIP_ARM_PCT must be between 0 and 0.20")
    if trigger_pct >= 0 or trigger_pct < Decimal("-0.20"):
        raise RuntimeError("AUTO_TRADE_PROFIT_FLIP_TRIGGER_PCT must be between -0.20 and 0")
    if recovery_pct < trigger_pct or recovery_pct > Decimal("0.20"):
        raise RuntimeError(
            "AUTO_TRADE_PROFIT_FLIP_RECOVERY_PCT must be >= trigger and <= 0.20"
        )
    if confirm_observations < 1 or confirm_observations > 12:
        raise RuntimeError(
            "AUTO_TRADE_PROFIT_FLIP_CONFIRM_OBSERVATIONS must be between 1 and 12"
        )


def advance_profit_flip(
    state: ProfitFlipState,
    *,
    price_return: Decimal,
    arm_pct: Decimal,
    trigger_pct: Decimal,
    confirm_observations: int,
    observed_at: str,
) -> ProfitFlipState:
    """Advance exactly one live observation without execution assumptions."""

    previous_peak = state.peak_price_return
    if previous_peak is None:
        previous_peak = price_return
    peak = max(previous_peak, price_return)
    armed = state.armed or peak >= arm_pct

    negative_count = state.negative_count
    if armed and price_return <= trigger_pct:
        negative_count += 1
    else:
        negative_count = 0

    pending_reason = state.pending_reason
    pending_since = state.pending_since
    if armed and negative_count >= int(confirm_observations) and not pending_reason:
        pending_reason = PROFIT_TO_LOSS_FLIP
        pending_since = observed_at

    return ProfitFlipState(
        peak_price_return=peak,
        armed=armed,
        negative_count=negative_count,
        pending_reason=pending_reason,
        pending_since=pending_since,
    )


def should_clear_profit_flip_pending(
    *,
    pending_reason: str | None,
    price_return: Decimal,
    recovery_pct: Decimal,
) -> bool:
    return pending_reason == PROFIT_TO_LOSS_FLIP and price_return > recovery_pct


def clear_profit_flip_pending(state: ProfitFlipState) -> ProfitFlipState:
    """Clear pending state exactly as the live store does after recovery."""

    return replace(
        state,
        negative_count=0,
        pending_reason=None,
        pending_since=None,
    )


def choose_exit_reason(
    *,
    price_return: Decimal,
    stop_loss: Decimal,
    take_profit: Decimal,
    model_rotation: bool,
    elapsed_buckets: int,
    target_buckets: int,
    pending_exit_reason: str | None = None,
) -> str | None:
    """Live exit-priority contract shared by production and research replay."""

    if price_return <= stop_loss:
        return "STOP_LOSS_3PCT"
    if price_return >= take_profit:
        return "TAKE_PROFIT_20PCT"
    if pending_exit_reason:
        return pending_exit_reason
    if model_rotation:
        return "MODEL_ROTATION"
    if elapsed_buckets >= target_buckets:
        return "MAX_HOLD_4_BUCKETS"
    return None
