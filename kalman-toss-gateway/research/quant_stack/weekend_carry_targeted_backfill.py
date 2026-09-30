from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

NY = ZoneInfo("America/New_York")
ALPACA_BARS_URL = "https://data.alpaca.markets/v2/stocks/{symbol}/bars"


def _load_env_file(path: str | None) -> None:
    if not path:
        return
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def _credentials() -> tuple[str, str]:
    key = (
        os.environ.get("APCA_API_KEY_ID")
        or os.environ.get("ALPACA_API_KEY")
        or os.environ.get("ALPACA_API_KEY_ID")
        or os.environ.get("APCA_API_KEY")
        or os.environ.get("ALPACA_KEY")
        or ""
    ).strip()
    secret = (
        os.environ.get("APCA_API_SECRET_KEY")
        or os.environ.get("ALPACA_API_SECRET_KEY")
        or os.environ.get("ALPACA_API_SECRET")
        or os.environ.get("APCA_SECRET_KEY")
        or os.environ.get("ALPACA_SECRET")
        or ""
    ).strip()
    if not key or not secret:
        raise RuntimeError("Alpaca credentials missing")
    return key, secret


def _request_json(url: str, key: str, secret: str, max_retries: int = 7) -> dict:
    headers = {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
        "User-Agent": "KalmanWeekendCarryBackfill/1.0",
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
                wait = float(retry_after) if retry_after else min(30.0, 1.6 ** (attempt + 1))
                time.sleep(wait)
                continue
            if 500 <= exc.code < 600 and attempt + 1 < max_retries:
                time.sleep(min(20.0, 1.6 ** (attempt + 1)))
                continue
            raise RuntimeError(f"HTTP {exc.code}: {body[:500]}") from exc
        except urllib.error.URLError as exc:
            if attempt + 1 >= max_retries:
                raise RuntimeError(f"request failed: {exc}") from exc
            time.sleep(min(20.0, 1.6 ** (attempt + 1)))
    raise RuntimeError("request exhausted retries")


def _fetch_1m(
    symbol: str,
    *,
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
    feed: str,
    key: str,
    secret: str,
) -> pd.DataFrame:
    rows: list[dict] = []
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

        base = ALPACA_BARS_URL.format(
            symbol=urllib.parse.quote(symbol.upper(), safe="")
        )
        payload = _request_json(
            base + "?" + urllib.parse.urlencode(query),
            key,
            secret,
        )
        rows.extend(payload.get("bars") or [])
        page_token = payload.get("next_page_token")
        if not page_token:
            break

    if not rows:
        return pd.DataFrame(
            columns=[
                "timestamp", "open", "high", "low", "close",
                "volume", "trade_count", "vwap",
            ]
        )

    out = pd.DataFrame({
        "timestamp": [r.get("t") for r in rows],
        "open": [r.get("o") for r in rows],
        "high": [r.get("h") for r in rows],
        "low": [r.get("l") for r in rows],
        "close": [r.get("c") for r in rows],
        "volume": [r.get("v") for r in rows],
        "trade_count": [r.get("n") for r in rows],
        "vwap": [r.get("vw") for r in rows],
    })
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    for col in ["open", "high", "low", "close", "volume", "trade_count", "vwap"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return (
        out.dropna(subset=["timestamp", "close"])
        .sort_values("timestamp")
        .drop_duplicates("timestamp", keep="last")
        .reset_index(drop=True)
    )


def _window(entry_ts: pd.Timestamp, exit_ts: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    entry_local = entry_ts.tz_convert(NY)
    exit_local = exit_ts.tz_convert(NY)
    start_local = pd.Timestamp(
        datetime.combine(entry_local.date(), dt_time(9, 20), tzinfo=NY)
    )
    end_local = pd.Timestamp(
        datetime.combine(exit_local.date(), dt_time(16, 10), tzinfo=NY)
    )
    return start_local.tz_convert("UTC"), end_local.tz_convert("UTC")


def _name(start_utc: pd.Timestamp, end_utc: pd.Timestamp) -> str:
    a = start_utc.strftime("%Y%m%dT%H%M%SZ")
    b = end_utc.strftime("%Y%m%dT%H%M%SZ")
    return f"{a}__{b}.parquet"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--execution-audit",
        default="/mnt/gdrive/US_ETF/model_lab_v1/results/weekend_carry_execution_validation_v1/weekend_carry_execution_audit.csv",
    )
    ap.add_argument(
        "--alpaca-root",
        default="/mnt/gdrive/US_ETF/directional_research/live_policy_replay_1m_alpaca_v1",
    )
    ap.add_argument("--env-file", default="/opt/kalman/.env")
    ap.add_argument("--primary-only", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--sleep-seconds", type=float, default=0.15)
    args = ap.parse_args()

    _load_env_file(args.env_file)
    key, secret = _credentials()

    audit = pd.read_csv(args.execution_audit)
    if "iex_boats_covered" not in audit:
        raise RuntimeError("iex_boats_covered column missing")

    audit["entry_timestamp"] = pd.to_datetime(audit["entry_timestamp"], utc=True)
    audit["fixed4_exit_timestamp"] = pd.to_datetime(
        audit["fixed4_exit_timestamp"], utc=True
    )

    covered = audit["iex_boats_covered"].fillna(False).astype(bool)
    missing = audit.loc[~covered].copy()
    if missing.empty:
        print("NO_MISSING_PRIMARY_TRADES")
        return 0

    root = Path(args.alpaca_root)
    feeds = [("iex+boats", "iex")]
    if not args.primary_only:
        feeds.append(("sip+boats", "sip"))

    jobs: list[dict] = []
    for _, row in missing.iterrows():
        start_utc, end_utc = _window(
            row["entry_timestamp"],
            row["fixed4_exit_timestamp"],
        )
        for folder_feed, api_feed in feeds:
            jobs.append({
                "symbol": str(row["symbol"]).upper(),
                "fold": row.get("fold"),
                "folder_feed": folder_feed,
                "api_feed": api_feed,
                "start_utc": start_utc,
                "end_utc": end_utc,
            })

    unique = {}
    for job in jobs:
        key_job = (
            job["folder_feed"],
            job["symbol"],
            job["start_utc"].isoformat(),
            job["end_utc"].isoformat(),
        )
        unique[key_job] = job
    jobs = list(unique.values())

    print("============================================================")
    print("KALMAN WEEKEND CARRY TARGETED ALPACA BACKFILL")
    print("============================================================")
    print("missing_primary_trades =", len(missing))
    print("download_jobs =", len(jobs))
    print("alpaca_root =", root)
    print("feeds =", [x[0] for x in feeds])

    downloaded = 0
    existing = 0
    no_data = 0
    errors = 0
    feed_stats: dict[str, dict[str, int]] = {}

    for i, job in enumerate(jobs, start=1):
        folder_feed = job["folder_feed"]
        api_feed = job["api_feed"]
        symbol = job["symbol"]
        outdir = root / folder_feed / symbol
        outfile = outdir / _name(job["start_utc"], job["end_utc"])

        stat = feed_stats.setdefault(
            folder_feed,
            {"downloaded": 0, "existing": 0, "no_data": 0, "errors": 0},
        )

        if outfile.is_file() and not args.refresh:
            existing += 1
            stat["existing"] += 1
            print(f"[{i}/{len(jobs)}] EXISTING {folder_feed} {symbol} {outfile.name}")
            continue

        try:
            frame = _fetch_1m(
                symbol,
                start_utc=job["start_utc"],
                end_utc=job["end_utc"],
                feed=api_feed,
                key=key,
                secret=secret,
            )
            if frame.empty:
                no_data += 1
                stat["no_data"] += 1
                print(f"[{i}/{len(jobs)}] NO_DATA {folder_feed} {symbol}")
                continue

            outdir.mkdir(parents=True, exist_ok=True)
            tmp = outfile.with_suffix(".parquet.tmp")
            frame.to_parquet(tmp, index=False)
            tmp.replace(outfile)

            downloaded += 1
            stat["downloaded"] += 1
            print(
                f"[{i}/{len(jobs)}] DOWNLOADED {folder_feed} {symbol} "
                f"rows={len(frame)} {frame['timestamp'].min()} -> {frame['timestamp'].max()}"
            )
        except Exception as exc:
            errors += 1
            stat["errors"] += 1
            print(f"[{i}/{len(jobs)}] ERROR {folder_feed} {symbol} {type(exc).__name__}: {exc}")

        if args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)

    summary = {
        "missing_primary_trades": int(len(missing)),
        "jobs": int(len(jobs)),
        "downloaded": downloaded,
        "existing": existing,
        "no_data": no_data,
        "errors": errors,
        "feed_stats": feed_stats,
    }

    print()
    print("SUMMARY")
    print(json.dumps(summary, indent=2))

    # Primary IEX errors are decision-critical. SIP is a cross-check and may
    # legitimately be unavailable depending on Alpaca subscription.
    primary_errors = feed_stats.get("iex+boats", {}).get("errors", 0)
    return 0 if primary_errors == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
