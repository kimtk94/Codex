from __future__ import annotations

from typing import Any

from .base import MarketDataProvider, ProviderRequest, ProviderResult
from .schema import canonicalize_ohlcv, validate_canonical_ohlcv


class FinanceDataReaderProvider(MarketDataProvider):
    name = "FinanceDataReader"

    def fetch(self, request: ProviderRequest) -> ProviderResult:
        try:
            import FinanceDataReader as fdr
        except ImportError as exc:
            raise RuntimeError(
                "FinanceDataReader is not installed. Use the Market Tools V2 virtualenv."
            ) from exc

        provider_symbol = request.source_symbol
        raw = fdr.DataReader(provider_symbol, request.start, request.end)
        if raw is None or raw.empty:
            raise RuntimeError(f"FinanceDataReader returned no data for {provider_symbol}")

        rename: dict[Any, str] = {}
        for col in raw.columns:
            key = str(col).strip().lower().replace(" ", "_")
            if key in {"open", "high", "low", "close", "volume"}:
                rename[col] = key
            elif key in {"adj_close", "adjclose"}:
                rename[col] = "adj_close"

        data = canonicalize_ohlcv(
            raw,
            symbol=request.symbol,
            market=request.market,
            currency=request.currency,
            source=self.name,
            column_map=rename,
            adjusted=False,
        )
        issues = validate_canonical_ohlcv(data)
        metadata = {
            "provider": self.name,
            "provider_symbol": provider_symbol,
            "symbol": request.symbol,
            "market": request.market,
            "currency": request.currency,
            "kind": request.kind,
            "interval": request.interval,
            "request_start": request.start,
            "request_end": request.end,
            "adjusted": False,
            "row_count": int(len(data)),
            "first_timestamp": None if data.empty else str(data["timestamp"].iloc[0]),
            "last_timestamp": None if data.empty else str(data["timestamp"].iloc[-1]),
            "missing_close_count": int(data["close"].isna().sum()) if not data.empty else 0,
            "validation_issues": issues,
            "status": "READY" if not issues else "DEGRADED",
        }
        return ProviderResult(data=data, metadata=metadata)
