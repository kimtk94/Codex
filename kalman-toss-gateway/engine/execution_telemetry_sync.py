from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from pathlib import Path

import httpx
from dotenv import load_dotenv

from app.config import Settings
from app.executor import TradeLedger
from app.market_guard import unwrap
from app.toss_client import TossClient
from engine.position_manager import _broker_order_telemetry


DEFAULT_LIMIT = 100
MAX_RETRY_AFTER_SECONDS = 5.0


def _broker_orders(path: Path, limit: int) -> list[dict]:
    if not path.exists():
        return []
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT client_order_id,toss_order_id,symbol,side,status,created_at,telemetry_json
            FROM order_guard
            WHERE toss_order_id IS NOT NULL AND trim(toss_order_id) <> ''
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    return [dict(row) for row in rows]


async def _fetch_order_with_bounded_429_retry(
    client: TossClient,
    order_id: str,
    *,
    max_attempts: int = 2,
) -> dict:
    attempts = 0
    while True:
        attempts += 1
        try:
            payload = await client.order(order_id)
            data = unwrap(payload) or {}
            if not isinstance(data, dict):
                raise RuntimeError(f"Unexpected Toss order payload for {order_id}")
            return data
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status != 429 or attempts >= max_attempts:
                raise
            retry_after = client.last_response_meta.get("retry_after_seconds")
            try:
                delay = float(retry_after)
            except (TypeError, ValueError):
                delay = 1.0
            await asyncio.sleep(max(0.0, min(delay, MAX_RETRY_AFTER_SECONDS)))


async def main_async() -> int:
    load_dotenv(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"), override=True)
    settings = Settings()
    state_db = Path(os.environ.get("TRADING_STATE_DB", str(settings.state_db_path)))
    limit = int(os.environ.get("EXECUTION_TELEMETRY_SYNC_LIMIT", str(DEFAULT_LIMIT)))
    if limit < 1 or limit > 1000:
        raise RuntimeError("EXECUTION_TELEMETRY_SYNC_LIMIT must be between 1 and 1000")

    rows = _broker_orders(state_db, limit)
    if not rows:
        print(json.dumps({"status": "SKIP", "reason": "NO_BROKER_ORDERS", "orders": 0}))
        return 0

    ledger = TradeLedger(state_db)
    client = TossClient(settings)
    synced = 0
    failed = []

    for row in rows:
        try:
            order = await _fetch_order_with_bounded_429_retry(client, row["toss_order_id"])
            ledger.patch_telemetry(
                row["client_order_id"],
                {
                    "broker_order": _broker_order_telemetry(
                        order,
                        getattr(client, "last_response_meta", {}),
                    )
                },
            )
            synced += 1
        except Exception as exc:
            failed.append(
                {
                    "client_order_id": row["client_order_id"],
                    "order_id": row["toss_order_id"],
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    report = {
        "status": "SYNCED" if not failed else "PARTIAL",
        "orders": len(rows),
        "synced": synced,
        "failed": len(failed),
        "failures": failed[:10],
        "read_only_broker_calls": True,
    }
    print(json.dumps(report, ensure_ascii=False, default=str))
    return 0 if not failed else 2


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
