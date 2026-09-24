#!/usr/bin/env python3
"""
Kalman Multi-Market Phase 1 Collector
=====================================

Leakage-safe P0 market/macro collector for US / KR / BTC.
Read-only: this module never places trades.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import math
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

UTC = timezone.utc
KST = ZoneInfo("Asia/Seoul")
NY = ZoneInfo("America/New_York")
LOG = logging.getLogger("kalman.phase1")


@dataclasses.dataclass
class Settings:
    data_dir: Path
    lookback_days: int
    http_timeout: int
    alpaca_key: Optional[str]
    alpaca_secret: Optional[str]
    alpaca_feed: str
    fred_key: Optional[str]
    ecos_key: Optional[str]
    ecos_kr3y_stat_code: Optional[str]
    ecos_kr3y_cycle: str
    ecos_kr3y_item_code1: Optional[str]
    ecos_kr10y_stat_code: Optional[str]
    ecos_kr10y_cycle: str
    ecos_kr10y_item_code1: Optional[str]
    ecos_usdkrw_stat_code: Optional[str]
    ecos_usdkrw_cycle: str
    ecos_usdkrw_item_code1: Optional[str]
    macro_us_lag_days: int
    macro_kr_lag_days: int
    stale_daily_hours: int

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            data_dir=Path(os.getenv("DATA_DIR", "./data")).expanduser().resolve(),
            lookback_days=int(os.getenv("LOOKBACK_DAYS", "420")),
            http_timeout=int(os.getenv("HTTP_TIMEOUT", "20")),
            alpaca_key=os.getenv("ALPACA_API_KEY_ID") or os.getenv("APCA_API_KEY_ID"),
            alpaca_secret=os.getenv("ALPACA_API_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY"),
            alpaca_feed=os.getenv("ALPACA_FEED", "iex"),
            fred_key=os.getenv("FRED_API_KEY"),
            ecos_key=os.getenv("BOK_ECOS_API_KEY") or os.getenv("ECOS_API_KEY"),
            ecos_kr3y_stat_code=os.getenv("ECOS_KR3Y_STAT_CODE"),
            ecos_kr3y_cycle=os.getenv("ECOS_KR3Y_CYCLE", "D"),
            ecos_kr3y_item_code1=os.getenv("ECOS_KR3Y_ITEM_CODE1"),
            ecos_kr10y_stat_code=os.getenv("ECOS_KR10Y_STAT_CODE"),
            ecos_kr10y_cycle=os.getenv("ECOS_KR10Y_CYCLE", "D"),
            ecos_kr10y_item_code1=os.getenv("ECOS_KR10Y_ITEM_CODE1"),
            ecos_usdkrw_stat_code=os.getenv("ECOS_USDKRW_STAT_CODE"),
            ecos_usdkrw_cycle=os.getenv("ECOS_USDKRW_CYCLE", "D"),
            ecos_usdkrw_item_code1=os.getenv("ECOS_USDKRW_ITEM_CODE1"),
            macro_us_lag_days=int(os.getenv("MACRO_US_LAG_DAYS", "2")),
            macro_kr_lag_days=int(os.getenv("MACRO_KR_LAG_DAYS", "1")),
            stale_daily_hours=int(os.getenv("STALE_DAILY_HOURS", "72")),
        )


def utcnow() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def safe_float(x: Any) -> float:
    if x in (None, "", "."):
        return np.nan
    try:
        return float(x)
    except Exception:
        return np.nan


def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "event_time", "available_time", "market", "indicator_id", "raw_value",
        "source", "source_updated_at", "is_complete", "is_stale",
        "quality_flag", "metadata",
    ]
    if df.empty:
        return pd.DataFrame(columns=cols)
    for c in cols:
        if c not in df.columns:
            df[c] = None
    df["event_time"] = pd.to_datetime(df["event_time"], utc=True, errors="coerce")
    df["available_time"] = pd.to_datetime(df["available_time"], utc=True, errors="coerce")
    df["source_updated_at"] = pd.to_datetime(df["source_updated_at"], utc=True, errors="coerce")
    df["raw_value"] = pd.to_numeric(df["raw_value"], errors="coerce")
    df["is_complete"] = df["is_complete"].fillna(False).astype(bool)
    df["is_stale"] = df["is_stale"].fillna(True).astype(bool)
    return df[cols].sort_values(["indicator_id", "event_time"]).reset_index(drop=True)


def request_json(method: str, url: str, *, headers=None, params=None, timeout=20, retries=3) -> Any:
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.request(method, url, headers=headers, params=params, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(1.5 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            if attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"HTTP failed after {retries} attempts: {url}: {last_err}")


def daily_market_close_utc(day: pd.Timestamp, market: str) -> pd.Timestamp:
    d = pd.Timestamp(day).date()
    if market == "US":
        return pd.Timestamp(datetime(d.year, d.month, d.day, 16, 0, tzinfo=NY)).tz_convert("UTC")
    if market == "KR":
        return pd.Timestamp(datetime(d.year, d.month, d.day, 15, 30, tzinfo=KST)).tz_convert("UTC")
    raise ValueError(market)


def freshness_flag(available_time: pd.Timestamp, threshold_hours: int) -> bool:
    if pd.isna(available_time):
        return True
    return (utcnow() - available_time) > pd.Timedelta(hours=threshold_hours)


class AlpacaCollector:
    BASE = "https://data.alpaca.markets/v2/stocks/bars"

    def __init__(self, cfg: Settings):
        self.cfg = cfg

    def collect_daily(self, symbols: Iterable[str], start: date, end: date) -> pd.DataFrame:
        if not (self.cfg.alpaca_key and self.cfg.alpaca_secret):
            raise RuntimeError("Alpaca credentials missing")
        headers = {
            "APCA-API-KEY-ID": self.cfg.alpaca_key,
            "APCA-API-SECRET-KEY": self.cfg.alpaca_secret,
        }
        params = {
            "symbols": ",".join(symbols),
            "timeframe": "1Day",
            "start": pd.Timestamp(start, tz="UTC").isoformat(),
            "end": (pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)).isoformat(),
            "adjustment": "all",
            "feed": self.cfg.alpaca_feed,
            "limit": 10000,
            "sort": "asc",
        }
        rows: List[dict] = []
        next_page = None
        while True:
            p = dict(params)
            if next_page:
                p["page_token"] = next_page
            data = request_json("GET", self.BASE, headers=headers, params=p, timeout=self.cfg.http_timeout)
            for symbol, items in data.get("bars", {}).items():
                for b in items:
                    event_time = daily_market_close_utc(pd.Timestamp(b["t"]), "US")
                    complete = event_time <= utcnow()
                    rows.append({
                        "event_time": event_time,
                        "available_time": event_time + pd.Timedelta(minutes=2),
                        "market": "US",
                        "indicator_id": f"US_{symbol}",
                        "raw_value": safe_float(b.get("c")),
                        "source": "alpaca",
                        "source_updated_at": event_time,
                        "is_complete": complete,
                        "is_stale": False,
                        "quality_flag": "OK" if complete else "PARTIAL",
                        "metadata": json.dumps({
                            "open": b.get("o"), "high": b.get("h"), "low": b.get("l"),
                            "close": b.get("c"), "volume": b.get("v"), "vwap": b.get("vw"),
                            "feed": self.cfg.alpaca_feed,
                        }),
                    })
            next_page = data.get("next_page_token")
            if not next_page:
                break
        return ensure_schema(pd.DataFrame(rows))


class UpbitCollector:
    BASE = "https://api.upbit.com/v1/candles/days"

    def __init__(self, cfg: Settings):
        self.cfg = cfg

    def collect_daily(self, market: str, start: date, end: date) -> pd.DataFrame:
        rows = []
        to = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)
        oldest_needed = pd.Timestamp(start, tz="UTC")
        while True:
            data = request_json(
                "GET", self.BASE,
                params={"market": market, "count": 200, "to": to.isoformat()},
                timeout=self.cfg.http_timeout,
            )
            if not data:
                break
            oldest_seen = None
            for b in data:
                start_ts = pd.Timestamp(b["candle_date_time_utc"], tz="UTC")
                event_time = start_ts + pd.Timedelta(days=1)
                oldest_seen = start_ts if oldest_seen is None else min(oldest_seen, start_ts)
                if event_time < oldest_needed:
                    continue
                complete = event_time <= utcnow()
                rows.append({
                    "event_time": event_time,
                    "available_time": event_time + pd.Timedelta(seconds=10),
                    "market": "BTC",
                    "indicator_id": "BTC_KRW",
                    "raw_value": safe_float(b.get("trade_price")),
                    "source": "upbit",
                    "source_updated_at": pd.Timestamp(b.get("timestamp"), unit="ms", tz="UTC"),
                    "is_complete": complete,
                    "is_stale": False,
                    "quality_flag": "OK" if complete else "PARTIAL",
                    "metadata": json.dumps({
                        "market": market,
                        "open": b.get("opening_price"), "high": b.get("high_price"),
                        "low": b.get("low_price"), "close": b.get("trade_price"),
                        "volume": b.get("candle_acc_trade_volume"),
                    }),
                })
            if oldest_seen is None or oldest_seen <= oldest_needed:
                break
            to = oldest_seen
            time.sleep(0.12)
        return ensure_schema(pd.DataFrame(rows))


class FredCollector:
    BASE = "https://api.stlouisfed.org/fred/series/observations"

    def __init__(self, cfg: Settings):
        self.cfg = cfg

    def collect_series(self, series_id: str, indicator_id: str, start: date, end: date) -> pd.DataFrame:
        if not self.cfg.fred_key:
            raise RuntimeError("FRED_API_KEY missing")
        data = request_json("GET", self.BASE, params={
            "series_id": series_id,
            "api_key": self.cfg.fred_key,
            "file_type": "json",
            "observation_start": str(start),
            "observation_end": str(end),
            "sort_order": "asc",
        }, timeout=self.cfg.http_timeout)
        rows = []
        for o in data.get("observations", []):
            value = safe_float(o.get("value"))
            if math.isnan(value):
                continue
            obs = pd.Timestamp(o["date"])
            available = (obs + pd.Timedelta(days=self.cfg.macro_us_lag_days)).tz_localize("UTC")
            complete = available <= utcnow()
            rows.append({
                "event_time": obs.tz_localize("UTC"),
                "available_time": available,
                "market": "US",
                "indicator_id": indicator_id,
                "raw_value": value,
                "source": "fred",
                "source_updated_at": available,
                "is_complete": complete,
                "is_stale": False,
                "quality_flag": "OK" if complete else "EMBARGOED",
                "metadata": json.dumps({"fred_series_id": series_id, "lag_days": self.cfg.macro_us_lag_days}),
            })
        return ensure_schema(pd.DataFrame(rows))


class EcosCollector:
    BASE = "https://ecos.bok.or.kr/api/StatisticSearch"

    def __init__(self, cfg: Settings):
        self.cfg = cfg

    def collect_series(self, *, stat_code: str, cycle: str, item_code1: str,
                       indicator_id: str, start: date, end: date) -> pd.DataFrame:
        if not self.cfg.ecos_key:
            raise RuntimeError("BOK_ECOS_API_KEY missing")
        if not (stat_code and cycle and item_code1):
            raise RuntimeError(f"ECOS mapping missing for {indicator_id}")

        def fmt(d: date) -> str:
            return pd.Timestamp(d).strftime("%Y%m%d") if cycle.upper() == "D" else pd.Timestamp(d).strftime("%Y%m")

        url = (
            f"{self.BASE}/{self.cfg.ecos_key}/json/kr/1/1000/"
            f"{stat_code}/{cycle}/{fmt(start)}/{fmt(end)}/{item_code1}"
        )
        data = request_json("GET", url, timeout=self.cfg.http_timeout)
        rows = []
        for r in (data.get("StatisticSearch") or {}).get("row", []):
            time_str = str(r.get("TIME", ""))
            obs = pd.to_datetime(time_str, format="%Y%m%d", errors="coerce") if cycle.upper() == "D" else pd.to_datetime(time_str, errors="coerce")
            value = safe_float(r.get("DATA_VALUE"))
            if pd.isna(obs) or math.isnan(value):
                continue
            available = (
                pd.Timestamp(datetime(obs.year, obs.month, obs.day, 0, 5, tzinfo=KST))
                + pd.Timedelta(days=self.cfg.macro_kr_lag_days)
            ).tz_convert("UTC")
            complete = available <= utcnow()
            rows.append({
                "event_time": obs.tz_localize("UTC"),
                "available_time": available,
                "market": "KR",
                "indicator_id": indicator_id,
                "raw_value": value,
                "source": "ecos",
                "source_updated_at": available,
                "is_complete": complete,
                "is_stale": False,
                "quality_flag": "OK" if complete else "EMBARGOED",
                "metadata": json.dumps({
                    "stat_code": stat_code, "cycle": cycle, "item_code1": item_code1,
                    "item_name1": r.get("ITEM_NAME1"), "unit": r.get("UNIT_NAME"),
                    "lag_days": self.cfg.macro_kr_lag_days,
                }, ensure_ascii=False),
            })
        return ensure_schema(pd.DataFrame(rows))


class FdrCollector:
    def __init__(self, cfg: Settings):
        self.cfg = cfg

    def collect_daily(self, symbol: str, indicator_id: str, market: str, start: date, end: date) -> pd.DataFrame:
        try:
            import FinanceDataReader as fdr
        except ImportError as e:
            raise RuntimeError("FinanceDataReader not installed") from e
        df = fdr.DataReader(symbol, str(start), str(end))
        if df is None or df.empty:
            return ensure_schema(pd.DataFrame())
        close_col = "Close" if "Close" in df.columns else df.columns[-1]
        rows = []
        for idx, r in df.iterrows():
            event_time = daily_market_close_utc(pd.Timestamp(idx), market)
            rows.append({
                "event_time": event_time,
                "available_time": event_time + pd.Timedelta(minutes=10),
                "market": market,
                "indicator_id": indicator_id,
                "raw_value": safe_float(r[close_col]),
                "source": "finance-datareader",
                "source_updated_at": event_time,
                "is_complete": event_time <= utcnow(),
                "is_stale": False,
                "quality_flag": "FALLBACK",
                "metadata": json.dumps({"symbol": symbol}),
            })
        return ensure_schema(pd.DataFrame(rows))


PRICE_IDS = {"US_SPY", "US_QQQ", "US_SOXX", "KR_KOSPI", "KR_KOSDAQ", "BTC_KRW", "KR_USDKRW"}
RATE_IDS = {"US_DGS2", "US_DGS10", "KR_KR3Y", "KR_KR10Y"}


def zscore(s: pd.Series, window: int) -> pd.Series:
    mean = s.rolling(window, min_periods=max(5, window // 3)).mean()
    std = s.rolling(window, min_periods=max(5, window // 3)).std(ddof=0)
    return (s - mean) / std.replace(0, np.nan)


def build_univariate_features(raw: pd.DataFrame) -> pd.DataFrame:
    out = []
    for indicator_id, g in raw.groupby("indicator_id"):
        g = g[g["is_complete"]].dropna(subset=["raw_value", "event_time"]).copy()
        if g.empty:
            continue
        g = g.sort_values("event_time").drop_duplicates("event_time", keep="last")
        s = g.set_index("event_time")["raw_value"].astype(float)
        avail = g.set_index("event_time")["available_time"]
        fmap: Dict[str, pd.Series] = {}
        if indicator_id in PRICE_IDS:
            for n in (1, 5, 20):
                fmap[f"{indicator_id}_RET_{n}D"] = s.pct_change(n)
            fmap[f"{indicator_id}_MA20_DIST"] = s / s.rolling(20).mean() - 1
            fmap[f"{indicator_id}_RV20"] = s.pct_change().rolling(20).std(ddof=0) * np.sqrt(252)
            fmap[f"{indicator_id}_Z60"] = zscore(s, 60)
        if indicator_id in RATE_IDS:
            fmap[f"{indicator_id}_CHG_1D"] = s.diff(1)
            fmap[f"{indicator_id}_CHG_5D"] = s.diff(5)
            fmap[f"{indicator_id}_Z60"] = zscore(s, 60)
        for name, fs in fmap.items():
            for ts, val in fs.dropna().items():
                a = avail.loc[ts]
                out.append({
                    "event_time": ts,
                    "available_time": a,
                    "market": indicator_id.split("_", 1)[0],
                    "feature_name": name,
                    "feature_value": float(val),
                    "source": "derived",
                    "is_stale": freshness_flag(a, 240),
                    "quality_flag": "OK" if a <= utcnow() else "EMBARGOED",
                    "inputs": indicator_id,
                })
    return pd.DataFrame(out)


def build_cross_asset_features(raw: pd.DataFrame) -> pd.DataFrame:
    specs = [
        ("QQQ_SPY_RATIO", "US_QQQ", "US_SPY", "US"),
        ("SOXX_QQQ_RATIO", "US_SOXX", "US_QQQ", "US"),
        ("KOSDAQ_KOSPI_RATIO", "KR_KOSDAQ", "KR_KOSPI", "KR"),
    ]
    rows = []
    work = raw[raw["is_complete"]].copy()
    work["trade_date"] = work["event_time"].dt.tz_convert("UTC").dt.date
    for name, a_id, b_id, market in specs:
        a = work[work["indicator_id"] == a_id][["trade_date", "event_time", "available_time", "raw_value"]].rename(
            columns={"event_time": "event_time_a", "available_time": "available_time_a", "raw_value": "a"})
        b = work[work["indicator_id"] == b_id][["trade_date", "event_time", "available_time", "raw_value"]].rename(
            columns={"event_time": "event_time_b", "available_time": "available_time_b", "raw_value": "b"})
        m = a.merge(b, on="trade_date", how="inner").sort_values("trade_date")
        if m.empty:
            continue
        m["ratio"] = m["a"] / m["b"].replace(0, np.nan)
        m["ret5"] = m["ratio"].pct_change(5)
        m["z60"] = zscore(m["ratio"], 60)
        for _, r in m.iterrows():
            event_time = max(r["event_time_a"], r["event_time_b"])
            available_time = max(r["available_time_a"], r["available_time_b"])
            for suffix, val in (("LEVEL", r["ratio"]), ("RET_5D", r["ret5"]), ("Z60", r["z60"])):
                if pd.isna(val):
                    continue
                rows.append({
                    "event_time": event_time,
                    "available_time": available_time,
                    "market": market,
                    "feature_name": f"{name}_{suffix}",
                    "feature_value": float(val),
                    "source": "derived-cross",
                    "is_stale": freshness_flag(available_time, 240),
                    "quality_flag": "OK" if available_time <= utcnow() else "EMBARGOED",
                    "inputs": f"{a_id},{b_id}",
                })
    return pd.DataFrame(rows)


def save_frame(df: pd.DataFrame, base_path: Path) -> None:
    base_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(base_path.with_suffix(".csv"), index=False)
    try:
        df.to_parquet(base_path.with_suffix(".parquet"), index=False)
    except Exception as e:
        LOG.warning("Parquet skipped (%s). CSV was saved.", e)


def source_status(name: str, fn) -> Tuple[pd.DataFrame, dict]:
    t0 = time.time()
    try:
        df = fn()
        return df, {"source": name, "ok": True, "rows": len(df), "elapsed_sec": round(time.time()-t0, 3), "error": None}
    except Exception as e:
        LOG.warning("%s failed: %s", name, e)
        return ensure_schema(pd.DataFrame()), {"source": name, "ok": False, "rows": 0, "elapsed_sec": round(time.time()-t0, 3), "error": str(e)}


def run(cfg: Settings) -> dict:
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    end = utcnow().date()
    start = end - timedelta(days=cfg.lookback_days)
    alpaca, upbit, fred, ecos, fdr = AlpacaCollector(cfg), UpbitCollector(cfg), FredCollector(cfg), EcosCollector(cfg), FdrCollector(cfg)

    jobs = [
        ("alpaca_us_etf", lambda: alpaca.collect_daily(["SPY", "QQQ", "SOXX"], start, end)),
        ("upbit_btc_krw", lambda: upbit.collect_daily("KRW-BTC", start, end)),
        ("fred_dgs2", lambda: fred.collect_series("DGS2", "US_DGS2", start, end)),
        ("fred_dgs10", lambda: fred.collect_series("DGS10", "US_DGS10", start, end)),
        ("fdr_kospi", lambda: fdr.collect_daily("KS11", "KR_KOSPI", "KR", start, end)),
        ("fdr_kosdaq", lambda: fdr.collect_daily("KQ11", "KR_KOSDAQ", "KR", start, end)),
    ]

    if cfg.ecos_key and cfg.ecos_kr3y_stat_code and cfg.ecos_kr3y_item_code1:
        jobs.append(("ecos_kr3y", lambda: ecos.collect_series(stat_code=cfg.ecos_kr3y_stat_code, cycle=cfg.ecos_kr3y_cycle, item_code1=cfg.ecos_kr3y_item_code1, indicator_id="KR_KR3Y", start=start, end=end)))
    else:
        jobs.append(("fdr_kr3y_fallback", lambda: fdr.collect_daily("KR3YT=RR", "KR_KR3Y", "KR", start, end)))

    if cfg.ecos_key and cfg.ecos_kr10y_stat_code and cfg.ecos_kr10y_item_code1:
        jobs.append(("ecos_kr10y", lambda: ecos.collect_series(stat_code=cfg.ecos_kr10y_stat_code, cycle=cfg.ecos_kr10y_cycle, item_code1=cfg.ecos_kr10y_item_code1, indicator_id="KR_KR10Y", start=start, end=end)))
    else:
        jobs.append(("fdr_kr10y_fallback", lambda: fdr.collect_daily("KR10YT=RR", "KR_KR10Y", "KR", start, end)))

    if cfg.ecos_key and cfg.ecos_usdkrw_stat_code and cfg.ecos_usdkrw_item_code1:
        jobs.append(("ecos_usdkrw", lambda: ecos.collect_series(stat_code=cfg.ecos_usdkrw_stat_code, cycle=cfg.ecos_usdkrw_cycle, item_code1=cfg.ecos_usdkrw_item_code1, indicator_id="KR_USDKRW", start=start, end=end)))
    else:
        jobs.append(("fdr_usdkrw_fallback", lambda: fdr.collect_daily("USD/KRW", "KR_USDKRW", "KR", start, end)))

    frames, statuses = [], []
    for name, fn in jobs:
        df, status = source_status(name, fn)
        statuses.append(status)
        if not df.empty:
            frames.append(df)

    raw = ensure_schema(pd.concat(frames, ignore_index=True) if frames else pd.DataFrame())
    raw["is_stale"] = raw["available_time"].apply(lambda x: freshness_flag(x, cfg.stale_daily_hours) if pd.notna(x) else True)
    features = pd.concat([build_univariate_features(raw), build_cross_asset_features(raw)], ignore_index=True)
    if not features.empty:
        features["event_time"] = pd.to_datetime(features["event_time"], utc=True)
        features["available_time"] = pd.to_datetime(features["available_time"], utc=True)
        eligible = features[(features["available_time"] <= utcnow()) & (features["quality_flag"] == "OK")].copy()
    else:
        eligible = features.copy()

    save_frame(raw, cfg.data_dir / "raw" / "phase1_raw")
    save_frame(features, cfg.data_dir / "features" / "phase1_features")
    save_frame(eligible, cfg.data_dir / "features" / "phase1_features_eligible")
    latest = raw.sort_values("event_time").groupby("indicator_id", as_index=False).tail(1) if not raw.empty else pd.DataFrame()
    save_frame(latest, cfg.data_dir / "snapshots" / "phase1_latest")

    summary = {
        "run_time_utc": utcnow().isoformat(),
        "lookback_days": cfg.lookback_days,
        "raw_rows": len(raw),
        "feature_rows": len(features),
        "eligible_feature_rows": len(eligible),
        "sources": statuses,
        "credentials_present": {
            "alpaca": bool(cfg.alpaca_key and cfg.alpaca_secret),
            "fred": bool(cfg.fred_key),
            "ecos": bool(cfg.ecos_key),
        },
    }
    with open(cfg.data_dir / "run_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary


def dry_run(cfg: Settings) -> dict:
    return {
        "data_dir": str(cfg.data_dir),
        "lookback_days": cfg.lookback_days,
        "alpaca_credentials_present": bool(cfg.alpaca_key and cfg.alpaca_secret),
        "fred_key_present": bool(cfg.fred_key),
        "ecos_key_present": bool(cfg.ecos_key),
        "alpaca_feed": cfg.alpaca_feed,
        "macro_us_lag_days": cfg.macro_us_lag_days,
        "macro_kr_lag_days": cfg.macro_kr_lag_days,
        "ecos_mappings_configured": {
            "kr3y": bool(cfg.ecos_kr3y_stat_code and cfg.ecos_kr3y_item_code1),
            "kr10y": bool(cfg.ecos_kr10y_stat_code and cfg.ecos_kr10y_item_code1),
            "usdkrw": bool(cfg.ecos_usdkrw_stat_code and cfg.ecos_usdkrw_item_code1),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log-level", default=os.getenv("LOG_LEVEL", "INFO"))
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s | %(message)s")
    cfg = Settings.from_env()
    result = dry_run(cfg) if args.dry_run else run(cfg)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
