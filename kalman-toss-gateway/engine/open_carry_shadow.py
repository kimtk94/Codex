"""Prospective shadow for an early-session R5.1 carry entry.

This module never submits a broker order. It observes the prior session's final
R5.1 Top1 signal at the next US open and records a two-step 5K + 5K hypothetical
entry:
- 09:30 ET: capture open baseline price.
- 09:35 ET: leg 1 is eligible when prior Top1 score clears the frozen
  confidence threshold and first-5m momentum is positive.
- 09:40 ET: leg 2 is eligible only when leg 1 qualified and price has not
  weakened versus 09:35.
- 09:45 ET: fallback evaluation only if 09:40 was missed; a failed 09:40
  decision is not retried.

The target exposure is KRW 10,000 while the single-order contract remains
KRW 5,000. Existing hourly LIVE execution is not changed.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
from dotenv import load_dotenv

from app.config import Settings
from app.managed_positions import ManagedPositionStore
from app.market_guard import unwrap, us_fractional_order_window
from app.toss_client import TossClient
from engine.r5_conditional_live import _rank_context_from_same_run
from engine.open_carry_policy import (
    CHUNK_KRW,
    STRATEGY,
    TARGET_KRW,
    evaluate_leg1,
    evaluate_leg2,
)

NY = ZoneInfo("America/New_York")


def _state_path() -> Path:
    return Path(os.environ.get("OPEN_CARRY_SHADOW_STATE_PATH", "/opt/kalman/state/open_carry_shadow.json"))


def _load_state() -> dict:
    path = _state_path()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_state(payload: dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


def _session_open_utc(now_ny: datetime) -> datetime:
    return datetime.combine(now_ny.date(), time(9, 30), tzinfo=NY).astimezone(timezone.utc)


def _latest_prior_signal(db_url: str, cutoff_utc: datetime) -> dict | None:
    sql = """
        SELECT s.symbol, s.as_of, s.run_id, s.strategy_version, s.payload,
               s.signal, s.position_state, s.risk_gate, s.entry_allowed
        FROM strategy_signal s
        JOIN dashboard_snapshot d ON d.run_id=s.run_id AND d.market=s.market
        WHERE s.market='US'
          AND s.strategy_version=%s
          AND s.as_of < %s
          AND d.status='READY'
          AND s.signal='SHADOW'
          AND upper(COALESCE(s.position_state,''))='FLAT'
          AND lower(COALESCE(s.payload->>'allow_trade_shadow','false'))='true'
        ORDER BY s.as_of DESC
        LIMIT 1
    """
    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.execute(sql, (STRATEGY, cutoff_utc))
        row = cur.fetchone()
    if not row:
        return None
    return {
        "symbol": str(row[0]).upper(),
        "as_of": row[1],
        "run_id": row[2],
        "strategy_version": row[3],
        "payload": row[4] if isinstance(row[4], dict) else {},
        "signal": row[5],
        "position_state": row[6],
        "risk_gate": row[7],
        "entry_allowed": row[8],
    }


async def _last_price(client: TossClient, symbol: str) -> Decimal:
    payload = unwrap(await client.prices([symbol])) or []
    rows = payload if isinstance(payload, list) else payload.get("items", []) if isinstance(payload, dict) else []
    if not rows:
        raise RuntimeError(f"NO_PRICE:{symbol}")
    price = Decimal(str(rows[0].get("lastPrice") or "0"))
    if price <= 0:
        raise RuntimeError(f"INVALID_PRICE:{symbol}")
    return price


async def main_async() -> int:
    load_dotenv(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"), override=True)
    now_ny = datetime.now(timezone.utc).astimezone(NY)
    hm = (now_ny.hour, now_ny.minute)
    if hm not in {(9, 30), (9, 35), (9, 40), (9, 45)}:
        return 0

    db_url = os.environ.get("DATABASE_URL_WRITER") or os.environ.get("DATABASE_URL")
    if not db_url:
        print("OPEN_CARRY_SHADOW_SKIP reason=NO_DATABASE_URL")
        return 0

    settings = Settings()
    client = TossClient(settings)
    window_open, window_info = await us_fractional_order_window(client)
    if not window_open:
        print("OPEN_CARRY_SHADOW_SKIP reason=MARKET_WINDOW_CLOSED")
        return 0

    signal = _latest_prior_signal(db_url, _session_open_utc(now_ny))
    if not signal:
        print("OPEN_CARRY_SHADOW_SKIP reason=NO_PRIOR_SIGNAL")
        return 0

    rank1_score, rank2_symbol, rank2_score = _rank_context_from_same_run(signal)
    threshold = float(os.environ.get("AUTO_TRADE_CONDITIONAL_CONFIDENCE_THRESHOLD", "0.00041106678948450823"))
    symbol = str(signal["symbol"]).upper()
    price = await _last_price(client, symbol)
    session = now_ny.date().isoformat()
    state = _load_state()

    if hm == (9, 30):
        state = {
            "schema_version": "kalman-open-carry-shadow-v1",
            "mode": "SHADOW_NO_BROKER_ORDERS",
            "session_date_et": session,
            "captured_at": now_ny.isoformat(),
            "strategy_version": STRATEGY,
            "source_run_id": signal["run_id"],
            "source_signal_as_of": signal["as_of"].isoformat(),
            "symbol": symbol,
            "rank1_score": rank1_score,
            "rank2_symbol": rank2_symbol,
            "rank2_score": rank2_score,
            "confidence_threshold": threshold,
            "target_total_krw": TARGET_KRW,
            "chunk_krw": CHUNK_KRW,
            "open_price": str(price),
            "window": window_info,
            "leg1": None,
            "leg2": None,
        }
        _save_state(state)
        print(json.dumps({"status":"OPEN_CARRY_BASELINE_CAPTURED","symbol":symbol,"openPrice":str(price),"targetKrw":TARGET_KRW}, ensure_ascii=False))
        return 0

    if state.get("session_date_et") != session or state.get("source_run_id") != signal["run_id"] or state.get("symbol") != symbol:
        print("OPEN_CARRY_SHADOW_SKIP reason=NO_MATCHING_0930_BASELINE")
        return 0

    store = ManagedPositionStore(settings.state_db_path)
    active = store.active()
    active_same_symbol = any(str(x.get("symbol") or "").upper() == symbol for x in active)
    max_active = int(os.environ.get("AUTO_TRADE_MAX_ACTIVE_POSITIONS", "3") or 3)
    capacity_ok = len(active) < max_active and not active_same_symbol

    if hm == (9, 35):
        ok, momentum, reason = evaluate_leg1(rank1_score, threshold, Decimal(state["open_price"]), price)
        simulated_live_ok = bool(ok and capacity_ok)
        state["price_5m"] = str(price)
        state["leg1"] = {
            "evaluated_at": now_ny.isoformat(),
            "eligible": ok,
            "simulated_live_eligible": simulated_live_ok,
            "reason": reason if capacity_ok else "ACTIVE_POSITION_CAP_OR_SAME_SYMBOL",
            "momentum_5m": momentum,
            "target_krw": CHUNK_KRW,
            "active_positions": len(active),
            "same_symbol_active": active_same_symbol,
        }
        _save_state(state)
        print(json.dumps({"status":"OPEN_CARRY_LEG1_SHADOW","symbol":symbol,**state["leg1"]}, ensure_ascii=False, default=str))
        return 0

    if state.get("leg2") is not None:
        print("OPEN_CARRY_SHADOW_SKIP reason=LEG2_ALREADY_EVALUATED")
        return 0

    leg1 = state.get("leg1") or {}
    price_5m = Decimal(str(state.get("price_5m") or "0"))
    ok, continuation, reason = evaluate_leg2(bool(leg1.get("simulated_live_eligible")), price_5m, price)
    simulated_live_ok = bool(ok and capacity_ok)
    state["price_10m"] = str(price)
    state["leg2"] = {
        "evaluated_at": now_ny.isoformat(),
        "eligible": ok,
        "simulated_live_eligible": simulated_live_ok,
        "reason": reason if capacity_ok else "ACTIVE_POSITION_CAP_OR_SAME_SYMBOL",
        "continuation_5m": continuation,
        "target_krw": CHUNK_KRW,
        "target_total_krw_if_both": TARGET_KRW,
        "active_positions": len(active),
        "same_symbol_active": active_same_symbol,
    }
    _save_state(state)
    print(json.dumps({"status":"OPEN_CARRY_LEG2_SHADOW","symbol":symbol,**state["leg2"]}, ensure_ascii=False, default=str))
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
