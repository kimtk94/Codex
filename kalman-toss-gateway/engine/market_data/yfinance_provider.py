from __future__ import annotations

from typing import Any

import pandas as pd
import yfinance as yf

from .base import MarketDataProvider, ProviderRequest, ProviderResult
from .schema import canonicalize_ohlcv, validate_canonical_ohlcv


class YFinanceProvider(MarketDataProvider):
    name = "yfinance"

    @staticmethod
    def _flatten_single(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
        if not isinstance(raw.columns, pd.MultiIndex):
            return raw.copy()

        for level in range(raw.columns.nlevels):
            values = raw.columns.get_level_values(level).astype(str)
            if ticker in set(values):
                try:
                    return raw.xs(ticker, axis=1, level=level, drop_level=True).copy()
                except KeyError:
                    pass

        for level in range(raw.columns.nlevels - 1, -1, -1):
            if len(set(raw.columns.get_level_values(level))) == 1:
                return raw.droplevel(level, axis=1).copy()

        raise RuntimeError(f"cannot flatten yfinance columns for {ticker}: {raw.columns!r}")

    def fetch(self, request: ProviderRequest) -> ProviderResult:
        ticker = request.source_symbol
        raw = yf.download(
            tickers=ticker,
            start=request.start,
            end=request.end,
            interval=request.interval,
            auto_adjust=request.adjusted,
            repair=True,
            keepna=True,
            ignore_tz=True,
            progress=False,
            group_by="column",
            threads=False,
            timeout=30,
        )
        if raw is None or raw.empty:
            raise RuntimeError(f"yfinance returned no data for {ticker}")

        one = self._flatten_single(raw, ticker)
        rename: dict[Any, str] = {}
        for col in one.columns:
            key = str(col).strip().lower().replace(" ", "_")
            if key in {"open", "high", "low", "close", "volume"}:
                rename[col] = key
            elif key in {"adj_close", "adjclose"}:
                rename[col] = "adj_close"

        data = canonicalize_ohlcv(
            one,
            symbol=request.symbol,
            market=request.market,
            currency=request.currency,
            source=self.name,
            column_map=rename,
            adjusted=request.adjusted,
        )
        issues = validate_canonical_ohlcv(data)
        metadata = {
            "provider": self.name,
            "provider_symbol": ticker,
            "symbol": request.symbol,
            "market": request.market,
            "currency": request.currency,
            "kind": request.kind,
            "interval": request.interval,
            "request_start": request.start,
            "request_end": request.end,
            "adjusted": request.adjusted,
            "row_count": int(len(data)),
            "first_timestamp": None if data.empty else str(data["timestamp"].iloc[0]),
            "last_timestamp": None if data.empty else str(data["timestamp"].iloc[-1]),
            "missing_close_count": int(data["close"].isna().sum()) if not data.empty else 0,
            "validation_issues": issues,
            "status": "READY" if not issues else "DEGRADED",
        }
        return ProviderResult(data=data, metadata=metadata)
