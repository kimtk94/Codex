from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv


UNIVERSE = {
    "US_CORE": ["SPY", "QQQ", "IWM", "DIA"],
    "US_SECTOR": ["SMH", "SOXX", "XLF", "XLK", "XLE", "XLI", "XLY", "XLP", "XLV", "XLU"],
    "BTC_CORE": ["BTC-USD"],
    "BTC_ETF": ["IBIT", "FBTC"],
    "CRYPTO_EQUITY": ["COIN", "MSTR", "MARA", "RIOT", "CLSK"],
    "COMMON": ["^VIX", "^TNX", "DX-Y.NYB", "HYG", "LQD", "TLT", "GLD"],
}
BTC_24_7 = ["BTC-USD"]
BTC_ETF_TICKERS = UNIVERSE["BTC_ETF"]
CRYPTO_EQUITY_TICKERS = UNIVERSE["CRYPTO_EQUITY"]
BTC_PROXY_TICKERS = BTC_ETF_TICKERS + CRYPTO_EQUITY_TICKERS
US_BREADTH_TICKERS = UNIVERSE["US_CORE"] + UNIVERSE["US_SECTOR"]
ALL_TICKERS = sorted(set(sum(UNIVERSE.values(), [])))

GRADE_MAP = {
    "A+": 5.0, "A": 4.8, "A-": 4.5,
    "B+": 4.2, "B": 4.0, "B-": 3.7,
    "C+": 3.4, "C": 3.0, "C-": 2.7,
    "D+": 2.4, "D": 2.0, "D-": 1.7, "F": 1.0,
}
RATING_MAP = {
    "strong buy": 5.0, "buy": 4.0, "hold": 3.0, "neutral": 3.0,
    "sell": 2.0, "strong sell": 1.0,
}
SA_STOCK_COLS = [
    "quant_rating", "value", "growth", "profitability", "momentum", "eps_revision",
    "sa_analyst_rating", "wall_street_rating", "news_sentiment",
]
SA_ETF_COLS = [
    "quant_rating", "momentum", "expenses", "dividends", "risk", "liquidity",
    "sa_analyst_rating", "news_sentiment",
]
ALL_SA_NUMERIC = sorted(set(SA_STOCK_COLS + SA_ETF_COLS))


def as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    output_dir: Path
    sa_csv: Path
    start_date: str
    end_date: str | None
    sa_asof_lag_bdays: int
    sa_required: bool

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "Settings":
        data_root = Path(os.environ.get("KALMAN_DATA_ROOT", "/opt/kalman/data")).expanduser()
        return cls(
            output_dir=Path(
                args.output_dir
                or os.environ.get(
                    "KALMAN_SA_OUTPUT_DIR",
                    str(data_root / "Market_Features" / "sa_us_btc"),
                )
            ).expanduser(),
            sa_csv=Path(
                args.sa_csv
                or os.environ.get(
                    "KALMAN_SA_INPUT_CSV",
                    str(data_root / "SeekingAlpha" / "seeking_alpha_daily.csv"),
                )
            ).expanduser(),
            start_date=args.start_date or os.environ.get("KALMAN_SA_START_DATE", "2022-01-01"),
            end_date=args.end_date or os.environ.get("KALMAN_SA_END_DATE") or None,
            sa_asof_lag_bdays=int(
                args.sa_asof_lag_bdays
                if args.sa_asof_lag_bdays is not None
                else os.environ.get("KALMAN_SA_ASOF_LAG_BDAYS", "0")
            ),
            sa_required=(
                args.sa_required
                if args.sa_required is not None
                else as_bool(os.environ.get("KALMAN_SA_REQUIRED", "false"))
            ),
        )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build Seeking Alpha x US x BTC daily features")
    p.add_argument("--start-date")
    p.add_argument("--end-date")
    p.add_argument("--sa-csv")
    p.add_argument("--output-dir")
    p.add_argument("--sa-asof-lag-bdays", type=int)
    p.add_argument("--sa-required", action=argparse.BooleanOptionalAction, default=None)
    return p.parse_args()


def load_server_env() -> None:
    env_file = Path(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env")).expanduser()
    if env_file.exists():
        load_dotenv(env_file, override=True)


def download_market(
    tickers: list[str],
    start: str,
    end: str | None,
    attempts: int = 3,
) -> pd.DataFrame:
    for attempt in range(1, attempts + 1):
        try:
            raw = yf.download(
                tickers=tickers,
                start=start,
                end=end,
                interval="1d",
                auto_adjust=False,
                repair=True,
                keepna=True,
                ignore_tz=True,
                progress=False,
                group_by="column",
                threads=True,
                timeout=30,
            )
            if raw is None or raw.empty:
                raise RuntimeError("yfinance returned no data")
            break
        except Exception as exc:
            if attempt == attempts:
                raise RuntimeError(
                    f"market download failed after {attempts} attempts: {exc}"
                ) from exc
            time.sleep(2 ** attempt)

    if isinstance(raw.columns, pd.MultiIndex):
        level0 = raw.columns.get_level_values(0)
        key = "Adj Close" if "Adj Close" in level0 else "Close"
        close = raw[key].copy()
    else:
        key = "Adj Close" if "Adj Close" in raw.columns else "Close"
        close = raw[[key]].copy()
        close.columns = [tickers[0]]

    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close.sort_index().replace([np.inf, -np.inf], np.nan).dropna(how="all")


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    avg_up = up.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_down = down.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_up / avg_down.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def zscore(series: pd.Series, window: int = 20) -> pd.Series:
    mean = series.rolling(window, min_periods=window).mean()
    std = series.rolling(window, min_periods=window).std()
    return (series - mean) / std.replace(0, np.nan)


def safe_key(ticker: str) -> str:
    return ticker.replace("^", "").replace("-", "_").replace(".", "_")


def asset_features(
    series: pd.Series,
    ticker: str,
    master_index: pd.DatetimeIndex,
) -> pd.DataFrame:
    px = series.dropna().astype(float).sort_index()
    key = safe_key(ticker)
    annualizer = 365 if ticker in BTC_24_7 else 252
    out = pd.DataFrame(index=px.index)
    ret1 = px.pct_change(fill_method=None)
    ma20 = px.rolling(20, min_periods=20).mean()
    ma50 = px.rolling(50, min_periods=50).mean()

    out[f"{key}_px"] = px
    out[f"{key}_ret_1d"] = ret1
    out[f"{key}_ret_5obs"] = px.pct_change(5, fill_method=None)
    out[f"{key}_ret_20obs"] = px.pct_change(20, fill_method=None)
    out[f"{key}_rsi14"] = rsi(px)
    out[f"{key}_vol20"] = ret1.rolling(20, min_periods=20).std() * np.sqrt(annualizer)
    out[f"{key}_z20"] = zscore(px)
    out[f"{key}_ma20_gap"] = px / ma20 - 1
    out[f"{key}_ma50_gap"] = px / ma50 - 1
    out[f"{key}_above_ma20"] = (px > ma20).where(ma20.notna()).astype(float)
    out[f"{key}_above_ma50"] = (px > ma50).where(ma50.notna()).astype(float)
    return out.reindex(master_index).ffill()


def breadth(
    close: pd.DataFrame,
    trading_index: pd.DatetimeIndex,
    tickers: Iterable[str],
    prefix: str,
    master_index: pd.DatetimeIndex,
) -> pd.DataFrame:
    tickers = [t for t in tickers if t in close.columns]
    if not tickers:
        return pd.DataFrame(index=master_index)

    px = close.reindex(trading_index)[tickers]
    ret1 = px.pct_change(fill_method=None)
    ret5 = px.pct_change(5, fill_method=None)
    ret20 = px.pct_change(20, fill_method=None)
    ma20 = px.rolling(20, min_periods=20).mean()
    ma50 = px.rolling(50, min_periods=50).mean()
    out = pd.DataFrame(index=trading_index)
    out[f"{prefix}_positive_1d_ratio"] = (ret1 > 0).where(ret1.notna()).mean(axis=1)
    out[f"{prefix}_above_ma20_ratio"] = (
        (px > ma20).where(px.notna() & ma20.notna()).mean(axis=1)
    )
    out[f"{prefix}_above_ma50_ratio"] = (
        (px > ma50).where(px.notna() & ma50.notna()).mean(axis=1)
    )
    out[f"{prefix}_median_ret_5obs"] = ret5.median(axis=1, skipna=True)
    out[f"{prefix}_median_ret_20obs"] = ret20.median(axis=1, skipna=True)
    out[f"{prefix}_coverage"] = px.notna().sum(axis=1) / max(len(tickers), 1)
    return out.reindex(master_index).ffill()


def to_score(value: object) -> float:
    if pd.isna(value):
        return np.nan
    if isinstance(value, (int, float, np.number)):
        return float(value)
    text = str(value).strip()
    if text.upper() in GRADE_MAP:
        return GRADE_MAP[text.upper()]
    if text.lower() in RATING_MAP:
        return RATING_MAP[text.lower()]
    try:
        return float(text)
    except Exception:
        return np.nan


def load_sa(path: Path, lag_bdays: int, required: bool) -> pd.DataFrame:
    base = ["date", "ticker", "asset_type"] + ALL_SA_NUMERIC
    if not path.exists():
        if required:
            raise FileNotFoundError(f"required Seeking Alpha CSV missing: {path}")
        print(f"[WARN] SA CSV missing; continuing market-only: {path}")
        return pd.DataFrame(columns=base)

    sa = pd.read_csv(path)
    sa.columns = [c.strip().lower() for c in sa.columns]
    if "valuation" in sa.columns and "value" not in sa.columns:
        sa = sa.rename(columns={"valuation": "value"})
    missing = {"date", "ticker"} - set(sa.columns)
    if missing:
        raise ValueError(f"SA CSV missing required columns: {sorted(missing)}")

    sa["date"] = pd.to_datetime(sa["date"], errors="coerce").dt.tz_localize(None)
    sa = sa.dropna(subset=["date"])
    if lag_bdays:
        sa["date"] = sa["date"] + pd.offsets.BDay(lag_bdays)
    sa["ticker"] = sa["ticker"].astype(str).str.upper().str.strip()
    if "asset_type" not in sa.columns:
        sa["asset_type"] = np.where(sa["ticker"].isin(BTC_ETF_TICKERS), "ETF", "STOCK")
    else:
        sa["asset_type"] = sa["asset_type"].astype(str).str.upper().str.strip()
    for col in ALL_SA_NUMERIC:
        sa[col] = sa[col].map(to_score) if col in sa.columns else np.nan
    return sa.sort_values(["ticker", "date"]).drop_duplicates(
        ["ticker", "date"], keep="last"
    )


def aggregate_sa(df: pd.DataFrame, prefix: str, fields: Iterable[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    x = df.copy().sort_values(["ticker", "date"])
    for col in ALL_SA_NUMERIC:
        if col in x.columns:
            x[f"{col}_delta_1obs"] = x.groupby("ticker")[col].diff(1)

    g = x.groupby("date")
    out = pd.DataFrame(index=sorted(x["date"].unique()))
    for col in fields:
        if col in x.columns:
            out[f"{prefix}_{col}_mean"] = g[col].mean()
            out[f"{prefix}_{col}_median"] = g[col].median()

    if "quant_rating" in x.columns:
        out[f"{prefix}_quant_buy_ratio"] = g["quant_rating"].apply(
            lambda s: (s >= 4.0).mean() if s.notna().any() else np.nan
        )
        out[f"{prefix}_quant_strongbuy_ratio"] = g["quant_rating"].apply(
            lambda s: (s >= 4.5).mean() if s.notna().any() else np.nan
        )
    if "momentum" in x.columns:
        out[f"{prefix}_momentum_A_ratio"] = g["momentum"].apply(
            lambda s: (s >= 4.5).mean() if s.notna().any() else np.nan
        )
    if "eps_revision" in x.columns:
        out[f"{prefix}_epsrev_A_ratio"] = g["eps_revision"].apply(
            lambda s: (s >= 4.5).mean() if s.notna().any() else np.nan
        )

    for col, short in [
        ("quant_rating", "quant"),
        ("momentum", "momentum"),
        ("eps_revision", "epsrev"),
    ]:
        dcol = f"{col}_delta_1obs"
        if dcol in x.columns:
            out[f"{prefix}_{short}_upgrade_breadth"] = g[dcol].apply(
                lambda s: (
                    (s > 0).mean() - (s < 0).mean()
                    if s.notna().any()
                    else np.nan
                )
            )
    out[f"{prefix}_ticker_count"] = g["ticker"].nunique()
    return out


def sa_features(sa: pd.DataFrame, master_index: pd.DatetimeIndex) -> pd.DataFrame:
    if sa.empty:
        return pd.DataFrame(index=master_index)

    btc_etf = sa[sa["ticker"].isin(BTC_ETF_TICKERS)]
    btc_equity = sa[sa["ticker"].isin(CRYPTO_EQUITY_TICKERS)]
    us_stock = sa[
        (~sa["ticker"].isin(BTC_PROXY_TICKERS))
        & (sa["asset_type"] == "STOCK")
    ]

    parts = [
        aggregate_sa(us_stock, "sa_us_stock", SA_STOCK_COLS),
        aggregate_sa(btc_equity, "sa_btc_equity", SA_STOCK_COLS),
        aggregate_sa(btc_etf, "sa_btc_etf", SA_ETF_COLS),
    ]
    parts = [p for p in parts if not p.empty]
    if not parts:
        return pd.DataFrame(index=master_index)
    return pd.concat(parts, axis=1).sort_index().reindex(master_index).ffill()


def rolling_z(series: pd.Series, window: int = 60) -> pd.Series:
    mean = series.rolling(window, min_periods=window).mean()
    std = series.rolling(window, min_periods=window).std()
    return (series - mean) / std.replace(0, np.nan)


def add_composite(df: pd.DataFrame, cols: Iterable[str], name: str) -> None:
    present = [c for c in cols if c in df.columns]
    z = pd.DataFrame(index=df.index)
    for col in present:
        z[col] = rolling_z(df[col])
    df[name] = z.mean(axis=1, skipna=True) if present else np.nan
    df[f"{name}_coverage"] = z.notna().sum(axis=1) / max(len(present), 1)


def atomic_csv(df: pd.DataFrame, path: Path, index: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=index, encoding="utf-8-sig")
    os.replace(tmp, path)


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def json_safe(value: object) -> object:
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value


def build(settings: Settings) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    close = download_market(ALL_TICKERS, settings.start_date, settings.end_date)
    if "BTC-USD" not in close.columns or close["BTC-USD"].dropna().empty:
        raise RuntimeError("BTC-USD data missing; master calendar cannot be built")

    btc_index = close["BTC-USD"].dropna().index
    us_index = (
        close["SPY"].dropna().index
        if "SPY" in close.columns and not close["SPY"].dropna().empty
        else close[[t for t in UNIVERSE["US_CORE"] if t in close.columns]]
        .dropna(how="all")
        .index
    )
    master = pd.date_range(btc_index.min().normalize(), btc_index.max().normalize(), freq="D")

    parts = [
        asset_features(close[ticker], ticker, master)
        for ticker in close.columns
        if close[ticker].notna().sum() >= 5
    ]
    market = pd.concat(parts, axis=1)

    flags = pd.DataFrame(index=master)
    flags["us_market_open"] = master.isin(us_index).astype(int)
    flags["btc_market_open"] = 1
    last_us = pd.Series(pd.NaT, index=master, dtype="datetime64[ns]")
    mask = last_us.index.isin(us_index)
    last_us.loc[mask] = last_us.index[mask]
    last_us = last_us.ffill()
    flags["us_data_age_days"] = (
        pd.Series(master, index=master) - last_us
    ).dt.days.astype(float)

    us_breadth = breadth(close, us_index, US_BREADTH_TICKERS, "us_etf_breadth", master)
    btc_breadth = breadth(close, us_index, BTC_PROXY_TICKERS, "btc_proxy_breadth", master)

    regime_native = pd.DataFrame(index=us_index)
    for a, b, name in [
        ("HYG", "LQD", "credit_risk_on_ratio"),
        ("QQQ", "SPY", "qqq_spy_ratio"),
    ]:
        if a in close.columns and b in close.columns:
            ratio = close[a].reindex(us_index) / close[b].reindex(us_index)
            regime_native[name] = ratio
            regime_native[f"{name}_ret20obs"] = ratio.pct_change(20, fill_method=None)
    regime = regime_native.reindex(master).ffill()

    if "SPY" in close.columns:
        btc_daily = close["BTC-USD"].reindex(master)
        spy_asof = close["SPY"].reindex(master).ffill()
        ratio = btc_daily / spy_asof
        regime["btc_spy_ratio_cal"] = ratio
        regime["btc_spy_ratio_ret20cal"] = ratio.pct_change(20, fill_method=None)

    sa = load_sa(settings.sa_csv, settings.sa_asof_lag_bdays, settings.sa_required)
    features = pd.concat(
        [market, flags, us_breadth, btc_breadth, regime, sa_features(sa, master)],
        axis=1,
    ).sort_index()
    features.index.name = "date"

    targets = pd.DataFrame(index=master)
    btc = close["BTC-USD"].dropna().sort_index()
    targets["target_btc_fwd_1d"] = (btc.shift(-1) / btc - 1).reindex(master)
    targets["target_btc_fwd_5d"] = (btc.shift(-5) / btc - 1).reindex(master)
    if "SPY" in close.columns:
        spy = close["SPY"].dropna().sort_index()
        targets["target_spy_fwd_1td"] = (spy.shift(-1) / spy - 1).reindex(master)
        targets["target_spy_fwd_5td"] = (spy.shift(-5) / spy - 1).reindex(master)
    targets.index.name = "date"

    add_composite(
        features,
        [
            "us_etf_breadth_above_ma20_ratio",
            "us_etf_breadth_above_ma50_ratio",
            "qqq_spy_ratio_ret20obs",
            "credit_risk_on_ratio_ret20obs",
        ],
        "US_MARKET_COMPOSITE_V1",
    )
    add_composite(
        features,
        [
            "btc_proxy_breadth_above_ma20_ratio",
            "btc_proxy_breadth_above_ma50_ratio",
            "btc_proxy_breadth_median_ret_20obs",
            "btc_spy_ratio_ret20cal",
        ],
        "BTC_MARKET_COMPOSITE_V1",
    )
    add_composite(
        features,
        [
            "sa_us_stock_quant_rating_mean",
            "sa_us_stock_momentum_mean",
            "sa_us_stock_eps_revision_mean",
            "sa_us_stock_quant_upgrade_breadth",
        ],
        "US_SA_COMPOSITE_V1",
    )
    add_composite(
        features,
        [
            "sa_btc_equity_quant_rating_mean",
            "sa_btc_equity_momentum_mean",
            "sa_btc_equity_eps_revision_mean",
            "sa_btc_equity_quant_upgrade_breadth",
        ],
        "BTC_SA_EQUITY_COMPOSITE_V1",
    )
    add_composite(
        features,
        [
            "sa_btc_etf_quant_rating_mean",
            "sa_btc_etf_momentum_mean",
            "sa_btc_etf_risk_mean",
            "sa_btc_etf_liquidity_mean",
        ],
        "BTC_SA_ETF_COMPOSITE_V1",
    )

    schema = pd.DataFrame(
        {"feature": features.columns, "group": "FEATURE", "role": "FEATURE"}
    )
    target_schema = pd.DataFrame(
        {"feature": targets.columns, "group": "TARGET", "role": "TARGET"}
    )
    schema = pd.concat([schema, target_schema], ignore_index=True)

    meta = {
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "market_last_date": master.max().date().isoformat(),
        "sa_input_path": str(settings.sa_csv),
        "sa_input_exists": settings.sa_csv.exists(),
        "sa_rows": int(len(sa)),
        "sa_tickers": int(sa["ticker"].nunique()) if not sa.empty else 0,
        "feature_rows": int(len(features)),
        "feature_cols": int(features.shape[1]),
    }
    return features, targets, schema, meta


def save(
    settings: Settings,
    features: pd.DataFrame,
    targets: pd.DataFrame,
    schema: pd.DataFrame,
    meta: dict[str, object],
) -> None:
    out = settings.output_dir
    atomic_csv(features, out / "us_btc_sa_features_X_daily.csv")
    atomic_csv(targets, out / "us_btc_targets_y_daily.csv")
    atomic_csv(
        pd.concat([features, targets], axis=1),
        out / "us_btc_sa_dataset_combined_daily.csv",
    )
    atomic_csv(schema, out / "us_btc_sa_feature_schema.csv", index=False)

    latest = {
        k: json_safe(v)
        for k, v in features.tail(1).reset_index().iloc[0].to_dict().items()
    }
    atomic_text(
        out / "us_btc_sa_features_latest.json",
        json.dumps(latest, ensure_ascii=False, indent=2, allow_nan=False),
    )
    atomic_text(
        out / "us_btc_sa_run_status.json",
        json.dumps(meta, ensure_ascii=False, indent=2, allow_nan=False),
    )


def main() -> None:
    load_server_env()
    settings = Settings.from_args(parse_args())
    print(f"[SA-US-BTC] output={settings.output_dir}")
    print(
        f"[SA-US-BTC] sa_csv={settings.sa_csv} "
        f"required={settings.sa_required} lag_bdays={settings.sa_asof_lag_bdays}"
    )
    features, targets, schema, meta = build(settings)
    save(settings, features, targets, schema, meta)
    print(
        f"[SA-US-BTC] OK rows={len(features)} features={features.shape[1]} "
        f"market_last_date={meta['market_last_date']}"
    )


if __name__ == "__main__":
    main()
