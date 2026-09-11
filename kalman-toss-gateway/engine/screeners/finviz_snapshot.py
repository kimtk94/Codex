from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from engine.market_data.snapshot import atomic_json, write_snapshot


@dataclass(frozen=True)
class FinvizSettings:
    output_dir: Path
    limit: int = 500
    filters: dict[str, str] | None = None
    signal: str = ""
    min_price: float = 0.0
    min_market_cap: float = 0.0
    min_volume: float = 0.0


VIEW_CLASSES = {
    "overview": ("finvizfinance.screener.overview", "Overview"),
    "valuation": ("finvizfinance.screener.valuation", "Valuation"),
    "financial": ("finvizfinance.screener.financial", "Financial"),
    "performance": ("finvizfinance.screener.performance", "Performance"),
    "technical": ("finvizfinance.screener.technical", "Technical"),
}


def _import_view(module_name: str, class_name: str):
    import importlib

    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def _numeric(value: object) -> float:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return np.nan
    if isinstance(value, (int, float, np.number)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text or text in {"-", "N/A", "nan", "None"}:
        return np.nan

    pct = text.endswith("%")
    if pct:
        text = text[:-1]

    multipliers = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
    factor = 1.0
    if text and text[-1].upper() in multipliers:
        factor = multipliers[text[-1].upper()]
        text = text[:-1]

    try:
        value = float(text) * factor
    except ValueError:
        return np.nan
    return value / 100.0 if pct else value


def _ticker_column(frame: pd.DataFrame) -> str:
    for candidate in ("Ticker", "ticker", "Symbol", "symbol"):
        if candidate in frame.columns:
            return candidate
    raise ValueError(f"Finviz view missing ticker column: {frame.columns.tolist()}")


def fetch_views(settings: FinvizSettings) -> tuple[dict[str, pd.DataFrame], str]:
    snapshot_at = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    views: dict[str, pd.DataFrame] = {}

    for name, (module_name, class_name) in VIEW_CLASSES.items():
        cls = _import_view(module_name, class_name)
        screener = cls()
        screener.set_filter(
            signal=settings.signal,
            filters_dict=settings.filters or {},
        )
        frame = screener.screener_view(
            order="Ticker",
            limit=settings.limit,
            verbose=0,
            sleep_sec=1,
        )
        if frame is None or frame.empty:
            raise RuntimeError(f"Finviz {name} view returned no rows")
        frame = frame.copy()
        ticker_col = _ticker_column(frame)
        if ticker_col != "Ticker":
            frame = frame.rename(columns={ticker_col: "Ticker"})
        frame["Ticker"] = frame["Ticker"].astype(str).str.upper().str.strip()
        frame["snapshot_at"] = snapshot_at
        views[name] = frame.drop_duplicates("Ticker", keep="last")

    return views, snapshot_at


def merge_views(views: dict[str, pd.DataFrame]) -> pd.DataFrame:
    merged: pd.DataFrame | None = None

    for name, frame in views.items():
        x = frame.copy()
        keep = ["Ticker"]
        renamed: dict[str, str] = {}
        for col in x.columns:
            if col == "Ticker":
                continue
            renamed[col] = f"{name}__{col}"
            keep.append(col)
        x = x[keep].rename(columns=renamed)
        merged = x if merged is None else merged.merge(x, on="Ticker", how="outer")

    if merged is None:
        return pd.DataFrame(columns=["Ticker"])
    return merged.sort_values("Ticker").reset_index(drop=True)


def build_candidate_universe(
    merged: pd.DataFrame,
    settings: FinvizSettings,
) -> pd.DataFrame:
    out = merged.copy()

    lookup = {
        "price": ["overview__Price", "technical__Price"],
        "market_cap": ["overview__Market Cap"],
        "volume": ["overview__Volume", "technical__Volume"],
        "sector": ["overview__Sector"],
        "industry": ["overview__Industry"],
        "rsi": ["technical__RSI"],
        "relative_volume": ["technical__Rel Volume", "technical__Relative Volume"],
        "sma20": ["technical__SMA20"],
        "sma50": ["technical__SMA50"],
        "sma200": ["technical__SMA200"],
        "pe": ["valuation__P/E", "overview__P/E"],
        "forward_pe": ["valuation__Forward P/E"],
        "peg": ["valuation__PEG"],
        "roe": ["financial__ROE"],
        "debt_equity": ["financial__Debt/Eq"],
        "sales_growth": ["financial__Sales past 5Y", "financial__Sales Y/Y TTM"],
        "eps_growth": ["financial__EPS past 5Y", "financial__EPS Y/Y TTM"],
    }

    candidate = pd.DataFrame({"ticker": out["Ticker"]})
    for canonical, candidates in lookup.items():
        source = next((c for c in candidates if c in out.columns), None)
        if source is None:
            candidate[canonical] = np.nan
        elif canonical in {"sector", "industry"}:
            candidate[canonical] = out[source]
        else:
            candidate[canonical] = out[source].map(_numeric)

    candidate["source"] = "finvizfinance"
    snapshot_cols = [c for c in out.columns if c.endswith("__snapshot_at")]
    candidate["snapshot_at"] = (
        out[snapshot_cols[0]] if snapshot_cols else pd.Timestamp.now(tz="UTC").isoformat()
    )

    mask = pd.Series(True, index=candidate.index)
    if settings.min_price > 0:
        mask &= candidate["price"].fillna(-np.inf) >= settings.min_price
    if settings.min_market_cap > 0:
        mask &= candidate["market_cap"].fillna(-np.inf) >= settings.min_market_cap
    if settings.min_volume > 0:
        mask &= candidate["volume"].fillna(-np.inf) >= settings.min_volume

    candidate["passes_local_filter"] = mask.astype(bool)
    return candidate.sort_values(["passes_local_filter", "ticker"], ascending=[False, True])


def save_snapshot(
    views: dict[str, pd.DataFrame],
    merged: pd.DataFrame,
    candidates: pd.DataFrame,
    *,
    settings: FinvizSettings,
    snapshot_at: str,
) -> dict[str, Any]:
    snapshot_dt = pd.Timestamp(snapshot_at)
    date_key = snapshot_dt.strftime("%Y-%m-%d")
    root = settings.output_dir / date_key
    root.mkdir(parents=True, exist_ok=True)

    files: dict[str, Any] = {}
    for name, frame in views.items():
        files[name] = write_snapshot(
            frame,
            root / f"{name}.parquet",
            metadata={
                "source": "finvizfinance",
                "view": name,
                "snapshot_at": snapshot_at,
                "point_in_time": True,
                "filters": settings.filters or {},
                "signal": settings.signal,
                "limit": settings.limit,
            },
        )

    files["merged"] = write_snapshot(
        merged,
        root / "merged_snapshot.parquet",
        metadata={
            "source": "finvizfinance",
            "snapshot_at": snapshot_at,
            "point_in_time": True,
            "filters": settings.filters or {},
            "signal": settings.signal,
        },
    )
    files["candidates"] = write_snapshot(
        candidates,
        root / "candidate_universe.parquet",
        metadata={
            "source": "finvizfinance",
            "snapshot_at": snapshot_at,
            "point_in_time": True,
            "local_filters": {
                "min_price": settings.min_price,
                "min_market_cap": settings.min_market_cap,
                "min_volume": settings.min_volume,
            },
        },
    )

    status = {
        "status": "READY",
        "source": "finvizfinance",
        "point_in_time": True,
        "snapshot_at": snapshot_at,
        "snapshot_date": date_key,
        "output_dir": str(root),
        "views": {k: int(len(v)) for k, v in views.items()},
        "merged_rows": int(len(merged)),
        "candidate_rows": int(len(candidates)),
        "passing_candidates": int(candidates["passes_local_filter"].sum()),
        "files": files,
    }
    atomic_json(settings.output_dir / "finviz_run_status.json", status)
    return status
