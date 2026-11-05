"""Fast position PRICE CHECK ONLY, never places orders or mutates trade state.

Runs on a two-minute cron, independently of 5-minute LIVE execution checks.
The two-confirmation LIVE guard state is deliberately NOT updated by this
script; it is evaluated only by the existing execution/position_manager cycle.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import sqlite3
import sys


def get_active_positions(path: Path) -> list[dict]:
    """Use an immutable SQLite snapshot connection. Does not run migrations."""
    uri = f"file:{path.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(
            """SELECT position_id,symbol,state,entry_avg_fill_price,
                      peak_price_return,profit_flip_armed,profit_flip_negative_count,
                      exit_pending_reason,entry_count
               FROM managed_position WHERE state IN ('OPEN','EXIT_RESERVED','EXIT_SUBMITTED')
               ORDER BY created_at"""
        )]


def parse_last_price(payload, symbol: str) -> Decimal:
    from app.market_guard import unwrap
    payload = unwrap(payload) or []
    rows = payload if isinstance(payload, list) else payload.get("items",[]) if isinstance(payload, dict) else []
    matched = [row for row in rows if str(row.get("symbol","")).upper() == symbol.upper()]
    # Same broker response contract as position_manager._last_price.
    row = matched[0] if matched else (rows[0] if rows else None)
    if row is None:
        raise ValueError("EMPTY_PRICE_RESPONSE")
    price = Decimal(str(row.get("lastPrice") or "0"))
    if not price.is_finite() or price <= 0:
        raise ValueError("INVALID_PRICE")
    return price


async def snapshot() -> dict:
    from dotenv import load_dotenv
    from app.config import Settings
    from app.toss_client import TossClient
    load_dotenv(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"), override=True)
    settings = Settings()
    threshold = Decimal(os.environ.get("AUTO_TRADE_PROFIT_FLIP_TRIGGER_PCT", "-0.002"))
    arm = Decimal(os.environ.get("AUTO_TRADE_PROFIT_FLIP_ARM_PCT", "0.002"))
    stop = Decimal(os.environ.get("AUTO_TRADE_STOP_LOSS_PCT", "-0.03"))
    positions = get_active_positions(settings.state_db_path)
    result = {"schema":"kalman-profit-flip-fast-readonly-v1",
              "observed_at_utc":datetime.now(timezone.utc).isoformat(),
              "interval_label":"2m","order_submission":False,
              "trade_state_mutation":False,"live_confirmations_incremented":False,
              "flip_threshold_pct":float(threshold * 100),
              "position_count":len(positions),"positions":[]}
    if not positions:
        return result
    client = TossClient(settings)
    for position in positions:
        sym = position["symbol"]
        record = {"symbol":sym,"state":position["state"],
                  "entry_count":position["entry_count"],
                  "pending_exit":position.get("exit_pending_reason"),
                  "persisted_confirmations":position.get("profit_flip_negative_count")}
        try:
            price = parse_last_price(await client.prices([sym]),sym)
            entry = Decimal(str(position.get("entry_avg_fill_price") or "0"))
            if entry <= 0:
                raise ValueError("INVALID_ENTRY_BASIS")
            current = price / entry - Decimal("1")
            peak = Decimal(str(position["peak_price_return"])) if position.get("peak_price_return") not in (None,"") else current
            armed = bool(position.get("profit_flip_armed")) or max(current,peak) >= arm
            record.update({"last_price":str(price),
                           "price_return_pct":round(float(current*100),4),
                           "armed":armed,
                           "under_new_flip_threshold":bool(armed and current <= threshold),
                           "under_stop_loss":bool(current <= stop),
                           "observation_only":True})
        except Exception as exc:
            # No tokens, account identifiers, authenticated responses or secret text.
            record["quote_status"]="ERROR_"+type(exc).__name__
        result["positions"].append(record)
    return result


def main() -> int:
    try:
        report = asyncio.run(snapshot())
        print(json.dumps(report,ensure_ascii=False,sort_keys=True))
        return 0 if not any("quote_status" in r for r in report["positions"]) else 3
    except Exception as exc:
        print(json.dumps({"schema":"kalman-profit-flip-fast-readonly-v1",
                          "status":"ERROR_"+type(exc).__name__}),file=sys.stderr)
        return 2


if __name__=="__main__":
    sys.exit(main())
