from dataclasses import dataclass
from .config import Settings


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str


def validate_order(settings: Settings, symbol: str, amount_krw: int) -> RiskDecision:
    symbol = symbol.upper()

    if not settings.trading_enabled:
        return RiskDecision(False, 'TRADING_DISABLED')
    if symbol not in settings.allowed_symbols:
        return RiskDecision(False, 'SYMBOL_NOT_ALLOWED')
    if amount_krw <= 0:
        return RiskDecision(False, 'INVALID_AMOUNT')
    if amount_krw > settings.max_single_order_krw:
        return RiskDecision(False, 'MAX_SINGLE_ORDER_EXCEEDED')
    if amount_krw > settings.symbol_limit_krw(symbol):
        return RiskDecision(False, 'SYMBOL_LIMIT_EXCEEDED')
    if amount_krw > settings.live_micro_total_limit_krw:
        return RiskDecision(False, 'LIVE_MICRO_TOTAL_LIMIT_EXCEEDED')

    return RiskDecision(True, 'OK')
