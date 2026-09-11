from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ProviderRequest:
    """Provider-neutral request for a daily market series."""

    symbol: str
    start: str
    end: str | None = None
    market: str = "UNKNOWN"
    currency: str = ""
    interval: str = "1d"
    kind: str = "equity"
    provider_symbol: str | None = None
    adjusted: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def source_symbol(self) -> str:
        return self.provider_symbol or self.symbol


@dataclass
class ProviderResult:
    """Canonical provider response plus provenance metadata."""

    data: pd.DataFrame
    metadata: dict[str, Any]


class MarketDataProvider(ABC):
    name: str

    @abstractmethod
    def fetch(self, request: ProviderRequest) -> ProviderResult:
        """Return canonical OHLCV data and source metadata."""
        raise NotImplementedError
