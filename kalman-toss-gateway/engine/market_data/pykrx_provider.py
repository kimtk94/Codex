from __future__ import annotations

from .base import MarketDataProvider, ProviderRequest, ProviderResult
from .schema import canonicalize_ohlcv, validate_canonical_ohlcv


_KRX_COLUMNS = {
    "시가": "open",
    "고가": "high",
    "저가": "low",
    "종가": "close",
    "거래량": "volume",
}


class PyKrxProvider(MarketDataProvider):
    name = "pykrx"

    @staticmethod
    def _yyyymmdd(value: str | None, *, fallback_today: bool = False) -> str:
        import pandas as pd

        if value:
            return pd.Timestamp(value).strftime("%Y%m%d")
        if fallback_today:
            return pd.Timestamp.now(tz="Asia/Seoul").strftime("%Y%m%d")
        raise ValueError("date is required")

    def fetch(self, request: ProviderRequest) -> ProviderResult:
        try:
            from pykrx import stock
        except ImportError as exc:
            raise RuntimeError("pykrx is not installed") from exc

        start = self._yyyymmdd(request.start)
        end = self._yyyymmdd(request.end, fallback_today=True)
        provider_symbol = request.source_symbol

        if request.kind.lower() == "index":
            raw = stock.get_index_ohlcv_by_date(start, end, provider_symbol)
            adjusted = False
        elif request.kind.lower() in {"equity", "stock"}:
            raw = stock.get_market_ohlcv_by_date(
                start,
                end,
                provider_symbol,
                adjusted=request.adjusted,
            )
            adjusted = request.adjusted
        else:
            raise ValueError(f"pykrx does not support kind={request.kind!r}")

        if raw is None or raw.empty:
            raise RuntimeError(f"pykrx returned no data for {provider_symbol}")

        data = canonicalize_ohlcv(
            raw,
            symbol=request.symbol,
            market=request.market,
            currency=request.currency or "KRW",
            source=self.name,
            column_map=_KRX_COLUMNS,
            adjusted=adjusted,
        )
        issues = validate_canonical_ohlcv(data)
        metadata = {
            "provider": self.name,
            "provider_symbol": provider_symbol,
            "symbol": request.symbol,
            "market": request.market,
            "currency": request.currency or "KRW",
            "kind": request.kind,
            "interval": "1d",
            "request_start": request.start,
            "request_end": request.end,
            "adjusted": adjusted,
            "row_count": int(len(data)),
            "first_timestamp": None if data.empty else str(data["timestamp"].iloc[0]),
            "last_timestamp": None if data.empty else str(data["timestamp"].iloc[-1]),
            "missing_close_count": int(data["close"].isna().sum()) if not data.empty else 0,
            "validation_issues": issues,
            "status": "READY" if not issues else "DEGRADED",
        }
        return ProviderResult(data=data, metadata=metadata)
