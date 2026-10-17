from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

UTC = timezone.utc
FEATURE_VERSION = "prediction-market-v0"
DEFAULT_CONFIG = Path("config/prediction-market-layer-v0.json")


class LegalAccessRestricted(RuntimeError):
    pass


@dataclass(frozen=True)
class FetchStatus:
    status: str
    http_status: int | None = None
    detail: str | None = None


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def parse_dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def parse_jsonish(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def classify_theme(text: str, config: dict[str, Any]) -> str:
    low = text.lower()
    for theme, keywords in (config.get("theme_keywords") or {}).items():
        if any(str(k).lower() in low for k in keywords):
            return str(theme).upper()
    return "OTHER"


def semantic_channel(text: str, config: dict[str, Any]) -> tuple[str, int | None]:
    low = text.lower()
    for name, spec in (config.get("semantic_rules") or {}).items():
        for pattern in spec.get("patterns") or []:
            terms = [str(x).lower() for x in pattern]
            if terms and all(term in low for term in terms):
                sign = spec.get("risk_prior_sign")
                return str(name).upper(), int(sign) if sign in (-1, 1) else None
    return "UNMAPPED", None


def contract_semantics(
    slug: str,
    question: str,
    theme: str,
    config: dict[str, Any],
) -> tuple[str, int | None]:
    s = str(slug or "").lower()
    q = str(question or "").lower()
    theme = str(theme or "OTHER").upper()

    if theme == "FED_POLICY":
        if "-cut" in s or "rate cut" in q:
            return "FED_EASING", 1
        if "-hike" in s or "rate hike" in q:
            return "FED_TIGHTENING", -1
        return semantic_channel(" ".join([s, q]), config)

    if theme == "INFLATION":
        if "-gt" in s or " above " in f" {q} ":
            return "INFLATION_UPSIDE", -1
        if "-lt" in s or " below " in f" {q} ":
            return "INFLATION_DOWNSIDE", 1
        return "UNMAPPED", None

    if theme == "FISCAL_POLICY" and "shutdown" in q:
        return "GOVERNMENT_SHUTDOWN", -1

    if theme == "RECESSION_GROWTH":
        if "recession" in q:
            return "RECESSION_RISK", -1
        return "UNMAPPED", None

    if theme == "GEOPOLITICS":
        if "ceasefire" in q or "peace agreement" in q:
            return "GEOPOLITICAL_DEESCALATION", 1
        if (
            "invasion" in q
            or "military strike" in q
            or "military attack" in q
            or "war between" in q
        ):
            return "GEOPOLITICAL_RISK", -1
        return "UNMAPPED", None

    return semantic_channel(" ".join([s, q]), config)


def yes_probability(market: dict[str, Any]) -> tuple[float | None, str | None]:
    outcomes = [str(x).strip() for x in parse_jsonish(market.get("outcomes"))]
    prices = parse_jsonish(market.get("outcomePrices"))
    if len(outcomes) != len(prices) or not outcomes:
        return None, None
    yes_idx = next((i for i, x in enumerate(outcomes) if x.lower() == "yes"), None)
    if yes_idx is None:
        return None, None
    p = as_float(prices[yes_idx])
    if p is None or not (0.0 <= p <= 1.0):
        return None, None
    tokens = [str(x) for x in parse_jsonish(market.get("clobTokenIds"))]
    token_id = tokens[yes_idx] if len(tokens) == len(outcomes) else None
    return p, token_id


def normalize_market(
    market: dict[str, Any],
    *,
    observed_at: datetime,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    p, yes_token_id = yes_probability(market)
    if p is None:
        return None

    question = str(market.get("question") or "").strip()
    category = str(market.get("category") or "").strip()
    description = str(market.get("description") or "").strip()
    text = " ".join([question, category, description])
    end_at = parse_dt(market.get("endDate") or market.get("endDateIso"))
    updated_at = parse_dt(market.get("updatedAt"))
    hours_to_event = (
        (end_at - observed_at).total_seconds() / 3600.0 if end_at is not None else None
    )
    age_minutes = (
        max(0.0, (observed_at - updated_at).total_seconds() / 60.0)
        if updated_at is not None
        else None
    )

    liquidity = as_float(market.get("liquidityNum"))
    if liquidity is None:
        liquidity = as_float(market.get("liquidity"))
    volume24h = as_float(market.get("volume24hr"))
    spread = as_float(market.get("spread"))
    best_bid = as_float(market.get("bestBid"))
    best_ask = as_float(market.get("bestAsk"))
    if spread is None and best_bid is not None and best_ask is not None:
        spread = max(0.0, best_ask - best_bid)

    theme = classify_theme(text, config)
    channel, risk_prior_sign = contract_semantics(
        str(market.get("slug") or ""),
        question,
        theme,
        config,
    )

    return {
        "feature_version": FEATURE_VERSION,
        "provider": "POLYMARKET",
        "observed_at": iso(observed_at),
        "market_id": str(market.get("id") or market.get("conditionId") or market.get("slug") or ""),
        "condition_id": market.get("conditionId"),
        "slug": market.get("slug"),
        "question": question,
        "category": category,
        "theme": theme,
        "semantic_channel": channel,
        "risk_prior_sign": risk_prior_sign,
        "yes_token_id": yes_token_id,
        "poly_prob": p,
        "poly_delta_10m": None,
        "poly_delta_1h": None,
        "poly_velocity_1h": None,
        "liquidity_usd": liquidity,
        "volume_24h_usd": volume24h,
        "spread": spread,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "last_trade_price": as_float(market.get("lastTradePrice")),
        "one_hour_price_change": as_float(market.get("oneHourPriceChange")),
        "one_day_price_change": as_float(market.get("oneDayPriceChange")),
        "hours_to_event": hours_to_event,
        "source_age_minutes": age_minutes,
        "end_at": iso(end_at) if end_at else None,
        "updated_at": iso(updated_at) if updated_at else None,
        "enable_order_book": bool(market.get("enableOrderBook")),
        "accepting_orders": bool(market.get("acceptingOrders")),
        "restricted": bool(market.get("restricted")),
        "r51_scoring_enabled": False,
        "trade_execution_enabled": False,
        "challenger_only": True,
    }


def eligibility(record: dict[str, Any], config: dict[str, Any]) -> tuple[bool, list[str]]:
    q = config.get("quality_gate") or {}
    reasons: list[str] = []
    if record["theme"] == "OTHER":
        reasons.append("OUT_OF_SCOPE_THEME")
    if (record.get("liquidity_usd") or 0.0) < float(q.get("min_liquidity_usd", 5000)):
        reasons.append("LOW_LIQUIDITY")
    if (record.get("volume_24h_usd") or 0.0) < float(q.get("min_volume_24h_usd", 0)):
        reasons.append("LOW_24H_VOLUME")
    spread = record.get("spread")
    if spread is not None and spread > float(q.get("max_spread", 0.10)):
        reasons.append("WIDE_SPREAD")
    h = record.get("hours_to_event")
    if h is not None and h < float(q.get("min_hours_to_event", 2)):
        reasons.append("TOO_CLOSE_TO_RESOLUTION")
    age = record.get("source_age_minutes")
    if age is not None and age > float(q.get("max_source_age_minutes", 360)):
        reasons.append("STALE_MARKET_METADATA")
    if not record.get("market_id"):
        reasons.append("MISSING_MARKET_ID")
    return not reasons, reasons


def fetch_gamma_markets(
    config: dict[str, Any],
    *,
    client: httpx.Client | None = None,
) -> tuple[list[dict[str, Any]], FetchStatus]:
    provider = config.get("provider") or {}
    base_url = str(provider.get("gamma_markets_url", "https://gamma-api.polymarket.com/markets"))
    max_markets = int(provider.get("max_markets", 1000))
    page_size = min(int(provider.get("page_size", 250)), max_markets)
    timeout = float(provider.get("timeout_seconds", 20))
    min_liquidity = float((config.get("quality_gate") or {}).get("min_liquidity_usd", 5000))

    own_client = client is None
    http = client or httpx.Client(timeout=timeout, follow_redirects=True)
    rows: list[dict[str, Any]] = []
    try:
        offset = 0
        while len(rows) < max_markets:
            limit = min(page_size, max_markets - len(rows))
            response = http.get(
                base_url,
                params={
                    "limit": limit,
                    "offset": offset,
                    "closed": "false",
                    "liquidity_num_min": min_liquidity,
                    "order": "volume24hr",
                    "ascending": "false",
                },
            )
            if response.status_code == 451:
                raise LegalAccessRestricted("Polymarket returned HTTP 451")
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise RuntimeError("Gamma markets response is not a list")
            rows.extend(x for x in payload if isinstance(x, dict))
            if len(payload) < limit:
                break
            offset += limit
        return rows, FetchStatus("OK", 200, f"{len(rows)} markets")
    except LegalAccessRestricted:
        raise
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return [], FetchStatus("ERROR", status, f"{type(exc).__name__}: {exc}")
    finally:
        if own_client:
            http.close()


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prediction_market_snapshot (
            market_id TEXT NOT NULL,
            observed_ts INTEGER NOT NULL,
            observed_at TEXT NOT NULL,
            theme TEXT NOT NULL,
            semantic_channel TEXT NOT NULL,
            probability REAL NOT NULL,
            liquidity_usd REAL,
            volume_24h_usd REAL,
            spread REAL,
            question TEXT,
            payload_json TEXT NOT NULL,
            PRIMARY KEY (market_id, observed_ts)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_prediction_market_lookup "
        "ON prediction_market_snapshot(market_id, observed_ts)"
    )


def prior_probability(
    conn: sqlite3.Connection,
    *,
    market_id: str,
    target_ts: int,
    tolerance_seconds: int,
) -> float | None:
    row = conn.execute(
        """
        SELECT probability
        FROM prediction_market_snapshot
        WHERE market_id = ?
          AND observed_ts <= ?
          AND observed_ts >= ?
        ORDER BY observed_ts DESC
        LIMIT 1
        """,
        (market_id, target_ts, target_ts - tolerance_seconds),
    ).fetchone()
    return float(row[0]) if row else None


def add_history_features(
    records: list[dict[str, Any]],
    conn: sqlite3.Connection,
    observed_at: datetime,
) -> None:
    now_ts = int(observed_at.timestamp())
    for rec in records:
        p = float(rec["poly_prob"])
        p10 = prior_probability(
            conn, market_id=rec["market_id"], target_ts=now_ts - 600, tolerance_seconds=900
        )
        p1h = prior_probability(
            conn, market_id=rec["market_id"], target_ts=now_ts - 3600, tolerance_seconds=1800
        )
        rec["poly_delta_10m"] = round(p - p10, 12) if p10 is not None else None
        rec["poly_delta_1h"] = round(p - p1h, 12) if p1h is not None else None
        rec["poly_velocity_1h"] = rec["poly_delta_1h"]


def store_records(
    records: list[dict[str, Any]],
    conn: sqlite3.Connection,
    observed_at: datetime,
    retention_days: int,
) -> None:
    ts = int(observed_at.timestamp())
    for rec in records:
        conn.execute(
            """
            INSERT OR REPLACE INTO prediction_market_snapshot (
                market_id, observed_ts, observed_at, theme, semantic_channel,
                probability, liquidity_usd, volume_24h_usd, spread, question, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rec["market_id"],
                ts,
                rec["observed_at"],
                rec["theme"],
                rec["semantic_channel"],
                rec["poly_prob"],
                rec.get("liquidity_usd"),
                rec.get("volume_24h_usd"),
                rec.get("spread"),
                rec.get("question"),
                json.dumps(rec, ensure_ascii=False, sort_keys=True),
            ),
        )
    cutoff = ts - max(1, retention_days) * 86400
    conn.execute("DELETE FROM prediction_market_snapshot WHERE observed_ts < ?", (cutoff,))
    conn.commit()


def build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [r for r in records if r.get("eligible")]
    by_theme: dict[str, dict[str, Any]] = {}
    for theme in sorted({r["theme"] for r in eligible}):
        rows = [r for r in eligible if r["theme"] == theme]
        d10 = [abs(float(r["poly_delta_10m"])) for r in rows if r.get("poly_delta_10m") is not None]
        d1h = [abs(float(r["poly_delta_1h"])) for r in rows if r.get("poly_delta_1h") is not None]
        by_theme[theme] = {
            "market_count": len(rows),
            "max_abs_delta_10m": max(d10) if d10 else None,
            "max_abs_delta_1h": max(d1h) if d1h else None,
            "liquidity_usd": round(sum(float(r.get("liquidity_usd") or 0.0) for r in rows), 2),
            "volume_24h_usd": round(sum(float(r.get("volume_24h_usd") or 0.0) for r in rows), 2),
        }
    ranked = sorted(
        eligible,
        key=lambda r: (
            abs(float(r.get("poly_delta_10m") or 0.0)),
            float(r.get("volume_24h_usd") or 0.0),
        ),
        reverse=True,
    )
    return {
        "eligible_count": len(eligible),
        "theme_summary": by_theme,
        "top_movers": ranked[:20],
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def build_payload(
    *,
    raw_markets: list[dict[str, Any]],
    observed_at: datetime,
    config: dict[str, Any],
    db_path: Path,
    provider_status: FetchStatus,
) -> dict[str, Any]:
    normalized = [
        r
        for m in raw_markets
        if (r := normalize_market(m, observed_at=observed_at, config=config)) is not None
    ]
    for rec in normalized:
        ok, reasons = eligibility(rec, config)
        rec["eligible"] = ok
        rec["quality_blockers"] = reasons

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        init_db(conn)
        add_history_features(normalized, conn, observed_at)
        store_records(normalized, conn, observed_at, int(config.get("retention_days", 180)))

    summary = build_summary(normalized)
    return {
        "feature_version": FEATURE_VERSION,
        "status": "READY",
        "observed_at": iso(observed_at),
        "provider_status": provider_status.__dict__,
        "record_count": len(normalized),
        **summary,
        "markets": normalized,
        "safety": {
            "read_only": True,
            "r51_scoring_enabled": False,
            "trade_execution_enabled": False,
            "order_endpoints_used": False,
            "geoblock_bypass_attempted": False,
        },
    }


def blocked_payload(observed_at: datetime, detail: str) -> dict[str, Any]:
    return {
        "feature_version": FEATURE_VERSION,
        "status": "BLOCKED_LEGAL_ACCESS",
        "observed_at": iso(observed_at),
        "provider_status": {
            "status": "LEGAL_ACCESS_RESTRICTED",
            "http_status": 451,
            "detail": detail,
        },
        "record_count": 0,
        "eligible_count": 0,
        "theme_summary": {},
        "top_movers": [],
        "markets": [],
        "safety": {
            "read_only": True,
            "r51_scoring_enabled": False,
            "trade_execution_enabled": False,
            "order_endpoints_used": False,
            "geoblock_bypass_attempted": False,
        },
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Kalman Prediction Market Layer v0 (read-only)")
    p.add_argument("command", choices=["collect", "status", "selftest"])
    p.add_argument("--config", default=str(DEFAULT_CONFIG))
    p.add_argument("--fixture")
    p.add_argument("--output")
    p.add_argument("--db")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(Path(args.config))
    output = Path(args.output or config["output"]["latest_json"])
    db_path = Path(args.db or config["output"]["sqlite_db"])
    observed_at = utc_now()

    if args.command == "status":
        if output.exists():
            print(output.read_text(encoding="utf-8"))
        else:
            print(json.dumps({"status": "NO_SNAPSHOT", "path": str(output)}, indent=2))
        return 0

    if args.command == "selftest":
        sample = {
            "id": "demo-fed-cut",
            "question": "Will the Fed cut interest rates at the next meeting?",
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.64","0.36"]',
            "clobTokenIds": '["yes-token","no-token"]',
            "liquidityNum": 25000,
            "volume24hr": 120000,
            "spread": 0.02,
            "endDate": "2030-01-01T00:00:00Z",
        }
        rec = normalize_market(sample, observed_at=observed_at, config=config)
        assert rec and rec["poly_prob"] == 0.64 and rec["theme"] == "FED_POLICY"
        ok, reasons = eligibility(rec, config)
        assert ok and reasons == []
        print(json.dumps({"status": "PASS", "feature_version": FEATURE_VERSION}, indent=2))
        return 0

    if args.fixture:
        fixture_payload = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
        raw_markets = (
            fixture_payload if isinstance(fixture_payload, list) else fixture_payload.get("markets", [])
        )
        provider_status = FetchStatus("FIXTURE", None, str(args.fixture))
    else:
        try:
            raw_markets, provider_status = fetch_gamma_markets(config)
        except LegalAccessRestricted as exc:
            payload = blocked_payload(observed_at, str(exc))
            write_json(output, payload)
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

    if provider_status.status == "ERROR":
        payload = {
            **blocked_payload(observed_at, provider_status.detail or "provider error"),
            "status": "PROVIDER_ERROR",
            "provider_status": provider_status.__dict__,
        }
        write_json(output, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2

    payload = build_payload(
        raw_markets=raw_markets,
        observed_at=observed_at,
        config=config,
        db_path=db_path,
        provider_status=provider_status,
    )
    write_json(output, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
