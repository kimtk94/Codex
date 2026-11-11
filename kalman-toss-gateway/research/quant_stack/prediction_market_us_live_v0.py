from __future__ import annotations

import argparse
import json
import math
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine.prediction_market_layer_v0 import (
    classify_theme,
    contract_semantics,
    load_config as load_prediction_config,
)
from research.quant_stack.prediction_market_archive_v0 import compute_probability_deltas
from research.quant_stack.prediction_market_oos_v0 import (
    evaluate_frozen_hypothesis,
    load_spec,
)
from research.quant_stack.prediction_market_us_oos_ledger_v0 import update_ledger
from research.quant_stack.prediction_market_source_health_v0 import evaluate_and_rollback_if_needed
from research.quant_stack.prediction_market_leadlag_v0 import load_asset_history


USER_AGENT = "KalmanPolymarketUSLive/0.1"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("value")
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def http_json(url: str, *, timeout: float, retries: int = 3) -> Any:
    for attempt in range(retries):
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code in (429, 500, 502, 503, 504) and attempt + 1 < retries:
                retry_after = exc.headers.get("Retry-After")
                delay = (
                    float(retry_after)
                    if retry_after and retry_after.replace(".", "", 1).isdigit()
                    else min(10.0, 2.0 ** attempt)
                )
                time.sleep(delay)
                continue
            raise RuntimeError(
                f"Polymarket US HTTP {exc.code}: {body[:500]}"
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt + 1 >= retries:
                raise RuntimeError(f"Polymarket US request failed: {exc}") from exc
            time.sleep(min(10.0, 2.0 ** attempt))
    raise RuntimeError("Polymarket US request retries exhausted")


def search_markets(
    *,
    gateway_base: str,
    queries: list[str],
    category: str,
    prediction_config: dict[str, Any],
    allowed_themes: set[str],
    allowed_channels: set[str],
    timeout: float,
) -> pd.DataFrame:
    by_slug: dict[str, dict[str, Any]] = {}
    for query in queries:
        url = (
            gateway_base.rstrip("/")
            + "/v1/search?"
            + urllib.parse.urlencode({"query": query, "limit": 100})
        )
        payload = http_json(url, timeout=timeout)
        for event in payload.get("events") or []:
            for market in event.get("markets") or []:
                if not bool(market.get("active")) or bool(market.get("closed")):
                    continue
                if str(market.get("category") or "").lower() != category.lower():
                    continue
                slug = str(market.get("slug") or "").strip()
                question = str(market.get("question") or "").strip()
                description = str(market.get("description") or "").strip()
                title = str(market.get("title") or "").strip()
                if not slug:
                    continue
                semantic_text = " ".join([slug, question, title, description])
                theme = classify_theme(semantic_text, prediction_config)
                channel, risk_sign = contract_semantics(
                    slug,
                    " ".join([question, title, description]),
                    theme,
                    prediction_config,
                )
                if theme not in allowed_themes or channel not in allowed_channels:
                    continue
                by_slug[slug] = {
                    "slug": slug,
                    "market_id": str(market.get("id") or ""),
                    "event_id": str(event.get("id") or ""),
                    "event_slug": str(event.get("slug") or ""),
                    "question": question,
                    "title": title,
                    "description": description,
                    "category": str(market.get("category") or ""),
                    "theme": theme,
                    "semantic_channel": channel,
                    "risk_prior_sign": risk_sign,
                    "start_date": market.get("startDate"),
                    "end_date": market.get("endDate"),
                    "game_start_time": market.get("gameStartTime"),
                }
    if not by_slug:
        return pd.DataFrame(
            columns=[
                "slug",
                "market_id",
                "event_id",
                "event_slug",
                "question",
                "title",
                "description",
                "category",
                "theme",
                "semantic_channel",
                "risk_prior_sign",
                "start_date",
                "end_date",
                "game_start_time",
            ]
        )
    return pd.DataFrame(by_slug.values()).sort_values("slug").reset_index(drop=True)


def parse_bbo(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("marketData") or {}
    bid = as_float(data.get("bestBid"))
    ask = as_float(data.get("bestAsk"))
    current_px = as_float(data.get("currentPx"))
    last_trade = as_float(data.get("lastTradePx"))
    long_quote = as_float(data.get("longQuote"))
    short_quote = as_float(data.get("shortQuote"))
    last_sample = data.get("lastPriceSample") or {}

    midpoint = None
    if bid is not None and ask is not None and 0.0 <= bid <= ask <= 1.0:
        midpoint = (bid + ask) / 2.0

    midpoint_vs_current = (
        abs(midpoint - current_px)
        if midpoint is not None and current_px is not None
        else None
    )
    return {
        "market_slug": str(data.get("marketSlug") or ""),
        "state": str(data.get("state") or ""),
        "bid": bid,
        "ask": ask,
        "midpoint": midpoint,
        "spread": (ask - bid) if bid is not None and ask is not None else None,
        "current_px": current_px,
        "last_trade": last_trade,
        "long_quote": long_quote,
        "short_quote": short_quote,
        "shares_traded": as_float(data.get("sharesTraded")),
        "open_interest": as_float(data.get("openInterest")),
        "bid_depth": data.get("bidDepth"),
        "ask_depth": data.get("askDepth"),
        "last_sample_ts": last_sample.get("ts"),
        "midpoint_vs_current": midpoint_vs_current,
    }


def init_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            observed_at TEXT NOT NULL,
            slug TEXT NOT NULL,
            market_id TEXT,
            event_id TEXT,
            event_slug TEXT,
            question TEXT NOT NULL,
            title TEXT,
            category TEXT,
            theme TEXT,
            semantic_channel TEXT,
            risk_prior_sign INTEGER,
            state TEXT,
            bid REAL,
            ask REAL,
            midpoint REAL,
            spread REAL,
            current_px REAL,
            last_trade REAL,
            shares_traded REAL,
            open_interest REAL,
            bid_depth INTEGER,
            ask_depth INTEGER,
            last_sample_ts TEXT,
            midpoint_vs_current REAL,
            source TEXT NOT NULL,
            UNIQUE(observed_at, slug)
        )
        """
    )
    con.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_snapshots_slug_time
        ON snapshots(slug, observed_at)
        """
    )
    con.commit()
    return con


def collect_once(
    *,
    config: dict[str, Any],
    prediction_config: dict[str, Any],
) -> dict[str, Any]:
    source = config["source"]
    collection = config["collection"]
    markets = search_markets(
        gateway_base=source["gateway_base"],
        queries=list(source["search_queries"]),
        category=str(source["category"]),
        prediction_config=prediction_config,
        allowed_themes={str(x) for x in collection["only_themes"]},
        allowed_channels={str(x) for x in collection["only_channels"]},
        timeout=float(source["timeout_seconds"]),
    )
    db_path = Path(config["paths"]["sqlite"])
    con = init_db(db_path)
    observed_at = now_iso()
    rows = []
    failures = []
    try:
        for idx, market in markets.iterrows():
            if idx:
                time.sleep(float(source["request_spacing_seconds"]))
            slug = str(market["slug"])
            url = (
                source["gateway_base"].rstrip("/")
                + "/v1/markets/"
                + urllib.parse.quote(slug, safe="")
                + "/bbo"
            )
            try:
                parsed = parse_bbo(
                    http_json(url, timeout=float(source["timeout_seconds"]))
                )
            except Exception as exc:
                failures.append({"slug": slug, "error": str(exc)})
                continue

            if collection["require_two_sided_book"] and parsed["midpoint"] is None:
                continue
            if parsed["midpoint"] is not None and not (
                0.0 <= float(parsed["midpoint"]) <= 1.0
            ):
                failures.append({"slug": slug, "error": "midpoint_out_of_range"})
                continue

            row = {
                "observed_at": observed_at,
                "slug": slug,
                "market_id": str(market["market_id"]),
                "event_id": str(market["event_id"]),
                "event_slug": str(market["event_slug"]),
                "question": str(market["question"]),
                "title": str(market["title"]),
                "category": str(market["category"]),
                "theme": str(market["theme"]),
                "semantic_channel": str(market["semantic_channel"]),
                "risk_prior_sign": int(market["risk_prior_sign"]),
                **parsed,
                "source": "Polymarket US public gateway /v1/markets/{slug}/bbo",
            }
            rows.append(row)
            con.execute(
                """
                INSERT OR IGNORE INTO snapshots (
                    observed_at, slug, market_id, event_id, event_slug,
                    question, title, category, theme, semantic_channel,
                    risk_prior_sign, state, bid, ask, midpoint, spread,
                    current_px, last_trade, shares_traded, open_interest,
                    bid_depth, ask_depth, last_sample_ts, midpoint_vs_current,
                    source
                ) VALUES (
                    :observed_at, :slug, :market_id, :event_id, :event_slug,
                    :question, :title, :category, :theme, :semantic_channel,
                    :risk_prior_sign, :state, :bid, :ask, :midpoint, :spread,
                    :current_px, :last_trade, :shares_traded, :open_interest,
                    :bid_depth, :ask_depth, :last_sample_ts, :midpoint_vs_current,
                    :source
                )
                """,
                row,
            )
        con.commit()
    finally:
        con.close()

    deviations = [
        float(r["midpoint_vs_current"])
        for r in rows
        if r.get("midpoint_vs_current") is not None
    ]
    return {
        "status": "COLLECTED",
        "observed_at": observed_at,
        "discovered_markets": int(len(markets)),
        "stored_snapshots": int(len(rows)),
        "request_failures": failures,
        "max_midpoint_vs_current": max(deviations) if deviations else None,
        "median_midpoint_vs_current": (
            float(np.median(deviations)) if deviations else None
        ),
        "source": "Polymarket US official public gateway",
        "auth_used": False,
        "trade_execution": False,
    }


def load_snapshots(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    con = sqlite3.connect(path)
    try:
        return pd.read_sql_query(
            """
            SELECT observed_at, slug, market_id, event_id, event_slug,
                   question, title, category, theme, semantic_channel,
                   risk_prior_sign, state, bid, ask, midpoint, spread,
                   current_px, last_trade, shares_traded, open_interest,
                   bid_depth, ask_depth, last_sample_ts, midpoint_vs_current,
                   source
            FROM snapshots
            ORDER BY observed_at, slug
            """,
            con,
        )
    finally:
        con.close()


def assign_gap_segments(frame: pd.DataFrame, gap_minutes: int) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    out = frame.sort_values(["slug", "observed_at"]).copy()
    diff = out.groupby("slug")["observed_at"].diff()
    breaks = diff.isna() | (diff > pd.Timedelta(minutes=int(gap_minutes)))
    out["segment"] = breaks.groupby(out["slug"]).cumsum().astype(int)
    return out


def build_canonical(
    *,
    sqlite_path: Path,
    output_path: Path,
    bucket_minutes: int,
    gap_segment_minutes: int,
) -> dict[str, Any]:
    raw = load_snapshots(sqlite_path)
    if raw.empty:
        return {
            "status": "NO_RAW_DATA",
            "rows": 0,
            "markets": 0,
        }

    raw["observed_at"] = pd.to_datetime(
        raw["observed_at"], utc=True, errors="coerce"
    ).astype("datetime64[ns, UTC]")
    raw = raw.dropna(subset=["observed_at", "slug", "midpoint"])
    for c in ["bid", "ask", "midpoint", "spread", "current_px", "last_trade"]:
        raw[c] = pd.to_numeric(raw[c], errors="coerce")
    raw = raw[
        raw["bid"].notna()
        & raw["ask"].notna()
        & (raw["bid"] >= 0)
        & (raw["ask"] <= 1)
        & (raw["ask"] >= raw["bid"])
    ].copy()
    if raw.empty:
        return {
            "status": "NO_TWO_SIDED_DATA",
            "rows": 0,
            "markets": 0,
        }

    raw = assign_gap_segments(raw, gap_segment_minutes)
    raw["bucket_ts"] = raw["observed_at"].dt.floor(f"{int(bucket_minutes)}min")
    raw = raw.sort_values(["slug", "segment", "observed_at"])
    q = (
        raw.groupby(["slug", "segment", "bucket_ts"], sort=False, as_index=False)
        .tail(1)
        .copy()
    )
    q["ts"] = q["bucket_ts"]
    q["probability"] = q["midpoint"]
    q["volume24hr"] = np.nan
    q["quote_price_kind"] = "MIDPOINT_NOT_TRADE"
    q["traded_price_available"] = q["last_trade"].notna()
    q["volume24hr_quality"] = "UNAVAILABLE_US_PUBLIC_BBO"
    q["known_gap_guard"] = f"OBSERVED_GAP_SEGMENT_{int(gap_segment_minutes)}M"
    q["source_dataset"] = "Polymarket US official public gateway BBO"
    q["source_license"] = "PUBLIC_API_TERMS_NOT_ASSERTED"
    q = q.rename(columns={"midpoint": "_raw_midpoint"})
    q["probability"] = q["_raw_midpoint"]
    q = compute_probability_deltas(
        q[
            [
                "ts",
                "slug",
                "question",
                "category",
                "theme",
                "semantic_channel",
                "risk_prior_sign",
                "segment",
                "probability",
                "bid",
                "ask",
                "spread",
                "volume24hr",
                "quote_price_kind",
                "traded_price_available",
                "volume24hr_quality",
                "known_gap_guard",
                "source_dataset",
                "source_license",
            ]
        ].copy()
    )
    cols = [
        "ts",
        "slug",
        "question",
        "category",
        "theme",
        "semantic_channel",
        "risk_prior_sign",
        "segment",
        "probability",
        "poly_delta_10m",
        "poly_delta_1h",
        "poly_velocity_1h",
        "bid",
        "ask",
        "spread",
        "volume24hr",
        "quote_price_kind",
        "traded_price_available",
        "volume24hr_quality",
        "known_gap_guard",
        "source_dataset",
        "source_license",
    ]
    q = q[cols].sort_values(["ts", "slug"]).reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(output_path.suffix + ".tmp")
    q.to_parquet(tmp, index=False)
    check = pd.read_parquet(tmp)
    if len(check) != len(q):
        tmp.unlink(missing_ok=True)
        raise RuntimeError("canonical post-write row count mismatch")
    tmp.replace(output_path)
    return {
        "status": "CANONICAL_READY",
        "rows": int(len(q)),
        "markets": int(q["slug"].nunique()),
        "min_ts": q["ts"].min().isoformat() if len(q) else None,
        "max_ts": q["ts"].max().isoformat() if len(q) else None,
        "one_hour_delta_rows": int(q["poly_delta_1h"].notna().sum()),
        "max_abs_delta_1h": (
            float(q["poly_delta_1h"].abs().max())
            if q["poly_delta_1h"].notna().any()
            else None
        ),
    }


def run_oos(
    *,
    canonical_path: Path,
    asset_path: Path,
    spec_path: Path,
    output_dir: Path,
    bootstrap_iterations: int,
) -> dict[str, Any]:
    if not canonical_path.exists():
        return {"status": "WAITING_FOR_OOS_DATA", "reason": "canonical missing"}

    prediction = pd.read_parquet(canonical_path)
    spec, spec_sha = load_spec(spec_path)
    symbol = str(spec["hypothesis"]["symbol"])
    asset = load_asset_history(asset_path, symbol)
    payload, rows = evaluate_frozen_hypothesis(
        prediction,
        asset,
        spec,
        bootstrap_iterations=int(bootstrap_iterations),
    )
    payload["spec_sha256"] = spec_sha
    payload["source"] = "Polymarket US official prospective BBO collector"
    payload["production_promotion"] = False
    payload["r51_mutated"] = False
    payload["auto_promote"] = False
    payload["trade_execution"] = False

    output_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(output_dir / "oos_summary.json", payload)
    if not rows.empty:
        tmp = output_dir / "oos_aligned_rows.parquet.tmp"
        rows.to_parquet(tmp, index=False)
        tmp.replace(output_dir / "oos_aligned_rows.parquet")
    return payload


def run_cycle(
    *,
    config: dict[str, Any],
    prediction_config: dict[str, Any],
) -> dict[str, Any]:
    paths = config["paths"]
    collection = config["collection"]
    collect_status = collect_once(
        config=config,
        prediction_config=prediction_config,
    )
    health_status = evaluate_and_rollback_if_needed(
        collect_status,
        sqlite_path=Path(paths["sqlite"]),
        gate=config.get("health_gate", {}),
    )
    collect_status["source_health"] = health_status

    if (
        bool(config.get("health_gate", {}).get("fail_closed"))
        and not bool(health_status.get("passed", True))
    ):
        payload = {
            "schema": "kalman-prediction-market-us-live-v0.1",
            "checked_at_utc": now_iso(),
            "collect": collect_status,
            "canonical": {
                "status": "FROZEN_SOURCE_HEALTH_FAIL",
                "reason": "source-health gate failed; canonical unchanged",
            },
            "ledger": {
                "status": "FROZEN_SOURCE_HEALTH_FAIL",
                "reason": "source-health gate failed; ledger unchanged",
                "production_promotion": False,
                "r51_mutated": False,
                "trade_execution": False,
            },
            "oos": {
                "status": "FROZEN_SOURCE_HEALTH_FAIL",
                "reason": "source-health gate failed; OOS not evaluated",
                "production_promotion": False,
                "r51_mutated": False,
                "auto_promote": False,
                "trade_execution": False,
            },
            "safety": config["safety"],
        }
        write_json_atomic(Path(paths["status"]), payload)
        print(json.dumps(payload, indent=2, default=str))
        return payload

    canonical_status = build_canonical(
        sqlite_path=Path(paths["sqlite"]),
        output_path=Path(paths["canonical"]),
        bucket_minutes=int(collection["canonical_bucket_minutes"]),
        gap_segment_minutes=int(collection["gap_segment_minutes"]),
    )

    ledger_status = update_ledger(
        canonical_path=Path(paths["canonical"]),
        asset_path=Path(config["oos"]["asset"]),
        spec_path=Path(config["oos"]["spec"]),
        sqlite_path=Path(paths["event_ledger_sqlite"]),
        parquet_path=Path(paths["event_ledger_parquet"]),
    )

    oos_status = {"status": "DISABLED"}
    if bool(config["oos"]["enabled"]):
        oos_status = run_oos(
            canonical_path=Path(paths["canonical"]),
            asset_path=Path(config["oos"]["asset"]),
            spec_path=Path(config["oos"]["spec"]),
            output_dir=Path(paths["oos_dir"]),
            bootstrap_iterations=int(config["oos"]["bootstrap_iterations"]),
        )

    payload = {
        "schema": "kalman-prediction-market-us-live-v0.1",
        "checked_at_utc": now_iso(),
        "collect": collect_status,
        "canonical": canonical_status,
        "ledger": ledger_status,
        "oos": oos_status,
        "safety": config["safety"],
    }
    write_json_atomic(Path(paths["status"]), payload)
    print(json.dumps(payload, indent=2, default=str))
    return payload


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Polymarket US prospective read-only collector v0")
    p.add_argument(
        "command",
        choices=["collect", "canonicalize", "oos", "run"],
        default="run",
        nargs="?",
    )
    p.add_argument("--config", required=True)
    p.add_argument("--prediction-config", required=True)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    cfg = read_json(Path(args.config))
    prediction_cfg = load_prediction_config(Path(args.prediction_config))
    paths = cfg["paths"]

    try:
        if args.command == "collect":
            result = collect_once(config=cfg, prediction_config=prediction_cfg)
        elif args.command == "canonicalize":
            result = build_canonical(
                sqlite_path=Path(paths["sqlite"]),
                output_path=Path(paths["canonical"]),
                bucket_minutes=int(cfg["collection"]["canonical_bucket_minutes"]),
                gap_segment_minutes=int(cfg["collection"]["gap_segment_minutes"]),
            )
        elif args.command == "oos":
            result = run_oos(
                canonical_path=Path(paths["canonical"]),
                asset_path=Path(cfg["oos"]["asset"]),
                spec_path=Path(cfg["oos"]["spec"]),
                output_dir=Path(paths["oos_dir"]),
                bootstrap_iterations=int(cfg["oos"]["bootstrap_iterations"]),
            )
        else:
            result = run_cycle(config=cfg, prediction_config=prediction_cfg)
        return 0
    except Exception as exc:
        payload = {
            "schema": "kalman-prediction-market-us-live-v0.1",
            "checked_at_utc": now_iso(),
            "status": "ERROR_FAIL_CLOSED",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "safety": cfg.get("safety"),
        }
        write_json_atomic(Path(paths["status"]), payload)
        print(json.dumps(payload, indent=2, default=str))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
