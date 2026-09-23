from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


NY = ZoneInfo("America/New_York")
UTC = timezone.utc
ALPACA_BARS_URL = "https://data.alpaca.markets/v2/stocks/{symbol}/bars"
SCHEMA_VERSION = "kalman-open-revalidation-backtest-v1"


@dataclass(frozen=True)
class Policy:
    name: str
    latency_minutes: int
    rule: str


POLICIES = (
    Policy("OPEN_NEG_0BP_0M", 0, "position_return_open<=0"),
    Policy("OPEN_NEG_20BP_0M", 0, "position_return_open<=-0.002"),
    Policy("OPEN_FLIP_0M", 0, "prev_close_positive_and_open_nonpositive"),
    Policy("OPEN_NEG_5M_CONFIRM", 5, "open_nonpositive_and_momentum_5m_nonpositive"),
    Policy("OPEN_FLIP_5M_CONFIRM", 5, "prev_close_positive_open_nonpositive_momentum_5m_nonpositive"),
    Policy("OPEN_GAP_5M_CONFIRM", 5, "negative_gap_nonpositive_at_5m_and_momentum_5m_nonpositive"),
    Policy("OPEN_GIVEBACK_5M", 5, "prev_close_ge_50bp_giveback_ge_70bp_momentum_5m_nonpositive"),
    Policy("OPEN_NEG_15M_CONFIRM", 15, "open_nonpositive_and_momentum_15m_nonpositive"),
)


def _iso_utc(value: Any) -> str:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.isoformat()


def _to_utc(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def _to_et(value: Any) -> pd.Timestamp:
    return _to_utc(value).tz_convert(NY)


def _effective_bar_close(value: Any) -> pd.Timestamp:
    # R5 timestamps label the 60m bar start. The final US regular-session
    # bucket is truncated at 16:00 ET, so do not push a 15:30 bucket to 16:30.
    start_utc = _to_utc(value)
    start_et = start_utc.tz_convert(NY)
    candidate_et = start_et + pd.Timedelta(hours=1)
    session_close_et = pd.Timestamp(
        datetime.combine(start_et.date(), dt_time(16, 0), tzinfo=NY)
    )
    effective_et = min(candidate_et, session_close_et)
    return effective_et.tz_convert("UTC")


def _cross_session(entry_timestamp: Any, exit_timestamp: Any) -> bool:
    return _to_et(entry_timestamp).date() < _to_et(exit_timestamp).date()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _alpaca_credentials() -> tuple[str, str]:
    key = (
        os.environ.get("ALPACA_API_KEY")
        or os.environ.get("APCA_API_KEY_ID")
        or ""
    ).strip()
    secret = (
        os.environ.get("ALPACA_API_SECRET")
        or os.environ.get("APCA_API_SECRET_KEY")
        or ""
    ).strip()
    if not key or not secret:
        raise RuntimeError(
            "Alpaca credentials missing: set ALPACA_API_KEY/ALPACA_API_SECRET "
            "or APCA_API_KEY_ID/APCA_API_SECRET_KEY"
        )
    return key, secret


def _session_window_utc(entry_day: date, exit_day: date) -> tuple[pd.Timestamp, pd.Timestamp]:
    start_local = datetime.combine(entry_day, dt_time(9, 20), tzinfo=NY)
    end_local = datetime.combine(exit_day, dt_time(16, 10), tzinfo=NY)
    return pd.Timestamp(start_local).tz_convert("UTC"), pd.Timestamp(end_local).tz_convert("UTC")


def _alpaca_request_json(
    url: str,
    *,
    key: str,
    secret: str,
    max_retries: int = 6,
) -> dict[str, Any]:
    headers = {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
        "User-Agent": "KalmanOpenRevalidation/1.0",
    }
    for attempt in range(max_retries):
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 429 and attempt + 1 < max_retries:
                retry_after = exc.headers.get("Retry-After")
                sleep_seconds = float(retry_after) if retry_after else min(30.0, 1.5 ** (attempt + 1))
                time.sleep(sleep_seconds)
                continue
            if 500 <= exc.code < 600 and attempt + 1 < max_retries:
                time.sleep(min(20.0, 1.5 ** (attempt + 1)))
                continue
            raise RuntimeError(f"Alpaca HTTP {exc.code}: {body[:500]}") from exc
        except urllib.error.URLError as exc:
            if attempt + 1 >= max_retries:
                raise RuntimeError(f"Alpaca request failed: {exc}") from exc
            time.sleep(min(20.0, 1.5 ** (attempt + 1)))
    raise RuntimeError("Alpaca request exhausted retries")


def _fetch_alpaca_1m(
    symbol: str,
    *,
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
    feed: str,
) -> pd.DataFrame:
    key, secret = _alpaca_credentials()
    rows: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        query = {
            "timeframe": "1Min",
            "start": start_utc.isoformat(),
            "end": end_utc.isoformat(),
            "adjustment": "all",
            "feed": feed,
            "limit": "10000",
            "sort": "asc",
        }
        if page_token:
            query["page_token"] = page_token
        url = ALPACA_BARS_URL.format(symbol=urllib.parse.quote(symbol, safe=""))
        payload = _alpaca_request_json(
            url + "?" + urllib.parse.urlencode(query),
            key=key,
            secret=secret,
        )
        bars = payload.get("bars") or []
        rows.extend(bars)
        page_token = payload.get("next_page_token")
        if not page_token:
            break

    if not rows:
        return pd.DataFrame(
            columns=["timestamp", "open", "high", "low", "close", "volume", "trade_count", "vwap"]
        )

    out = pd.DataFrame(
        {
            "timestamp": [r.get("t") for r in rows],
            "open": [r.get("o") for r in rows],
            "high": [r.get("h") for r in rows],
            "low": [r.get("l") for r in rows],
            "close": [r.get("c") for r in rows],
            "volume": [r.get("v") for r in rows],
            "trade_count": [r.get("n") for r in rows],
            "vwap": [r.get("vw") for r in rows],
        }
    )
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    for col in ["open", "high", "low", "close", "volume", "trade_count", "vwap"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return (
        out.dropna(subset=["timestamp", "open", "close"])
        .sort_values("timestamp")
        .drop_duplicates("timestamp", keep="last")
        .reset_index(drop=True)
    )


def _cache_path(cache_dir: Path, symbol: str, entry_day: date, exit_day: date, feed: str) -> Path:
    safe = symbol.upper().replace("/", "-").replace(".", "-")
    return cache_dir / feed / safe / f"{entry_day.isoformat()}__{exit_day.isoformat()}.parquet"


def load_or_fetch_session_window(
    symbol: str,
    *,
    entry_day: date,
    exit_day: date,
    cache_dir: Path,
    feed: str,
    refresh: bool = False,
) -> pd.DataFrame:
    path = _cache_path(cache_dir, symbol, entry_day, exit_day, feed)
    if path.is_file() and not refresh:
        out = pd.read_parquet(path)
        out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
        return out.sort_values("timestamp").reset_index(drop=True)

    start_utc, end_utc = _session_window_utc(entry_day, exit_day)
    out = _fetch_alpaca_1m(
        symbol,
        start_utc=start_utc,
        end_utc=end_utc,
        feed=feed,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(path, index=False)
    return out


def _last_completed_close(frame: pd.DataFrame, effective_ts: pd.Timestamp) -> float | None:
    z = frame.loc[
        (frame["timestamp"] < effective_ts)
        & (frame["timestamp"] >= effective_ts - pd.Timedelta(minutes=10))
    ]
    if z.empty:
        return None
    value = float(z.iloc[-1]["close"])
    return value if math.isfinite(value) and value > 0 else None


def _first_open_at_or_after(
    session: pd.DataFrame,
    *,
    local_hour: int,
    local_minute: int,
    tolerance_minutes: int = 3,
) -> float | None:
    if session.empty:
        return None
    local = session["timestamp"].dt.tz_convert(NY)
    target_date = local.iloc[0].date()
    target = pd.Timestamp(datetime.combine(target_date, dt_time(local_hour, local_minute), tzinfo=NY))
    target_utc = target.tz_convert("UTC")
    z = session.loc[
        (session["timestamp"] >= target_utc)
        & (session["timestamp"] <= target_utc + pd.Timedelta(minutes=tolerance_minutes))
    ]
    if z.empty:
        return None
    value = float(z.iloc[0]["open"])
    return value if math.isfinite(value) and value > 0 else None


def extract_revalidation_features(
    bars: pd.DataFrame,
    *,
    entry_timestamp: Any,
    exit_timestamp: Any,
) -> dict[str, Any] | None:
    if bars.empty:
        return None

    frame = bars.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["timestamp"]).sort_values("timestamp")
    if frame.empty:
        return None

    entry_ts = _to_utc(entry_timestamp)
    exit_ts = _to_utc(exit_timestamp)
    entry_effective = _effective_bar_close(entry_ts)
    fixed4_effective = _effective_bar_close(exit_ts)
    entry_price = _last_completed_close(frame, entry_effective)
    fixed4_price = _last_completed_close(frame, fixed4_effective)
    if entry_price is None or fixed4_price is None:
        return None

    entry_day = _to_et(entry_ts).date()
    next_session_day = _to_et(exit_ts).date()
    local = frame["timestamp"].dt.tz_convert(NY)
    local_dates = local.dt.date
    local_times = local.dt.time

    prior_session = frame.loc[
        (local_dates == entry_day)
        & (local_times >= dt_time(9, 30))
        & (local_times < dt_time(16, 0))
    ]
    next_session = frame.loc[
        (local_dates == next_session_day)
        & (local_times >= dt_time(9, 30))
        & (local_times < dt_time(16, 0))
    ]
    if prior_session.empty or next_session.empty:
        return None

    prev_close = float(prior_session.iloc[-1]["close"])
    open_0 = _first_open_at_or_after(next_session, local_hour=9, local_minute=30)
    open_5 = _first_open_at_or_after(next_session, local_hour=9, local_minute=35)
    open_15 = _first_open_at_or_after(next_session, local_hour=9, local_minute=45)
    if any(x is None for x in (open_0, open_5, open_15)):
        return None

    assert open_0 is not None and open_5 is not None and open_15 is not None
    return {
        "entry_effective_ts": entry_effective,
        "fixed4_effective_ts": fixed4_effective,
        "entry_price_iex": entry_price,
        "fixed4_exit_price_iex": fixed4_price,
        "prev_close_price_iex": prev_close,
        "open_0_price_iex": open_0,
        "open_5_price_iex": open_5,
        "open_15_price_iex": open_15,
        "position_return_prev_close": prev_close / entry_price - 1.0,
        "position_return_open": open_0 / entry_price - 1.0,
        "position_return_5m": open_5 / entry_price - 1.0,
        "position_return_15m": open_15 / entry_price - 1.0,
        "overnight_gap_return": open_0 / prev_close - 1.0,
        "open_momentum_5m": open_5 / open_0 - 1.0,
        "open_momentum_15m": open_15 / open_0 - 1.0,
        "giveback_prev_close_to_5m": (prev_close / entry_price - 1.0) - (open_5 / entry_price - 1.0),
        "reconstructed_fixed4_raw_return": fixed4_price / entry_price - 1.0,
    }


def policy_trigger(policy: Policy, row: pd.Series | dict[str, Any]) -> bool:
    get = row.get
    pos_prev = float(get("position_return_prev_close"))
    pos_open = float(get("position_return_open"))
    pos_5 = float(get("position_return_5m"))
    gap = float(get("overnight_gap_return"))
    mom5 = float(get("open_momentum_5m"))
    mom15 = float(get("open_momentum_15m"))
    giveback5 = float(get("giveback_prev_close_to_5m"))

    if policy.name == "OPEN_NEG_0BP_0M":
        return pos_open <= 0.0
    if policy.name == "OPEN_NEG_20BP_0M":
        return pos_open <= -0.002
    if policy.name == "OPEN_FLIP_0M":
        return pos_prev > 0.0 and pos_open <= 0.0
    if policy.name == "OPEN_NEG_5M_CONFIRM":
        return pos_open <= 0.0 and mom5 <= 0.0
    if policy.name == "OPEN_FLIP_5M_CONFIRM":
        return pos_prev > 0.0 and pos_open <= 0.0 and mom5 <= 0.0
    if policy.name == "OPEN_GAP_5M_CONFIRM":
        return gap < 0.0 and pos_5 <= 0.0 and mom5 <= 0.0
    if policy.name == "OPEN_GIVEBACK_5M":
        return pos_prev >= 0.005 and giveback5 >= 0.007 and mom5 <= 0.0
    if policy.name == "OPEN_NEG_15M_CONFIRM":
        return pos_open <= 0.0 and mom15 <= 0.0
    raise ValueError(f"unknown policy: {policy.name}")


def candidate_exit_price(policy: Policy, row: pd.Series | dict[str, Any]) -> float:
    if policy.latency_minutes == 0:
        return float(row.get("open_0_price_iex"))
    if policy.latency_minutes == 5:
        return float(row.get("open_5_price_iex"))
    if policy.latency_minutes == 15:
        return float(row.get("open_15_price_iex"))
    raise ValueError(policy.latency_minutes)


def _max_drawdown(returns: pd.Series) -> float | None:
    r = pd.to_numeric(returns, errors="coerce").dropna().astype(float)
    if r.empty:
        return None
    equity = (1.0 + r).cumprod()
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min())


def _metrics(frame: pd.DataFrame, return_col: str) -> dict[str, Any]:
    z = frame.sort_values(["entry_timestamp", "symbol"]).copy()
    r = pd.to_numeric(z[return_col], errors="coerce").dropna().astype(float)
    if r.empty:
        return {
            "trades": 0,
            "cum_return": None,
            "log_growth": None,
            "mdd": None,
            "mean_trade_return": None,
            "median_trade_return": None,
            "win_rate": None,
        }
    clipped = r.clip(lower=-0.999999)
    return {
        "trades": int(len(r)),
        "cum_return": float((1.0 + r).prod() - 1.0),
        "log_growth": float(np.log1p(clipped).sum()),
        "mdd": _max_drawdown(r),
        "mean_trade_return": float(r.mean()),
        "median_trade_return": float(r.median()),
        "win_rate": float((r > 0).mean()),
    }


def _daily_log_delta(frame: pd.DataFrame, candidate_col: str) -> pd.Series:
    z = frame.copy()
    z["entry_day_et"] = pd.to_datetime(z["entry_timestamp"], utc=True).dt.tz_convert(NY).dt.date
    base_daily = z.groupby("entry_day_et")["net_return"].sum().clip(lower=-0.999999)
    cand_daily = z.groupby("entry_day_et")[candidate_col].sum().clip(lower=-0.999999)
    idx = base_daily.index.union(cand_daily.index)
    base_daily = base_daily.reindex(idx, fill_value=0.0)
    cand_daily = cand_daily.reindex(idx, fill_value=0.0)
    return np.log1p(cand_daily) - np.log1p(base_daily)


def _bootstrap_daily_delta(
    frame: pd.DataFrame,
    candidate_col: str,
    *,
    n_boot: int = 4000,
    seed: int = 42,
) -> dict[str, Any]:
    delta = _daily_log_delta(frame, candidate_col).dropna().astype(float)
    if delta.empty:
        return {
            "days": 0,
            "obs_mean_daily_log_delta": None,
            "ci95_low": None,
            "ci95_high": None,
            "p_one_sided": None,
        }
    values = delta.to_numpy()
    rng = np.random.default_rng(seed)
    boot = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        boot[i] = float(rng.choice(values, size=len(values), replace=True).mean())
    obs = float(values.mean())
    return {
        "days": int(len(values)),
        "obs_mean_daily_log_delta": obs,
        "ci95_low": float(np.quantile(boot, 0.025)),
        "ci95_high": float(np.quantile(boot, 0.975)),
        "p_one_sided": float((np.sum(boot <= 0.0) + 1) / (len(boot) + 1)),
    }


def _holm_adjust(p_values: dict[str, float | None]) -> dict[str, float | None]:
    valid = [(name, float(p)) for name, p in p_values.items() if p is not None and math.isfinite(float(p))]
    valid.sort(key=lambda x: x[1])
    m = len(valid)
    out: dict[str, float | None] = {name: None for name in p_values}
    running = 0.0
    for i, (name, p) in enumerate(valid):
        adjusted = min(1.0, (m - i) * p)
        running = max(running, adjusted)
        out[name] = running
    return out


def _fold_summary(frame: pd.DataFrame, candidate_col: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fold, part in frame.groupby("fold", dropna=False):
        base = _metrics(part, "net_return")
        cand = _metrics(part, candidate_col)
        delta = _daily_log_delta(part, candidate_col)
        rows.append(
            {
                "fold": str(fold),
                "trades": int(len(part)),
                "baseline_log_growth": base["log_growth"],
                "candidate_log_growth": cand["log_growth"],
                "paired_log_delta": (
                    None
                    if base["log_growth"] is None or cand["log_growth"] is None
                    else float(cand["log_growth"] - base["log_growth"])
                ),
                "mean_daily_log_delta": float(delta.mean()) if len(delta) else None,
            }
        )
    return rows


def _reconciliation(audit: pd.DataFrame) -> dict[str, Any]:
    z = audit.loc[
        audit["cross_session"]
        & audit["revalidation_data_ready"]
    ].copy()
    if z.empty:
        return {
            "cross_session_rows": 0,
            "reconstructed_rows": 0,
            "coverage": 0.0,
            "median_abs_net_diff": None,
            "mean_abs_net_diff": None,
            "corr": None,
        }
    diff = pd.to_numeric(z["reconstructed_fixed4_net_return"], errors="coerce") - pd.to_numeric(
        z["net_return"], errors="coerce"
    )
    corr = pd.to_numeric(z["reconstructed_fixed4_net_return"], errors="coerce").corr(
        pd.to_numeric(z["net_return"], errors="coerce")
    )
    cross_total = int(audit["cross_session"].sum())
    return {
        "cross_session_rows": cross_total,
        "reconstructed_rows": int(len(z)),
        "coverage": float(len(z) / cross_total) if cross_total else 0.0,
        "median_abs_net_diff": float(diff.abs().median()),
        "mean_abs_net_diff": float(diff.abs().mean()),
        "corr": None if corr is None or not math.isfinite(float(corr)) else float(corr),
    }


def build_audit(
    ledger: pd.DataFrame,
    *,
    cache_dir: Path,
    feed: str,
    refresh_cache: bool,
    start: str | None = None,
    end: str | None = None,
    max_trades: int | None = None,
) -> pd.DataFrame:
    required = {
        "policy",
        "fold",
        "entry_timestamp",
        "exit_timestamp",
        "entry_seq",
        "exit_seq",
        "symbol",
        "weight",
        "gross_return",
        "net_return",
    }
    missing = required.difference(ledger.columns)
    if missing:
        raise RuntimeError(f"baseline ledger missing columns: {sorted(missing)}")

    base = ledger.loc[ledger["policy"].astype(str) == "FIXED_4"].copy()
    base["entry_timestamp"] = pd.to_datetime(base["entry_timestamp"], utc=True, errors="coerce")
    base["exit_timestamp"] = pd.to_datetime(base["exit_timestamp"], utc=True, errors="coerce")
    base = base.dropna(subset=["entry_timestamp", "exit_timestamp", "symbol", "net_return"])
    if start:
        base = base.loc[base["entry_timestamp"] >= pd.Timestamp(start, tz="UTC")]
    if end:
        base = base.loc[base["entry_timestamp"] < pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)]
    base = base.sort_values(["entry_timestamp", "symbol"]).reset_index(drop=True)
    base["cross_session"] = [
        _cross_session(a, b)
        for a, b in zip(base["entry_timestamp"], base["exit_timestamp"])
    ]

    cross_indices = base.index[base["cross_session"]].tolist()
    if max_trades is not None:
        cross_indices = cross_indices[: max(0, int(max_trades))]

    for col in [
        "entry_effective_ts",
        "fixed4_effective_ts",
        "entry_price_iex",
        "fixed4_exit_price_iex",
        "prev_close_price_iex",
        "open_0_price_iex",
        "open_5_price_iex",
        "open_15_price_iex",
        "position_return_prev_close",
        "position_return_open",
        "position_return_5m",
        "position_return_15m",
        "overnight_gap_return",
        "open_momentum_5m",
        "open_momentum_15m",
        "giveback_prev_close_to_5m",
        "reconstructed_fixed4_raw_return",
    ]:
        base[col] = np.nan if not col.endswith("_ts") else None
    base["revalidation_data_ready"] = False
    base["backfill_error"] = None

    window_cache: dict[tuple[str, date, date], pd.DataFrame] = {}
    for n, idx in enumerate(cross_indices, start=1):
        row = base.loc[idx]
        symbol = str(row["symbol"]).upper().replace(".", "-")
        entry_day = _to_et(row["entry_timestamp"]).date()
        exit_day = _to_et(row["exit_timestamp"]).date()
        key = (symbol, entry_day, exit_day)
        try:
            if key not in window_cache:
                window_cache[key] = load_or_fetch_session_window(
                    symbol,
                    entry_day=entry_day,
                    exit_day=exit_day,
                    cache_dir=cache_dir,
                    feed=feed,
                    refresh=refresh_cache,
                )
            features = extract_revalidation_features(
                window_cache[key],
                entry_timestamp=row["entry_timestamp"],
                exit_timestamp=row["exit_timestamp"],
            )
            if features is None:
                base.at[idx, "backfill_error"] = "REVALIDATION_FEATURES_UNAVAILABLE"
            else:
                for k, v in features.items():
                    base.at[idx, k] = v
                base.at[idx, "revalidation_data_ready"] = True
        except Exception as exc:
            base.at[idx, "backfill_error"] = f"{type(exc).__name__}: {exc}"

        if n % 50 == 0 or n == len(cross_indices):
            print(
                json.dumps(
                    {
                        "phase": "BACKFILL",
                        "processed": n,
                        "target": len(cross_indices),
                        "ready": int(base["revalidation_data_ready"].sum()),
                    }
                )
            )

    base["weight"] = pd.to_numeric(base["weight"], errors="coerce")
    base["gross_return"] = pd.to_numeric(base["gross_return"], errors="coerce")
    base["net_return"] = pd.to_numeric(base["net_return"], errors="coerce")
    base["cost_proxy"] = base["gross_return"] - base["net_return"]

    ready = base["revalidation_data_ready"]
    base["reconstructed_fixed4_net_return"] = np.nan
    base.loc[ready, "reconstructed_fixed4_net_return"] = (
        base.loc[ready, "weight"]
        * pd.to_numeric(base.loc[ready, "reconstructed_fixed4_raw_return"], errors="coerce")
        - base.loc[ready, "cost_proxy"]
    )

    for policy in POLICIES:
        trigger_col = f"{policy.name}__trigger"
        ret_col = f"{policy.name}__net_return"
        exit_col = f"{policy.name}__exit_price"
        base[trigger_col] = False
        base[ret_col] = base["net_return"].astype(float)
        base[exit_col] = np.nan
        for idx in base.index[ready]:
            row = base.loc[idx]
            triggered = policy_trigger(policy, row)
            base.at[idx, trigger_col] = bool(triggered)
            if not triggered:
                continue
            exit_price = candidate_exit_price(policy, row)
            entry_price = float(row["entry_price_iex"])
            fixed4_raw = float(row["reconstructed_fixed4_raw_return"])
            candidate_raw = exit_price / entry_price - 1.0
            delta_weighted = float(row["weight"]) * (candidate_raw - fixed4_raw)
            # Preserve the original full-market baseline return and add only
            # the same-feed (IEX/SIP) counterfactual delta. This materially
            # reduces feed-level bias in the paired comparison.
            base.at[idx, ret_col] = float(row["net_return"]) + delta_weighted
            base.at[idx, exit_col] = exit_price

    return base


def evaluate(audit: pd.DataFrame, *, feed: str) -> dict[str, Any]:
    baseline = _metrics(audit, "net_return")
    recon = _reconciliation(audit)
    summaries: list[dict[str, Any]] = []
    p_values: dict[str, float | None] = {}

    for policy in POLICIES:
        ret_col = f"{policy.name}__net_return"
        trigger_col = f"{policy.name}__trigger"
        metrics = _metrics(audit, ret_col)
        boot = _bootstrap_daily_delta(audit, ret_col)
        folds = _fold_summary(audit, ret_col)
        positive_folds = sum(
            1 for row in folds
            if row["paired_log_delta"] is not None and row["paired_log_delta"] > 0
        )
        triggered = int(audit[trigger_col].sum())
        cross_ready = int((audit["cross_session"] & audit["revalidation_data_ready"]).sum())
        item = {
            "policy": policy.name,
            "latency_minutes": policy.latency_minutes,
            "rule": policy.rule,
            "triggered_exits": triggered,
            "trigger_rate_cross_ready": float(triggered / cross_ready) if cross_ready else 0.0,
            **metrics,
            **boot,
            "positive_folds": int(positive_folds),
            "fold_count": int(len(folds)),
            "folds": folds,
        }
        item["delta_log_growth_vs_fixed4"] = (
            None
            if metrics["log_growth"] is None or baseline["log_growth"] is None
            else float(metrics["log_growth"] - baseline["log_growth"])
        )
        item["mdd_delta_vs_fixed4"] = (
            None
            if metrics["mdd"] is None or baseline["mdd"] is None
            else float(metrics["mdd"] - baseline["mdd"])
        )
        summaries.append(item)
        p_values[policy.name] = boot["p_one_sided"]

    holm = _holm_adjust(p_values)
    for item in summaries:
        item["holm_p"] = holm[item["policy"]]
        item["research_survivor"] = bool(
            item["ci95_low"] is not None
            and item["ci95_low"] > 0
            and item["holm_p"] is not None
            and item["holm_p"] <= 0.10
            and item["positive_folds"] >= max(1, math.ceil(item["fold_count"] * 0.60))
            and (
                item["mdd_delta_vs_fixed4"] is None
                or item["mdd_delta_vs_fixed4"] >= -0.02
            )
            and recon["coverage"] >= 0.90
        )

    survivors = [x for x in summaries if x["research_survivor"]]
    survivors.sort(
        key=lambda x: (
            float(x["obs_mean_daily_log_delta"] or -999),
            float(x["delta_log_growth_vs_fixed4"] or -999),
        ),
        reverse=True,
    )
    selected = survivors[0]["policy"] if survivors else None

    return {
        "schema": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "research_only": True,
        "production_changed": False,
        "live_exit_changed": False,
        "source_baseline": "exit_policy_v1_0_1 FIXED_4",
        "alpaca_feed": feed,
        "baseline": baseline,
        "reconciliation": recon,
        "candidate_summaries": summaries,
        "selected_research_survivor": selected,
        "promotion_recommendation": (
            "PROSPECTIVE_SHADOW_ONLY" if selected else "NO_PROMOTION"
        ),
        "notes": [
            "Only cross-session FIXED_4 trades can trigger open revalidation.",
            "Candidate return preserves original baseline and adds same-feed counterfactual delta.",
            "Historical quote spread/order-book is not used in v1; baseline transaction cost proxy is preserved.",
            "A survivor is not production SELL logic; it must be frozen and prospectively shadowed.",
        ],
    }


def _default_us_etf_root() -> Path:
    override = os.environ.get("KALMAN_US_ETF_ROOT", "").strip()
    if override:
        return Path(override).expanduser()

    candidates = (Path("/mnt/gdrive/US_ETF"), Path("/mnt/gdrive"))
    for candidate in candidates:
        if (candidate / "model_lab_v1").is_dir() and (candidate / "directional_research").is_dir():
            return candidate
    return Path("/mnt/gdrive/US_ETF")


def parse_args() -> argparse.Namespace:
    root = _default_us_etf_root()
    p = argparse.ArgumentParser(description="Research-only R5 open-revalidation backfill/backtest")
    p.add_argument(
        "--baseline-ledger",
        default=str(root / "model_lab_v1/results/exit_policy_v1_0_pre2026/exit_policy_v1_0_1_trade_ledger.parquet"),
    )
    p.add_argument(
        "--cache-dir",
        default=str(root / "directional_research/open_revalidation_1m_alpaca_v1"),
    )
    p.add_argument(
        "--output-dir",
        default=str(root / "model_lab_v1/results/open_revalidation_v1"),
    )
    p.add_argument("--feed", default=os.environ.get("OPEN_REVALIDATION_ALPACA_FEED", "iex"))
    p.add_argument("--start", default=None)
    p.add_argument("--end", default="2025-12-31")
    p.add_argument("--max-trades", type=int, default=None)
    p.add_argument("--refresh-cache", action="store_true")
    p.add_argument("--backfill-only", action="store_true")
    return p.parse_args()


def main() -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"), override=False)
    except ImportError:
        pass

    args = parse_args()
    baseline_path = Path(args.baseline_ledger)
    if not baseline_path.is_file():
        raise FileNotFoundError(baseline_path)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    status_path = output_dir / "status.json"
    _write_json(
        status_path,
        {
            "schema": SCHEMA_VERSION,
            "status": "RUNNING",
            "phase": "LOAD_BASELINE",
            "research_only": True,
            "production_changed": False,
            "baseline_ledger": str(baseline_path),
            "baseline_sha256": _sha256(baseline_path),
            "feed": args.feed,
        },
    )

    ledger = pd.read_parquet(baseline_path)
    _write_json(
        status_path,
        {
            "schema": SCHEMA_VERSION,
            "status": "RUNNING",
            "phase": "BACKFILL",
            "research_only": True,
            "production_changed": False,
            "baseline_rows": int(len(ledger)),
            "feed": args.feed,
        },
    )
    audit = build_audit(
        ledger,
        cache_dir=Path(args.cache_dir),
        feed=args.feed,
        refresh_cache=bool(args.refresh_cache),
        start=args.start,
        end=args.end,
        max_trades=args.max_trades,
    )
    audit_path = output_dir / "open_revalidation_trade_audit.parquet"
    audit.to_parquet(audit_path, index=False)

    if args.backfill_only:
        result = {
            "schema": SCHEMA_VERSION,
            "status": "BACKFILL_COMPLETE",
            "research_only": True,
            "production_changed": False,
            "rows": int(len(audit)),
            "cross_session_rows": int(audit["cross_session"].sum()),
            "ready_rows": int(audit["revalidation_data_ready"].sum()),
            "audit": str(audit_path),
        }
        _write_json(status_path, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    decision = evaluate(audit, feed=args.feed)
    decision["baseline_ledger"] = str(baseline_path)
    decision["baseline_sha256"] = _sha256(baseline_path)
    decision["audit_path"] = str(audit_path)
    decision_path = output_dir / "open_revalidation_decision.json"
    _write_json(decision_path, decision)

    summary_rows = []
    for item in decision["candidate_summaries"]:
        summary_rows.append(
            {
                k: v
                for k, v in item.items()
                if k != "folds"
            }
        )
    pd.DataFrame(summary_rows).to_csv(
        output_dir / "open_revalidation_candidate_summary.csv",
        index=False,
    )
    fold_rows = []
    for item in decision["candidate_summaries"]:
        for fold in item["folds"]:
            fold_rows.append({"policy": item["policy"], **fold})
    pd.DataFrame(fold_rows).to_csv(
        output_dir / "open_revalidation_fold_summary.csv",
        index=False,
    )

    final_status = {
        "schema": SCHEMA_VERSION,
        "status": "COMPLETE",
        "research_only": True,
        "production_changed": False,
        "live_exit_changed": False,
        "baseline_rows": int(len(audit)),
        "cross_session_rows": int(audit["cross_session"].sum()),
        "ready_rows": int(audit["revalidation_data_ready"].sum()),
        "reconciliation": decision["reconciliation"],
        "selected_research_survivor": decision["selected_research_survivor"],
        "promotion_recommendation": decision["promotion_recommendation"],
        "decision": str(decision_path),
        "audit": str(audit_path),
    }
    _write_json(status_path, final_status)
    print(json.dumps(final_status, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
