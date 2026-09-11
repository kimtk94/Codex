"""Kalman Market Data V2 provider layer.

This package is shadow/research-only. It must not mutate production model
artifacts, Neon strategy signals, or broker execution state.
"""

from .base import MarketDataProvider, ProviderRequest, ProviderResult
from .schema import MACRO_COLUMNS, OHLCV_COLUMNS

__all__ = [
    "MarketDataProvider",
    "ProviderRequest",
    "ProviderResult",
    "OHLCV_COLUMNS",
    "MACRO_COLUMNS",
]
