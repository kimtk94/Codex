#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

from engine.macro_consensus_provider_v1 import (
    normalize_calendar_row,
    upsert_observations,
)

UTC = timezone.utc
DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "macro-event-features-v1.json"
DEFAULT_OUT = Path("/opt/kalman/state/r7_macro_backfill")
SCHEMA = "kalman-r7-macro-backfill-v1"


def parse_date(text: str) -> date:
    return date.fromisoformat(text)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(UTC).isoformat() if dt else None


def chunk_ranges(start: date, end: date, days: int) -> list[tuple[date, date]]:
    if end < start:
        raise ValueError("end before start")
    if days < 1:
        raise ValueError("chunk days must be positive")
    out: list[tuple[date, date]] = []
    cur = start
    step = timedelta(days=days - 1)
    while cur <= end:
        stop = min(end, cur + step)
        out.append((cur, stop))
        cur = stop + timedelta(days=1)
    return out


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def market_spec(config: dict[str, Any], market: str) -> dict[str, Any]:
    provider = config.get("trading_economics") or {}
    markets = provider.get("markets") or {}
    raw = markets.get(market)
    if not isinstance(raw, dict):
        raise KeyError(f"market not configured: {market}")
    spec = {k: v for k, v in provider.items() if k != "markets"}
    spec.update(raw)
    spec["market"] = market
    return spec


def fetch_range(
    *,
    config: dict[str, Any],
    market: str,
    start: date,
    end: date,
    credentials: str,
    retries: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    spec = market_spec(config, market)
    provider = config.get("trading_economics") or {}
    country = str(spec.get("country") or "").strip()
    if not country:
        raise ValueError(f"missing country for {market}")

    base_url = str(provider.get("base_url") or "https://api.tradingeconomics.com").rstrip("/")
    timeout = float(provider.get("timeout_seconds", 20))
    url = f"{base_url}/calendar/country/{quote(country, safe='')}/{start.isoformat()}/{end.isoformat()}"
    params = {"c": credentials, "f": "json", "values": "true"}

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(url, params=params)
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"retryable provider status={response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                payload = response.json()
            if not isinstance(payload, list):
                raise ValueError("Trading Economics calendar response is not a list")

            # Use the research cutoff as the normalization as_of. Historical rows whose
            # LastUpdate occurred after the original release remain conservatively delayed
            # through available_at=max(Date, LastUpdate).
            as_of = datetime.combine(end, datetime.max.time(), tzinfo=UTC)
            normalized: list[dict[str, Any]] = []
            for raw in payload:
                if not isinstance(raw, dict):
                    continue
                row = normalize_calendar_row(raw, config, as_of, spec)
                if row is None:
                    continue
                row["payload"] = {
                    **(row.get("payload") or {}),
                    "r7_backfill": True,
                    "r7_pit_audit": "UNVERIFIED_PROVIDER_HISTORY",
                    "r7_fetch_window_start": start.isoformat(),
                    "r7_fetch_window_end": end.isoformat(),
                }
                normalized.append(row)
            return normalized, {
                "market": market,
                "country": country,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "provider_rows": len(payload),
                "mapped_rows": len(normalized),
                "status": "READY",
            }
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(min(8.0, 1.0 * (2 ** attempt)))
    assert last_error is not None
    raise last_error


def row_lag_minutes(row: dict[str, Any]) -> float | None:
    release = row.get("release_at")
    available = row.get("available_at")
    if not isinstance(release, datetime) or not isinstance(available, datetime):
        return None
    return (available - release).total_seconds() / 60.0


def audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_indicator: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_indicator[str(row.get("indicator_key") or "UNKNOWN")].append(row)

    lags = [x for r in rows if (x := row_lag_minutes(r)) is not None]
    event_usable = [x for x in lags if 0 <= x <= 120]
    consensus = [r for r in rows if r.get("consensus") is not None]
    actual = [r for r in rows if r.get("actual") is not None]
    qualities = Counter(str(r.get("time_quality") or "UNKNOWN") for r in rows)

    indicator_summary: dict[str, Any] = {}
    for key, vals in sorted(by_indicator.items()):
        releases = sorted(r["release_at"] for r in vals if isinstance(r.get("release_at"), datetime))
        indicator_summary[key] = {
            "n": len(vals),
            "consensus_ratio": sum(r.get("consensus") is not None for r in vals) / len(vals),
            "first_release": iso(releases[0]) if releases else None,
            "last_release": iso(releases[-1]) if releases else None,
        }

    def quantile(xs: list[float], q: float) -> float | None:
        if not xs:
            return None
        ys = sorted(xs)
        pos = (len(ys) - 1) * q
        lo = int(pos)
        hi = min(lo + 1, len(ys) - 1)
        frac = pos - lo
        return ys[lo] * (1 - frac) + ys[hi] * frac

    releases = sorted(r["release_at"] for r in rows if isinstance(r.get("release_at"), datetime))
    return {
        "rows": len(rows),
        "indicators": len(by_indicator),
        "first_release": iso(releases[0]) if releases else None,
        "last_release": iso(releases[-1]) if releases else None,
        "actual_ratio": len(actual) / len(rows) if rows else 0.0,
        "consensus_ratio": len(consensus) / len(rows) if rows else 0.0,
        "event_time_usable_ratio_120m": len(event_usable) / len(lags) if lags else 0.0,
        "release_to_available_lag_minutes_p50": quantile(lags, 0.50),
        "release_to_available_lag_minutes_p95": quantile(lags, 0.95),
        "time_quality_counts": dict(qualities),
        "by_indicator": indicator_summary,
        "pit_audit_status": "UNVERIFIED_PROVIDER_HISTORY",
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            serializable = {
                **row,
                "release_at": iso(row.get("release_at")),
                "available_at": iso(row.get("available_at")),
            }
            fh.write(json.dumps(serializable, ensure_ascii=False, sort_keys=True) + "\n")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="R7 research-only macro calendar backfill")
    p.add_argument("--start", default="2020-01-01")
    p.add_argument("--end", default="2026-09-02")
    p.add_argument("--market", default="US", choices=["US", "KR"])
    p.add_argument("--chunk-days", type=int, default=90)
    p.add_argument("--sleep-seconds", type=float, default=0.25)
    p.add_argument("--retries", type=int, default=3)
    p.add_argument("--max-chunks", type=int, default=0)
    p.add_argument("--config", default=str(DEFAULT_CONFIG))
    p.add_argument("--env-file", default=os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"))
    p.add_argument("--output-dir", default=str(DEFAULT_OUT))
    p.add_argument("--write", action="store_true", help="Explicitly upsert normalized rows into Neon")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    env_path = Path(args.env_file)
    if env_path.exists():
        load_dotenv(env_path, override=True)

    credentials = (os.environ.get("TRADING_ECONOMICS_API_KEY") or "").strip()
    if not credentials:
        raise SystemExit("TRADING_ECONOMICS_API_KEY missing")
    if credentials.lower() in {"guest", "guest:guest"}:
        raise SystemExit("Demo Trading Economics credentials are not allowed")

    config = load_config(Path(args.config))
    start, end = parse_date(args.start), parse_date(args.end)
    chunks = chunk_ranges(start, end, args.chunk_days)
    if args.max_chunks > 0:
        chunks = chunks[: args.max_chunks]

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    rows_by_id: dict[str, dict[str, Any]] = {}
    chunk_log: list[dict[str, Any]] = []
    for i, (a, b) in enumerate(chunks, 1):
        rows, status = fetch_range(
            config=config,
            market=args.market,
            start=a,
            end=b,
            credentials=credentials,
            retries=args.retries,
        )
        for row in rows:
            rows_by_id[str(row["observation_id"])] = row
        status["chunk_index"] = i
        chunk_log.append(status)
        print(
            f"[R7-M] chunk={i}/{len(chunks)} {a}..{b} "
            f"provider={status['provider_rows']} mapped={status['mapped_rows']}",
            flush=True,
        )
        if args.sleep_seconds > 0 and i < len(chunks):
            time.sleep(args.sleep_seconds)

    rows = sorted(
        rows_by_id.values(),
        key=lambda r: (r["release_at"], r["indicator_key"], r["observation_id"]),
    )
    report = {
        "schema": SCHEMA,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "research_only": True,
        "production_changed": False,
        "market": args.market,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "chunks": chunk_log,
        "audit": audit(rows),
        "write_requested": bool(args.write),
    }

    jsonl = out / f"r7_macro_{args.market.lower()}_{start}_{end}.jsonl"
    manifest = out / f"r7_macro_{args.market.lower()}_{start}_{end}_manifest.json"
    write_jsonl(jsonl, rows)

    if args.write:
        import psycopg

        db_url = os.environ.get("DATABASE_URL_WRITER") or os.environ.get("DATABASE_URL")
        if not db_url:
            raise SystemExit("DATABASE_URL_WRITER/DATABASE_URL missing for --write")
        with psycopg.connect(db_url, connect_timeout=15) as conn:
            counts = upsert_observations(conn, rows)
            conn.commit()
        report["db_write"] = counts
    else:
        report["db_write"] = {"status": "DRY_RUN_NO_DB_WRITE"}

    manifest.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print("[R7-M] MANIFEST", manifest)
    print(json.dumps(report["audit"], indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
