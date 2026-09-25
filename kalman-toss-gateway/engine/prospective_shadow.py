from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

def choose_candidate_exit_reason(
    *,
    price_return: Decimal,
    stop_loss: Decimal,
    take_profit: Decimal,
    elapsed_buckets: int,
    target_buckets: int,
) -> str | None:
    if price_return <= stop_loss:
        return "STOP_LOSS_3PCT"
    if price_return >= take_profit:
        return "TAKE_PROFIT_20PCT"
    if elapsed_buckets >= target_buckets:
        return "MAX_HOLD_4_BUCKETS"
    return None

from app.market_guard import unwrap, us_fractional_order_window
from app.managed_positions import ManagedPositionStore
from app.prospective_shadow import (
    ProspectiveShadowConfig,
    ProspectiveShadowStore,
)
from app.toss_client import TossClient


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or "0"))


async def _last_price(client: TossClient, symbol: str) -> Decimal:
    payload = unwrap(await client.prices([symbol])) or []
    rows = (
        payload
        if isinstance(payload, list)
        else payload.get("items", [])
        if isinstance(payload, dict)
        else []
    )
    if not rows:
        raise RuntimeError(f"No current price returned for {symbol}")
    price = _decimal(rows[0].get("lastPrice"))
    if price <= 0:
        raise RuntimeError(f"Invalid current price returned for {symbol}")
    return price


async def manage_prospective_shadows(
    *,
    config: ProspectiveShadowConfig,
    shadow_store: ProspectiveShadowStore,
    managed_store: ManagedPositionStore,
    client: TossClient,
    db_url: str,
    elapsed_buckets_fn: Callable[[str, str], int],
    price_overrides: dict[str, Decimal] | None = None,
    watch_source: str | None = None,
) -> list[dict[str, Any]]:
    """Advance the frozen no-profit-flip candidate without broker writes."""

    if not config.enabled:
        return []

    price_overrides = dict(price_overrides or {})
    source = (watch_source or os.environ.get("KALMAN_WATCH_SOURCE") or "UNKNOWN").strip()
    reports: list[dict[str, Any]] = []
    window_cache: tuple[bool, dict] | None = None

    for shadow in shadow_store.open_positions(config.candidate_id):
        live_position_id = str(shadow["live_position_id"])
        symbol = str(shadow["symbol"]).upper()
        live = managed_store.get(live_position_id) or {}
        live_state = str(live.get("state") or "").upper() or None
        live_exit_reason = live.get("exit_reason")

        shadow_store.update_live_link(
            config.candidate_id,
            live_position_id,
            live_state=live_state,
            live_exit_reason=live_exit_reason,
        )

        try:
            entry_price = _decimal(shadow.get("entry_average_price"))
            if entry_price <= 0:
                raise RuntimeError("shadow entry price is invalid")

            price = price_overrides.get(live_position_id)
            price_source = "LIVE_MANAGER_SAME_TICK"
            if price is None:
                price = await _last_price(client, symbol)
                price_source = "TOSS_PRICE_FETCH"

            price_return = price / entry_price - Decimal("1")
            elapsed = elapsed_buckets_fn(db_url, str(shadow["entry_signal_as_of"]))
            reason = choose_candidate_exit_reason(
                price_return=price_return,
                stop_loss=config.stop_loss,
                take_profit=config.take_profit,
                elapsed_buckets=elapsed,
                target_buckets=config.target_exit_buckets,
            )

            window_open = False
            window_info: dict[str, Any] | None = None
            if reason is not None:
                if window_cache is None:
                    opened, info = await us_fractional_order_window(client)
                    window_cache = (bool(opened), dict(info or {}))
                window_open, window_info = window_cache

            close_shadow = bool(reason is not None and window_open)
            observed_at = datetime.now(timezone.utc).isoformat()
            updated = shadow_store.observe(
                candidate_id=config.candidate_id,
                live_position_id=live_position_id,
                observed_at=observed_at,
                watch_source=source,
                price=price,
                price_return=price_return,
                elapsed_buckets=elapsed,
                order_window_open=window_open,
                exit_signal_reason=reason,
                live_state=live_state,
                live_exit_reason=live_exit_reason,
                close_shadow=close_shadow,
            )

            reports.append(
                {
                    "action": (
                        "SHADOW_EXIT"
                        if close_shadow
                        else "SHADOW_EXIT_DUE_WINDOW_CLOSED"
                        if reason
                        else "SHADOW_HOLD"
                    ),
                    "candidateId": config.candidate_id,
                    "candidateFingerprint": config.fingerprint,
                    "livePositionId": live_position_id,
                    "symbol": symbol,
                    "watchSource": source,
                    "priceSource": price_source,
                    "entryAveragePrice": str(entry_price),
                    "lastPrice": str(price),
                    "priceReturn": str(price_return),
                    "elapsedCanonicalBuckets": elapsed,
                    "targetExitBuckets": config.target_exit_buckets,
                    "exitReason": reason,
                    "orderWindowOpen": window_open,
                    "marketWindow": window_info,
                    "liveState": live_state,
                    "liveExitReason": live_exit_reason,
                    "shadowState": updated.get("state") if updated else None,
                    "brokerOrderAttempted": False,
                }
            )
        except Exception as exc:
            reports.append(
                {
                    "action": "SHADOW_OBSERVATION_ERROR",
                    "candidateId": config.candidate_id,
                    "livePositionId": live_position_id,
                    "symbol": symbol,
                    "error": f"{type(exc).__name__}: {exc}",
                    "brokerOrderAttempted": False,
                }
            )

    return reports


def print_shadow_cycle(reports: list[dict[str, Any]]) -> None:
    print(
        json.dumps(
            {
                "prospectiveShadow": True,
                "brokerOrderAttempted": False,
                "reports": reports,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
