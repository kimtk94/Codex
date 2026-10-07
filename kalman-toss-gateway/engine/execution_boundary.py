from __future__ import annotations

"""Fail-closed execution boundary for Kalman production and research modes."""

LIVE_R5_STRATEGY = "R5.1_BASE_HGB"

AUTO_TRADE_ENTRY_POLICIES = frozenset({
    "APPROVED_ONLY",
    "SHADOW_CANARY",
    "R5_LIVE_TOP1",
})

READINESS_POLICIES = frozenset({
    *AUTO_TRADE_ENTRY_POLICIES,
    "R5_LIVE_CONDITIONAL",
})

R5_LIVE_POLICIES = frozenset({
    "R5_LIVE_TOP1",
    "R5_LIVE_CONDITIONAL",
})

TOP1_CONFIRM_TOKEN = "CONFIRM_R5_LIVE_TOP1"

CONDITIONAL_CONFIRM_TOKENS = frozenset({
    "CONFIRM_R5_LIVE_CONDITIONAL_20000",
    "CONFIRM_R5_LIVE_CONDITIONAL_5000",
})


def r5_live_strategy_locked(policy: str, strategy_version: str | None) -> bool:
    """Only the frozen R5.1 strategy may cross an R5 LIVE policy boundary."""
    normalized_policy = str(policy or "").strip().upper()
    normalized_strategy = str(strategy_version or "").strip()
    if normalized_policy not in R5_LIVE_POLICIES:
        return True
    return normalized_strategy == LIVE_R5_STRATEGY


def is_r5_2_research_strategy(strategy_version: str | None) -> bool:
    """Recognize R5.2 naming without granting any execution permission."""
    normalized = str(strategy_version or "").strip().upper().replace("_", ".")
    return normalized.startswith("R5.2")
