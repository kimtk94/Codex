from dataclasses import dataclass
from .config import Settings


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str


def validate_order(
    settings: Settings,
    symbol: str,
    amount_krw: int,
    daily_committed_krw: int = 0,
    *,
    risk_reducing_exit: bool = False,
) -> RiskDecision:
    symbol = symbol.upper()

    if not settings.trading_enabled:
        return RiskDecision(False, 'TRADING_DISABLED')
    if settings.live_trading_confirm != 'CONFIRM_LIVE_TRADING':
        return RiskDecision(False, 'LIVE_CONFIRMATION_MISSING')
    if amount_krw <= 0:
        return RiskDecision(False, 'INVALID_AMOUNT')

    # Managed exits may reduce risk regardless of entry notional caps. Global
    # live gates still apply, and sellable quantity is verified by the broker API.
    if risk_reducing_exit:
        return RiskDecision(True, 'OK_RISK_REDUCING_EXIT')

    if amount_krw > settings.max_single_order_krw:
        return RiskDecision(False, 'MAX_SINGLE_ORDER_EXCEEDED')
    if daily_committed_krw + amount_krw > settings.live_micro_total_limit_krw:
        return RiskDecision(False, 'DAILY_TOTAL_LIMIT_EXCEEDED')

    return RiskDecision(True, 'OK')
