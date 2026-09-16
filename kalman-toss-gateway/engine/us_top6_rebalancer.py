"""US-only R5.1 Top-6 live micro-basket reconciler.

This is intentionally separate from the research Forward SHADOW ledger:
- target basket: latest READY R5.1_BASE_HGB ranks 1..N (default N=6)
- execution market: US only
- per-symbol target notional: 5,000 KRW
- total target basket notional: 30,000 KRW
- non-target US holdings are sold before any new buys are submitted
- any open broker order blocks a new rebalance cycle

No KR/CRYPTO order path exists in this module.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_DOWN
from types import SimpleNamespace
from typing import Any

import psycopg
from dotenv import load_dotenv

from app.config import Settings
from app.executor import execute_order
from app.managed_positions import ManagedPositionStore
from app.market_guard import unwrap, us_fractional_order_window
from app.toss_client import TossClient

MODEL_VERSION = "R5.1_BASE_HGB"
MARKET = "US"


@dataclass(frozen=True)
class BasketTarget:
    rank: int
    symbol: str
    model_score: float | None
    reference_price: float | None


def _bool(value: Any) -> bool:
    return str(value or "").strip().lower() == "true"


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value if value is not None else "0"))
    except Exception:
        return Decimal("0")


def _client_order_id(run_id: str, symbol: str, side: str) -> str:
    side = side.upper()
    digest = hashlib.sha256(f"US_TOP6|{run_id}|{symbol.upper()}|{side}".encode()).hexdigest()[:12]
    clean = "".join(c for c in symbol.upper() if c.isalnum() or c in "-_")[:8]
    return f"k-us6-{side[0]}-{clean}-{digest}"[:36]


def _item_market_value_usd(item: dict[str, Any]) -> Decimal:
    mv = item.get("marketValue") or {}
    if isinstance(mv, dict):
        for key in ("amountAfterCost", "amount"):
            if mv.get(key) is not None:
                return max(Decimal("0"), _decimal(mv.get(key)))
    qty = _decimal(item.get("quantity"))
    last = _decimal(item.get("lastPrice"))
    return max(Decimal("0"), qty * last)


def _is_us_holding(item: dict[str, Any]) -> bool:
    country = str(item.get("marketCountry") or "").upper()
    currency = str(item.get("currency") or "").upper()
    return country == "US" or currency == "USD"


def _holding_quantity(item: dict[str, Any]) -> Decimal:
    return _decimal(item.get("quantity"))


def _holding_symbol(item: dict[str, Any]) -> str:
    return str(item.get("symbol") or "").upper().strip()


def _open_order_items(payload: Any) -> list[dict[str, Any]]:
    data = unwrap(payload) or {}
    if isinstance(data, dict):
        return list(data.get("orders") or data.get("items") or [])
    return list(data or [])


def _holding_items(payload: Any) -> list[dict[str, Any]]:
    data = unwrap(payload) or {}
    if isinstance(data, dict):
        return list(data.get("items") or [])
    return []


def load_target_basket(
    database_url: str,
    *,
    max_positions: int,
    max_age_minutes: int,
) -> tuple[str, datetime, list[BasketTarget]]:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    sql = """
        SELECT run_id,data_as_of,payload
        FROM dashboard_snapshot
        WHERE market='US'
          AND status='READY'
          AND model_version=%s
          AND stale_after > now()
          AND data_as_of >= %s
        ORDER BY data_as_of DESC, generated_at DESC
        LIMIT 1
    """
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute(sql, (MODEL_VERSION, cutoff))
        row = cur.fetchone()
    if not row:
        raise RuntimeError("NO_FRESH_R5_1_US_DASHBOARD")

    run_id, data_as_of, payload = row
    payload = payload or {}
    assets = payload.get("assets") or payload.get("top3") or []
    ranked = []
    for raw in assets:
        symbol = str(raw.get("symbol") or "").upper().strip()
        rank = int(raw.get("rank") or 0)
        if not symbol or rank <= 0:
            continue
        ranked.append(
            BasketTarget(
                rank=rank,
                symbol=symbol,
                model_score=float(raw["model_score"]) if raw.get("model_score") is not None else None,
                reference_price=float(raw["reference_price"]) if raw.get("reference_price") is not None else None,
            )
        )
    ranked.sort(key=lambda x: (x.rank, x.symbol))
    targets = ranked[:max_positions]
    if len(targets) != max_positions:
        raise RuntimeError(
            f"R5.1 target basket incomplete: expected={max_positions} got={len(targets)}"
        )
    if len({x.symbol for x in targets}) != len(targets):
        raise RuntimeError("R5.1 target basket contains duplicate symbols")
    return str(run_id), data_as_of, targets


def build_rebalance_plan(
    *,
    targets: list[BasketTarget],
    holdings: list[dict[str, Any]],
    fx_usd_krw: Decimal,
    per_symbol_target_krw: int,
    portfolio_limit_krw: int,
    min_order_krw: int,
) -> dict[str, Any]:
    if fx_usd_krw <= 0:
        raise ValueError("fx_usd_krw must be > 0")
    if len(targets) <= 0:
        raise ValueError("targets must not be empty")
    if per_symbol_target_krw <= 0 or portfolio_limit_krw <= 0:
        raise ValueError("portfolio limits must be > 0")
    if per_symbol_target_krw * len(targets) > portfolio_limit_krw:
        raise ValueError("target basket exceeds portfolio limit")

    target_symbols = [x.symbol for x in targets]
    target_set = set(target_symbols)

    us_holdings: dict[str, dict[str, Any]] = {}
    ignored_non_us: list[str] = []
    for item in holdings:
        symbol = _holding_symbol(item)
        qty = _holding_quantity(item)
        if not symbol or qty <= 0:
            continue
        if not _is_us_holding(item):
            ignored_non_us.append(symbol)
            continue
        us_holdings[symbol] = item

    sells = []
    for symbol, item in sorted(us_holdings.items()):
        if symbol not in target_set:
            sells.append(
                {
                    "symbol": symbol,
                    "quantity": str(_holding_quantity(item)),
                    "marketValueUsd": str(_item_market_value_usd(item)),
                    "reason": "NOT_IN_R5_1_TOP6",
                }
            )

    # Fail-safe sequencing: when a sell is needed, do not create buy orders in
    # the same cycle. The next scheduled pass observes settled broker state.
    if sells:
        return {
            "targetSymbols": target_symbols,
            "sells": sells,
            "buys": [],
            "ignoredNonUsHoldings": sorted(set(ignored_non_us)),
            "phase": "SELL_NON_TARGETS",
        }

    current_krw: dict[str, Decimal] = {}
    current_total = Decimal("0")
    for symbol in target_symbols:
        item = us_holdings.get(symbol)
        value = _item_market_value_usd(item) * fx_usd_krw if item else Decimal("0")
        current_krw[symbol] = value
        current_total += value

    remaining_budget = max(Decimal("0"), Decimal(portfolio_limit_krw) - current_total)
    buys = []
    for target in targets:
        current = current_krw[target.symbol]
        gap = max(Decimal("0"), Decimal(per_symbol_target_krw) - current)
        desired = min(gap, remaining_budget, Decimal(per_symbol_target_krw))
        desired_krw = int(desired.quantize(Decimal("1"), rounding=ROUND_DOWN))
        if desired_krw < min_order_krw:
            continue
        buys.append(
            {
                "rank": target.rank,
                "symbol": target.symbol,
                "currentValueKrw": int(current.quantize(Decimal("1"), rounding=ROUND_DOWN)),
                "targetValueKrw": per_symbol_target_krw,
                "orderKrw": desired_krw,
                "modelScore": target.model_score,
            }
        )
        remaining_budget -= Decimal(desired_krw)

    return {
        "targetSymbols": target_symbols,
        "sells": [],
        "buys": buys,
        "ignoredNonUsHoldings": sorted(set(ignored_non_us)),
        "phase": "BUY_UNDERWEIGHTS" if buys else "IN_SYNC",
        "currentTargetValueKrw": int(current_total.quantize(Decimal("1"), rounding=ROUND_DOWN)),
        "remainingBudgetKrw": int(remaining_budget.quantize(Decimal("1"), rounding=ROUND_DOWN)),
    }


def _krw_to_usd_amount(order_krw: int, fx_usd_krw: Decimal) -> Decimal:
    if order_krw <= 0 or fx_usd_krw <= 0:
        return Decimal("0")
    return (Decimal(order_krw) / fx_usd_krw).quantize(Decimal("0.01"), rounding=ROUND_DOWN)


async def main_async() -> int:
    load_dotenv(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"), override=True)

    if not _bool(os.environ.get("AUTO_TRADE_ENABLED", "false")):
        print("AUTO_TRADE_DISABLED_US_TOP6")
        return 0

    mode = os.environ.get("AUTO_TRADE_EXECUTION_MODE", "DRY_RUN").strip().upper()
    if mode not in {"DRY_RUN", "LIVE"}:
        raise RuntimeError("AUTO_TRADE_EXECUTION_MODE must be DRY_RUN or LIVE")

    if os.environ.get("AUTO_TRADE_MARKET", "US").strip().upper() != "US":
        raise RuntimeError("AUTO_TRADE_MARKET must be US")
    if os.environ.get("AUTO_TRADE_PORTFOLIO_MODE", "R5_1_TOP6").strip().upper() != "R5_1_TOP6":
        raise RuntimeError("AUTO_TRADE_PORTFOLIO_MODE must be R5_1_TOP6")

    database_url = os.environ.get("DATABASE_URL_WRITER")
    if not database_url:
        raise RuntimeError("DATABASE_URL_WRITER is missing")

    max_positions = int(os.environ.get("AUTO_TRADE_MAX_POSITIONS", "6"))
    per_symbol_target_krw = int(os.environ.get("AUTO_TRADE_TARGET_PER_SYMBOL_KRW", "5000"))
    portfolio_limit_krw = int(os.environ.get("AUTO_TRADE_PORTFOLIO_LIMIT_KRW", "30000"))
    min_order_krw = int(os.environ.get("AUTO_TRADE_MIN_ORDER_KRW", "1000"))
    max_signal_age = int(os.environ.get("AUTO_TRADE_MAX_SIGNAL_AGE_MINUTES", "90"))

    if max_positions != 6:
        raise RuntimeError("AUTO_TRADE_MAX_POSITIONS must remain 6 for this micro profile")
    if per_symbol_target_krw > 5000:
        raise RuntimeError("AUTO_TRADE_TARGET_PER_SYMBOL_KRW cannot exceed 5000")
    if portfolio_limit_krw > 30000:
        raise RuntimeError("AUTO_TRADE_PORTFOLIO_LIMIT_KRW cannot exceed 30000")
    if per_symbol_target_krw * max_positions > portfolio_limit_krw:
        raise RuntimeError("configured Top-6 target exceeds total portfolio limit")

    settings = Settings()
    if settings.max_single_order_krw > 5000:
        raise RuntimeError("MAX_SINGLE_ORDER_KRW safety invariant exceeded")
    if settings.live_micro_total_limit_krw > 30000:
        raise RuntimeError("LIVE_MICRO_TOTAL_LIMIT_KRW safety invariant exceeded")

    # Do not mix the legacy one-position state machine with the Top-6 basket.
    legacy_active = ManagedPositionStore(settings.state_db_path).active()
    if legacy_active:
        print(
            "LEGACY_MANAGED_POSITION_ACTIVE",
            json.dumps(legacy_active, ensure_ascii=False, default=str),
        )
        return 2

    run_id, data_as_of, targets = load_target_basket(
        database_url,
        max_positions=max_positions,
        max_age_minutes=max_signal_age,
    )

    client = TossClient(settings)
    window_open, window_info = await us_fractional_order_window(client)
    holdings = _holding_items(await client.holdings())
    open_orders = _open_order_items(await client.orders("OPEN"))
    fx_payload = unwrap(await client.exchange_rate("USD", "KRW")) or {}
    fx = _decimal(fx_payload.get("rate"))
    if fx <= 0:
        raise RuntimeError("USD/KRW exchange rate missing")

    plan = build_rebalance_plan(
        targets=targets,
        holdings=holdings,
        fx_usd_krw=fx,
        per_symbol_target_krw=per_symbol_target_krw,
        portfolio_limit_krw=portfolio_limit_krw,
        min_order_krw=min_order_krw,
    )

    report = {
        "executionMode": mode,
        "market": MARKET,
        "portfolioMode": "R5_1_TOP6",
        "modelVersion": MODEL_VERSION,
        "runId": run_id,
        "dataAsOf": data_as_of,
        "targets": [
            {
                "rank": x.rank,
                "symbol": x.symbol,
                "modelScore": x.model_score,
                "referencePrice": x.reference_price,
            }
            for x in targets
        ],
        "maxPositions": max_positions,
        "perSymbolTargetKrw": per_symbol_target_krw,
        "portfolioLimitKrw": portfolio_limit_krw,
        "fxUsdKrw": str(fx),
        "openOrderCount": len(open_orders),
        "usFractionalOrderWindowOpen": window_open,
        "marketWindow": window_info,
        "liveGateOpen": settings.live_gate_open,
        "plan": plan,
    }

    if open_orders:
        report["action"] = "WAIT_OPEN_ORDERS"
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0

    if mode == "DRY_RUN":
        report["action"] = "DRY_RUN_PLAN_ONLY"
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0

    if not settings.live_gate_open:
        report["action"] = "LIVE_GATE_CLOSED"
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 2
    if not window_open:
        report["action"] = "US_FRACTIONAL_ORDER_WINDOW_CLOSED"
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0

    submitted = []

    # Phase 1: risk-reducing exits only. Never buy in the same invocation.
    for sell in plan["sells"]:
        symbol = sell["symbol"]
        request = SimpleNamespace(
            client_order_id=_client_order_id(run_id, symbol, "SELL"),
            symbol=symbol,
            side="SELL",
            order_type="MARKET",
            time_in_force="DAY",
            quantity=sell["quantity"],
            order_amount=None,
            price=None,
        )
        result = await execute_order(settings, request, risk_reducing_exit=True)
        submitted.append({"symbol": symbol, "side": "SELL", "result": result})

    if submitted:
        report["action"] = "SELL_NON_TARGETS_SUBMITTED"
        report["submitted"] = submitted
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0

    # Phase 2: fill underweight Top-6 slots, never above 5k/order or 30k basket.
    buying_power_usd = unwrap(await client.buying_power("USD")) or {}
    buying_power_krw = unwrap(await client.buying_power("KRW")) or {}
    cash_usd = _decimal(buying_power_usd.get("cashBuyingPower"))
    cash_krw = _decimal(buying_power_krw.get("cashBuyingPower"))

    for buy in plan["buys"]:
        order_krw = int(buy["orderKrw"])
        amount_usd = _krw_to_usd_amount(order_krw, fx)
        estimated_krw = int((amount_usd * fx).quantize(Decimal("1"), rounding=ROUND_CEILING))
        if amount_usd < Decimal(os.environ.get("AUTO_TRADE_MIN_ORDER_USD", "1")):
            submitted.append(
                {
                    "symbol": buy["symbol"],
                    "side": "BUY",
                    "skipped": "BELOW_MIN_USD_ORDER",
                    "orderKrw": order_krw,
                }
            )
            continue
        if cash_usd < amount_usd and cash_krw < Decimal(estimated_krw):
            submitted.append(
                {
                    "symbol": buy["symbol"],
                    "side": "BUY",
                    "skipped": "INSUFFICIENT_BUYING_POWER",
                    "orderKrw": order_krw,
                }
            )
            continue

        request = SimpleNamespace(
            client_order_id=_client_order_id(run_id, buy["symbol"], "BUY"),
            symbol=buy["symbol"],
            side="BUY",
            order_type="MARKET",
            time_in_force="DAY",
            quantity=None,
            order_amount=str(amount_usd),
            price=None,
        )
        result = await execute_order(settings, request)
        submitted.append({"symbol": buy["symbol"], "side": "BUY", "result": result})
        if result.get("allowed"):
            if result.get("fundingCurrency") == "KRW":
                cash_krw = max(Decimal("0"), cash_krw - Decimal(result["estimatedNotionalKrw"]))
            else:
                cash_usd = max(Decimal("0"), cash_usd - amount_usd)

    report["action"] = "BUY_REBALANCE_COMPLETE"
    report["submitted"] = submitted
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
