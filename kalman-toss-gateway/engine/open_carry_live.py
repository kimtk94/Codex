"""Guarded LIVE executor for a two-step early-session carry entry.

Contract
--------
- 09:30 ET: capture the prior session's final eligible R5.1 Top1 and open price.
- 09:35 ET: buy KRW 5,000 only when score confidence passes and first-5m
  momentum is positive.
- 09:40 ET: add KRW 5,000 only when leg 1 is OPEN and price has not weakened
  versus 09:35.
- 09:45 ET: fallback for leg 2 only when 09:40 was missed/deferred. A completed
  failed 09:40 decision is never retried.
- Maximum OPEN_CARRY exposure created by this executor is KRW 10,000.
- Every broker BUY remains capped at KRW 5,000.

This path is fail-closed and requires an explicit confirmation token in
addition to the existing LIVE trading gates.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv

from app.config import Settings
from app.executor import TradeLedger, execute_order
from app.managed_positions import ManagedPositionStore
from app.market_guard import unwrap, us_fractional_order_window
from app.toss_client import TossClient
from engine.auto_trade import (
    QTY_TOLERANCE,
    TARGET_EXIT_BUCKETS,
    _entry_exit_window_check,
    _exit_priority_positions,
    _exit_priority_summary,
    _has_open_buy_order,
    _holding_items,
    _open_order_items,
    _symbol_position_quantity,
)
from engine.open_carry_shadow import (
    NY,
    _last_price,
    _latest_prior_signal,
    _session_open_utc,
)
from engine.open_carry_policy import (
    CHUNK_KRW,
    MAX_ENTRIES,
    STRATEGY,
    TARGET_KRW,
    evaluate_leg1,
    evaluate_leg2,
    validate_execution_contract,
)
from engine.r5_conditional_live import (
    POLICY,
    _conditional_client_order_id,
    _order_usd,
    _rank_context_from_same_run,
)

CONFIRM = "CONFIRM_OPEN_CARRY_5000X2"


def _state_path() -> Path:
    return Path(
        os.environ.get(
            "OPEN_CARRY_LIVE_STATE_PATH",
            "/opt/kalman/state/open_carry_live.json",
        )
    )


def _load_state() -> dict:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_state(payload: dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _enabled() -> bool:
    return os.environ.get("OPEN_CARRY_LIVE_ENABLED", "false").strip().lower() == "true"


def _validate_contract(settings: Settings) -> tuple[bool, str]:
    if not _enabled():
        return False, "OPEN_CARRY_LIVE_DISABLED"
    if os.environ.get("OPEN_CARRY_LIVE_CONFIRM", "") != CONFIRM:
        return False, "OPEN_CARRY_CONFIRMATION_MISSING"
    if os.environ.get("AUTO_TRADE_ENABLED", "false").strip().lower() != "true":
        return False, "AUTO_TRADE_DISABLED"
    if os.environ.get("AUTO_TRADE_EXECUTION_MODE", "").strip().upper() != "LIVE":
        return False, "OPEN_CARRY_REQUIRES_LIVE"
    if os.environ.get("AUTO_TRADE_SIGNAL_POLICY", "").strip().upper() != POLICY:
        return False, "OPEN_CARRY_POLICY_MISMATCH"
    if os.environ.get("AUTO_TRADE_STRATEGY_VERSION", "").strip() != STRATEGY:
        return False, "OPEN_CARRY_STRATEGY_MISMATCH"

    order_krw = int(os.environ.get("OPEN_CARRY_ORDER_KRW", str(CHUNK_KRW)) or CHUNK_KRW)
    total_krw = int(os.environ.get("OPEN_CARRY_MAX_TOTAL_KRW", str(TARGET_KRW)) or TARGET_KRW)
    max_entries = int(os.environ.get("OPEN_CARRY_MAX_ENTRIES", str(MAX_ENTRIES)) or MAX_ENTRIES)
    contract_ok, contract_reason = validate_execution_contract(
        order_krw=order_krw,
        total_krw=total_krw,
        max_entries=max_entries,
        max_single_order_krw=int(settings.max_single_order_krw),
    )
    if not contract_ok:
        return False, contract_reason
    if not settings.live_gate_open:
        return False, "LIVE_GATE_CLOSED"
    return True, "PASS"


def _run_id(session: str, source_run_id: str) -> str:
    return f"open-carry-{session}-{source_run_id}"


def _telemetry(
    *,
    state: dict,
    leg: int,
    signal: dict,
    rank1_score: float | None,
    momentum: float | None = None,
    continuation: float | None = None,
) -> dict:
    return {
        "execution_mode": "LIVE",
        "signal_policy": "OPEN_CARRY_5000X2",
        "strategy_version": STRATEGY,
        "source_run_id": signal["run_id"],
        "source_signal_as_of": signal["as_of"].isoformat(),
        "open_carry_session_et": state["session_date_et"],
        "open_carry_leg": leg,
        "rank1_symbol": signal["symbol"],
        "rank1_score": rank1_score,
        "open_price": state.get("open_price"),
        "price_5m": state.get("price_5m"),
        "momentum_5m": momentum,
        "continuation_5m": continuation,
        "execution_chunk_krw": CHUNK_KRW,
        "open_carry_max_total_krw": TARGET_KRW,
        "max_entries_per_symbol": 2,
    }


async def _cash_context(client: TossClient) -> tuple[Decimal, Decimal]:
    buying_power = unwrap(await client.buying_power("USD")) or {}
    cash_usd = Decimal(str(buying_power.get("cashBuyingPower") or "0"))
    fx_payload = unwrap(await client.exchange_rate("USD", "KRW")) or {}
    usd_krw = Decimal(str(fx_payload.get("rate") or "0"))
    reserve = Decimal(os.environ.get("AUTO_TRADE_CASH_RESERVE_USD", "0"))
    return max(Decimal("0"), cash_usd - reserve), usd_krw


async def main_async() -> int:
    load_dotenv(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"), override=True)
    now_utc = datetime.now(timezone.utc)
    now_ny = now_utc.astimezone(NY)
    hm = (now_ny.hour, now_ny.minute)
    if hm not in {(9, 30), (9, 35), (9, 40), (9, 45)}:
        return 0

    settings = Settings()
    contract_ok, contract_reason = _validate_contract(settings)
    if not contract_ok:
        print(f"OPEN_CARRY_LIVE_SKIP reason={contract_reason}")
        return 0

    db_url = os.environ.get("DATABASE_URL_WRITER") or os.environ.get("DATABASE_URL")
    if not db_url:
        print("OPEN_CARRY_LIVE_SKIP reason=NO_DATABASE_URL")
        return 0

    client = TossClient(settings)
    window_open, window_info = await us_fractional_order_window(client)
    if not window_open:
        print("OPEN_CARRY_LIVE_SKIP reason=MARKET_WINDOW_CLOSED")
        return 0

    signal = _latest_prior_signal(db_url, _session_open_utc(now_ny))
    if not signal:
        print("OPEN_CARRY_LIVE_SKIP reason=NO_PRIOR_SIGNAL")
        return 0

    rank1_score, rank2_symbol, rank2_score = _rank_context_from_same_run(signal)
    threshold = float(
        os.environ.get(
            "AUTO_TRADE_CONDITIONAL_CONFIDENCE_THRESHOLD",
            "0.00041106678948450823",
        )
    )
    symbol = str(signal["symbol"]).upper()
    session = now_ny.date().isoformat()
    state = _load_state()

    if hm == (9, 30):
        price = await _last_price(client, symbol)
        state = {
            "schema_version": "kalman-open-carry-live-v1",
            "mode": "LIVE_GUARDED",
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
            "leg1": None,
            "leg2": None,
        }
        _save_state(state)
        print(
            json.dumps(
                {
                    "status": "OPEN_CARRY_LIVE_BASELINE_CAPTURED",
                    "symbol": symbol,
                    "openPrice": str(price),
                    "targetKrw": TARGET_KRW,
                },
                ensure_ascii=False,
            )
        )
        return 0

    if (
        state.get("session_date_et") != session
        or state.get("source_run_id") != signal["run_id"]
        or state.get("symbol") != symbol
    ):
        print("OPEN_CARRY_LIVE_SKIP reason=NO_MATCHING_0930_BASELINE")
        return 0

    store = ManagedPositionStore(settings.state_db_path)
    active = store.active()
    exit_priority = _exit_priority_positions(active)
    if exit_priority:
        print(
            json.dumps(
                {
                    "executionAttempted": False,
                    "reason": "OPEN_CARRY_BLOCKED_PENDING_EXIT_PRIORITY",
                    "exitPriorityPositions": _exit_priority_summary(exit_priority),
                },
                ensure_ascii=False,
                default=str,
            )
        )
        return 0

    window_ok, window_detail = _entry_exit_window_check(
        window_info,
        anchor_signal_as_of=now_utc,
        strategy_version=None,
        target_exit_buckets=TARGET_EXIT_BUCKETS,
    )
    if not window_ok:
        print(
            json.dumps(
                {
                    "executionAttempted": False,
                    "reason": "OPEN_CARRY_BLOCKED_FRIDAY_FLAT",
                    "fridayFlatGate": window_detail,
                },
                ensure_ascii=False,
                default=str,
            )
        )
        return 0

    holdings = _holding_items(await client.holdings())
    open_orders = _open_order_items(await client.orders("OPEN"))
    if _has_open_buy_order(open_orders, symbol):
        print("OPEN_CARRY_LIVE_SKIP reason=OPEN_BUY_ORDER_EXISTS")
        return 0

    price = await _last_price(client, symbol)
    max_active = int(os.environ.get("AUTO_TRADE_MAX_ACTIVE_POSITIONS", "3") or 3)

    if hm == (9, 35):
        if state.get("leg1") is not None:
            print("OPEN_CARRY_LIVE_SKIP reason=LEG1_ALREADY_EVALUATED")
            return 0

        ok, momentum, reason = evaluate_leg1(
            rank1_score,
            threshold,
            Decimal(str(state["open_price"])),
            price,
        )
        state["price_5m"] = str(price)
        if not ok:
            state["leg1"] = {
                "evaluated_at": now_ny.isoformat(),
                "eligible": False,
                "status": "REJECTED",
                "reason": reason,
                "momentum_5m": momentum,
            }
            _save_state(state)
            print(
                json.dumps(
                    {"status": "OPEN_CARRY_LEG1_REJECTED", "symbol": symbol, **state["leg1"]},
                    ensure_ascii=False,
                    default=str,
                )
            )
            return 0

        if len(active) >= max_active:
            print("OPEN_CARRY_LIVE_SKIP reason=MAX_ACTIVE_POSITIONS_REACHED")
            return 0
        if store.active_for_symbol(symbol):
            print("OPEN_CARRY_LIVE_SKIP reason=SAME_SYMBOL_ALREADY_ACTIVE")
            return 0
        if _symbol_position_quantity(holdings, symbol) > 0:
            print("OPEN_CARRY_LIVE_SKIP reason=UNMANAGED_BROKER_POSITION")
            return 0

        cash_usd, usd_krw = await _cash_context(client)
        amount_usd = _order_usd(CHUNK_KRW, usd_krw, cash_usd)
        if amount_usd is None:
            print("OPEN_CARRY_LIVE_SKIP reason=INSUFFICIENT_CASH")
            return 0

        open_run_id = _run_id(session, str(signal["run_id"]))
        client_order_id = _conditional_client_order_id(
            open_run_id,
            symbol,
            now_utc,
            1,
        )
        reserved, position = store.reserve_entry(
            run_id=open_run_id,
            symbol=symbol,
            strategy_version=STRATEGY,
            signal_as_of=now_utc.isoformat(),
            client_order_id=client_order_id,
            target_exit_buckets=TARGET_EXIT_BUCKETS,
        )
        if not reserved or not position:
            print("OPEN_CARRY_LIVE_SKIP reason=LEG1_RESERVATION_FAILED")
            return 0

        request = SimpleNamespace(
            client_order_id=client_order_id,
            symbol=symbol,
            side="BUY",
            order_type="MARKET",
            time_in_force="DAY",
            quantity=None,
            order_amount=str(amount_usd),
            price=None,
        )
        try:
            result = await execute_order(settings, request)
        except Exception as exc:
            guard = TradeLedger(settings.state_db_path).get(client_order_id)
            if guard and guard.get("status") == "AMBIGUOUS":
                store.mark_ambiguous_entry(
                    position["position_id"],
                    f"open carry leg1 ambiguous: {guard.get('error') or exc}",
                )
            else:
                store.mark_entry_aborted(
                    position["position_id"],
                    f"{type(exc).__name__}: {exc}",
                )
            raise

        if not result.get("allowed"):
            store.mark_entry_aborted(
                position["position_id"],
                f"open carry leg1 blocked: {result.get('reason')}",
            )
            state["leg1"] = {
                "evaluated_at": now_ny.isoformat(),
                "eligible": True,
                "status": "BLOCKED",
                "reason": result.get("reason"),
                "momentum_5m": momentum,
            }
            _save_state(state)
            print(json.dumps({"status": "OPEN_CARRY_LEG1_BLOCKED", "symbol": symbol, **state["leg1"]}, ensure_ascii=False, default=str))
            return 0

        TradeLedger(settings.state_db_path).patch_telemetry(
            client_order_id,
            {"signal_context": _telemetry(state=state, leg=1, signal=signal, rank1_score=rank1_score, momentum=momentum)},
        )
        order_id = result.get("orderId")
        if not order_id:
            store.mark_ambiguous_entry(position["position_id"], "open carry leg1 returned no orderId")
            state["leg1"] = {
                "evaluated_at": now_ny.isoformat(),
                "eligible": True,
                "status": "AMBIGUOUS_NO_ORDER_ID",
                "momentum_5m": momentum,
                "position_id": position["position_id"],
                "client_order_id": client_order_id,
            }
            _save_state(state)
            print(json.dumps({"status": "OPEN_CARRY_LEG1_AMBIGUOUS", "symbol": symbol, **state["leg1"]}, ensure_ascii=False, default=str))
            return 0

        store.mark_entry_submitted(position["position_id"], order_id)
        state["leg1"] = {
            "evaluated_at": now_ny.isoformat(),
            "eligible": True,
            "status": "SUBMITTED",
            "reason": "PASS",
            "momentum_5m": momentum,
            "target_krw": CHUNK_KRW,
            "position_id": position["position_id"],
            "client_order_id": client_order_id,
            "order_id": order_id,
        }
        _save_state(state)
        print(json.dumps({"status": "OPEN_CARRY_LEG1_SUBMITTED", "symbol": symbol, **state["leg1"]}, ensure_ascii=False, default=str))
        return 0

    if state.get("leg2") is not None:
        print("OPEN_CARRY_LIVE_SKIP reason=LEG2_ALREADY_EVALUATED")
        return 0

    leg1 = state.get("leg1") or {}
    if leg1.get("status") != "SUBMITTED":
        print("OPEN_CARRY_LIVE_SKIP reason=LEG1_NOT_SUBMITTED")
        return 0

    position = store.active_for_symbol(symbol)
    if not position or position.get("position_id") != leg1.get("position_id"):
        print("OPEN_CARRY_LIVE_DEFER reason=LEG1_POSITION_NOT_RECONCILED")
        return 0
    if position.get("state") != "OPEN":
        print(f"OPEN_CARRY_LIVE_DEFER reason=LEG1_POSITION_STATE_{position.get('state')}")
        return 0
    if int(position.get("entry_count") or 0) != 1:
        print("OPEN_CARRY_LIVE_SKIP reason=OPEN_CARRY_ENTRY_COUNT_NOT_ONE")
        return 0
    if position.get("exit_pending_reason"):
        print("OPEN_CARRY_LIVE_SKIP reason=EXIT_PENDING")
        return 0

    price_5m = Decimal(str(state.get("price_5m") or "0"))
    ok, continuation, reason = evaluate_leg2(True, price_5m, price)
    if not ok:
        state["price_leg2_check"] = str(price)
        state["leg2"] = {
            "evaluated_at": now_ny.isoformat(),
            "eligible": False,
            "status": "REJECTED",
            "reason": reason,
            "continuation_5m": continuation,
        }
        _save_state(state)
        print(json.dumps({"status": "OPEN_CARRY_LEG2_REJECTED", "symbol": symbol, **state["leg2"]}, ensure_ascii=False, default=str))
        return 0

    broker_qty = _symbol_position_quantity(holdings, symbol)
    managed_qty = Decimal(str(position.get("remaining_quantity") or "0"))
    if (
        broker_qty <= 0
        or managed_qty <= 0
        or abs(broker_qty - managed_qty) > QTY_TOLERANCE
    ):
        print(
            json.dumps(
                {
                    "executionAttempted": False,
                    "reason": "OPEN_CARRY_BROKER_QUANTITY_MISMATCH",
                    "brokerQuantity": str(broker_qty),
                    "managedQuantity": str(managed_qty),
                },
                ensure_ascii=False,
            )
        )
        return 0

    cash_usd, usd_krw = await _cash_context(client)
    amount_usd = _order_usd(CHUNK_KRW, usd_krw, cash_usd)
    if amount_usd is None:
        print("OPEN_CARRY_LIVE_SKIP reason=INSUFFICIENT_CASH")
        return 0

    open_run_id = _run_id(session, str(signal["run_id"]))
    client_order_id = _conditional_client_order_id(
        open_run_id,
        symbol,
        now_utc,
        2,
    )
    reserved, updated = store.reserve_add_on(
        position["position_id"],
        run_id=open_run_id,
        signal_as_of=now_utc.isoformat(),
        client_order_id=client_order_id,
        target_krw=str(CHUNK_KRW),
        max_entries=2,
        min_gap_minutes=5,
    )
    if not reserved or not updated:
        print("OPEN_CARRY_LIVE_SKIP reason=LEG2_RESERVATION_FAILED")
        return 0

    request = SimpleNamespace(
        client_order_id=client_order_id,
        symbol=symbol,
        side="BUY",
        order_type="MARKET",
        time_in_force="DAY",
        quantity=None,
        order_amount=str(amount_usd),
        price=None,
    )
    try:
        result = await execute_order(settings, request)
    except Exception as exc:
        guard = TradeLedger(settings.state_db_path).get(client_order_id)
        if guard and guard.get("status") == "AMBIGUOUS":
            store.mark_ambiguous_add_on(
                position["position_id"],
                f"open carry leg2 ambiguous: {guard.get('error') or exc}",
            )
        else:
            store.release_add_on(
                position["position_id"],
                f"{type(exc).__name__}: {exc}",
            )
        raise

    if not result.get("allowed"):
        store.release_add_on(
            position["position_id"],
            f"open carry leg2 blocked: {result.get('reason')}",
        )
        state["leg2"] = {
            "evaluated_at": now_ny.isoformat(),
            "eligible": True,
            "status": "BLOCKED",
            "reason": result.get("reason"),
            "continuation_5m": continuation,
        }
        _save_state(state)
        print(json.dumps({"status": "OPEN_CARRY_LEG2_BLOCKED", "symbol": symbol, **state["leg2"]}, ensure_ascii=False, default=str))
        return 0

    TradeLedger(settings.state_db_path).patch_telemetry(
        client_order_id,
        {"signal_context": _telemetry(state=state, leg=2, signal=signal, rank1_score=rank1_score, continuation=continuation)},
    )
    order_id = result.get("orderId")
    if not order_id:
        store.mark_ambiguous_add_on(position["position_id"], "open carry leg2 returned no orderId")
        state["leg2"] = {
            "evaluated_at": now_ny.isoformat(),
            "eligible": True,
            "status": "AMBIGUOUS_NO_ORDER_ID",
            "continuation_5m": continuation,
            "client_order_id": client_order_id,
        }
        _save_state(state)
        print(json.dumps({"status": "OPEN_CARRY_LEG2_AMBIGUOUS", "symbol": symbol, **state["leg2"]}, ensure_ascii=False, default=str))
        return 0

    store.mark_add_on_submitted(position["position_id"], order_id)
    state["price_leg2_check"] = str(price)
    state["leg2"] = {
        "evaluated_at": now_ny.isoformat(),
        "eligible": True,
        "status": "SUBMITTED",
        "reason": "PASS",
        "continuation_5m": continuation,
        "target_krw": CHUNK_KRW,
        "target_total_krw_if_both": TARGET_KRW,
        "position_id": position["position_id"],
        "client_order_id": client_order_id,
        "order_id": order_id,
    }
    _save_state(state)
    print(json.dumps({"status": "OPEN_CARRY_LEG2_SUBMITTED", "symbol": symbol, **state["leg2"]}, ensure_ascii=False, default=str))
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
