from __future__ import annotations

import json
import os
import sqlite3
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb
from dotenv import load_dotenv
from engine.broker_status_evidence import historical_broker_fill
from engine.order_position_link import explicit_buy_link


def _rows(conn: sqlite3.Connection, sql: str) -> list[dict]:
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(sql).fetchall()]


def _dec(v):
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


def _execution_status(
    order: dict, pos: dict | None, leg: str | None,
    telemetry: dict | None = None,
) -> tuple[str | None, str]:
    """Prefer managed position, then verified historical broker fill, then order guard.

    Broker telemetry is historical evidence, not an assertion about current open orders.
    """
    guard_status = str(order.get("status") or "").upper() or None
    if not pos or leg not in {"ENTRY", "EXIT"}:
        if guard_status == "SUBMITTED" and historical_broker_fill(order, telemetry):
            return "FILLED", "broker_order_telemetry"
        return guard_status, "order_guard"

    status_key = "entry_status" if leg == "ENTRY" else "exit_status"
    reconciled_status = str(pos.get(status_key) or "").upper() or None
    if reconciled_status:
        return reconciled_status, "managed_position"
    if guard_status == "SUBMITTED" and historical_broker_fill(order, telemetry):
        return "FILLED", "broker_order_telemetry"
    return guard_status, "order_guard"


def _json_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _execution_quality(side: str | None, average_fill, telemetry: dict) -> dict:
    broker = telemetry.get("broker_order") if isinstance(telemetry.get("broker_order"), dict) else {}
    quote = telemetry.get("pretrade_quote") if isinstance(telemetry.get("pretrade_quote"), dict) else {}
    submit = telemetry.get("submit") if isinstance(telemetry.get("submit"), dict) else {}
    submit_meta = submit.get("response_meta") if isinstance(submit.get("response_meta"), dict) else {}
    broker_meta = broker.get("response_meta") if isinstance(broker.get("response_meta"), dict) else {}

    fill_price = _dec(average_fill) or _dec(broker.get("average_filled_price"))
    fill_quantity = _dec(broker.get("filled_quantity"))
    exact_notional = None
    if fill_price is not None and fill_quantity is not None and fill_quantity > 0:
        exact_notional = fill_price * fill_quantity

    side = str(side or "").upper()
    reference_price = _dec(quote.get("best_ask" if side == "BUY" else "best_bid" if side == "SELL" else ""))
    slippage_bps = None
    if fill_price is not None and reference_price is not None and reference_price > 0:
        if side == "BUY":
            slippage_bps = (fill_price - reference_price) / reference_price * Decimal("10000")
        elif side == "SELL":
            slippage_bps = (reference_price - fill_price) / reference_price * Decimal("10000")

    filled_amount = _dec(broker.get("filled_amount"))
    # Never silently promote MISSING, NaN, infinity or negative fees to zero.
    # An explicit 0 is valid; a missing field is not a zero fee.
    commission = _dec(broker.get("commission"))
    tax = _dec(broker.get("tax"))
    commission = commission if commission is not None and commission.is_finite() and commission >= 0 else None
    tax = tax if tax is not None and tax.is_finite() and tax >= 0 else None
    cost_basis = exact_notional if exact_notional is not None and exact_notional > 0 else filled_amount
    cost_bps = None
    if commission is not None and tax is not None and cost_basis is not None and cost_basis > 0:
        cost_bps = (commission + tax) / cost_basis * Decimal("10000")

    def n(value):
        value = _dec(value)
        return float(value) if value is not None else None

    def meta_value(key):
        value = submit_meta.get(key)
        return value if value is not None else broker_meta.get(key)

    return {
        "currency": broker.get("currency") or quote.get("currency"),
        "broker_currency": broker.get("currency"),
        "fee_currency": broker.get("fee_currency"),
        "quote_timestamp": quote.get("timestamp"),
        "best_bid": n(quote.get("best_bid")),
        "best_ask": n(quote.get("best_ask")),
        "spread_bps": n(quote.get("spread_bps")),
        "reference_price": float(reference_price) if reference_price is not None else None,
        "slippage_bps": float(slippage_bps) if slippage_bps is not None else None,
        "filled_quantity": float(fill_quantity) if fill_quantity is not None else None,
        "average_filled_price": float(fill_price) if fill_price is not None else None,
        "filled_amount": float(filled_amount) if filled_amount is not None else None,
        "exact_notional": float(exact_notional) if exact_notional is not None else None,
        "commission": float(commission) if commission is not None else None,
        "tax": float(tax) if tax is not None else None,
        "cost_bps": float(cost_bps) if cost_bps is not None else None,
        "broker_ordered_at": broker.get("ordered_at"),
        "broker_filled_at": broker.get("filled_at"),
        "broker_fill_latency_ms": broker.get("broker_fill_latency_ms"),
        "submit_http_latency_ms": submit.get("http_latency_ms"),
        "rate_limit_limit": meta_value("rate_limit_limit"),
        "rate_limit_remaining": meta_value("rate_limit_remaining"),
        "rate_limit_reset_seconds": meta_value("rate_limit_reset_seconds"),
        "retry_after_seconds": meta_value("retry_after_seconds"),
    }


def _round_trip_quality(
    entry_quality: dict, exit_quality: dict, *, position: dict | None = None,
) -> dict:
    """Net return requires full entry AND exit execution/fee coverage.

    An add-on changes managed position quantities, but entry telemetry usually
    refers only to the first entry order. Treat incomplete coverage as UNKNOWN
    rather than calculating fictitious multi-bagger net returns.
    """
    if position is not None:
        if str(position.get("state") or "").upper() != "CLOSED":
            return {"quality_status": "POSITION_NOT_CLOSED", "net_return": None}
        expected_entry = _dec(position.get("entry_filled_quantity"))
        remaining = _dec(position.get("remaining_quantity"))
        expected_exit = (
            expected_entry - remaining
            if expected_entry is not None and remaining is not None
            else None
        )
        observed_entry = _dec(entry_quality.get("filled_quantity"))
        observed_exit = _dec(exit_quality.get("filled_quantity"))
        complete = (
            expected_entry is not None and expected_entry > 0
            and expected_exit is not None and expected_exit > 0
            and observed_entry is not None and observed_exit is not None
            and abs(expected_entry - observed_entry) <= Decimal("0.00000001")
            and abs(expected_exit - observed_exit) <= Decimal("0.00000001")
        )
        if not complete:
            entry_avg = _dec(position.get("entry_avg_fill_price"))
            exit_avg = _dec(position.get("exit_avg_fill_price"))
            gross = (
                exit_avg / entry_avg - Decimal("1")
                if entry_avg is not None and exit_avg is not None and entry_avg > 0
                else None
            )
            return {
                "quality_status": "INCOMPLETE_LEG_COVERAGE",
                "gross_return": float(gross) if gross is not None else None,
                "gross_return_pct": float(gross * 100) if gross is not None else None,
                "net_return": None,
                "net_return_pct": None,
                "round_trip_cost_bps": None,
                "entry_covered_quantity": float(observed_entry) if observed_entry is not None else None,
                "entry_position_quantity": float(expected_entry) if expected_entry is not None else None,
                "exit_covered_quantity": float(observed_exit) if observed_exit is not None else None,
                "exit_position_quantity": float(expected_exit) if expected_exit is not None else None,
            }
    # Net P&L requires explicitly reported fees for EACH leg, plus a proved
    # same-currency fee basis. Currency inferred from quote context is insufficient.
    for q in (entry_quality, exit_quality):
        comm, tax = _dec(q.get("commission")), _dec(q.get("tax"))
        if any(v is None or not v.is_finite() or v < 0 for v in (comm, tax)):
            return {"quality_status": "INCOMPLETE_FEE_EVIDENCE",
                    "net_return": None, "net_return_pct": None,
                    "round_trip_cost_bps": None}
    entry_ccy, exit_ccy = entry_quality.get("broker_currency"), exit_quality.get("broker_currency")
    if (entry_ccy not in ("USD", "KRW") or entry_ccy != exit_ccy
            or entry_quality.get("fee_currency") != entry_ccy
            or exit_quality.get("fee_currency") != exit_ccy):
        return {"quality_status": "UNVERIFIED_FEE_CURRENCY",
                "net_return": None, "net_return_pct": None,
                "round_trip_cost_bps": None}
    entry_amount = _dec(entry_quality.get("exact_notional")) or _dec(entry_quality.get("filled_amount"))
    exit_amount = _dec(exit_quality.get("exact_notional")) or _dec(exit_quality.get("filled_amount"))
    if entry_amount is None or exit_amount is None or entry_amount <= 0:
        return {}
    entry_cost = (_dec(entry_quality.get("commission")) or Decimal("0")) + (_dec(entry_quality.get("tax")) or Decimal("0"))
    exit_cost = (_dec(exit_quality.get("commission")) or Decimal("0")) + (_dec(exit_quality.get("tax")) or Decimal("0"))
    gross_return = exit_amount / entry_amount - Decimal("1")
    net_denominator = entry_amount + entry_cost
    net_return = None
    if net_denominator > 0:
        net_return = (exit_amount - exit_cost) / net_denominator - Decimal("1")
    total_cost = entry_cost + exit_cost
    return {
        "quality_status": "FULL_LEG_COVERAGE",
        "gross_return": float(gross_return),
        "net_return": float(net_return) if net_return is not None else None,
        "gross_return_pct": float(gross_return * Decimal("100")),
        "net_return_pct": float(net_return * Decimal("100")) if net_return is not None else None,
        "total_cost_native": float(total_cost),
        "round_trip_cost_bps": float(total_cost / entry_amount * Decimal("10000")),
    }


def main() -> int:
    load_dotenv(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"), override=True)
    db_url = os.environ.get("DATABASE_URL_WRITER")
    if not db_url:
        raise RuntimeError("DATABASE_URL_WRITER is missing")

    state_db = Path(os.environ.get("TRADING_STATE_DB", "/opt/kalman/state/trading.sqlite3"))
    if not state_db.exists():
        print(json.dumps({"status": "SKIP", "reason": "STATE_DB_MISSING", "path": str(state_db)}))
        return 0

    strategy_default = os.environ.get("AUTO_TRADE_STRATEGY_VERSION", "R5.1_BASE_HGB")
    execution_mode = os.environ.get("AUTO_TRADE_EXECUTION_MODE", "DRY_RUN").upper()
    signal_policy = os.environ.get("AUTO_TRADE_SIGNAL_POLICY", "APPROVED_ONLY").upper()

    with sqlite3.connect(state_db) as local:
        positions = _rows(local, "SELECT * FROM managed_position ORDER BY created_at")
        orders = _rows(local, "SELECT * FROM order_guard ORDER BY created_at")

    orders_by_client = {o.get("client_order_id"): o for o in orders if o.get("client_order_id")}
    pos_by_client = {}
    for p in positions:
        if p.get("entry_client_order_id"):
            pos_by_client[p["entry_client_order_id"]] = (p, "ENTRY")
        if p.get("exit_client_order_id"):
            pos_by_client[p["exit_client_order_id"]] = (p, "EXIT")

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            for p in positions:
                entry_filled = _dec(p.get("entry_filled_quantity"))
                remaining = _dec(p.get("remaining_quantity"))
                exit_filled = None
                if entry_filled is not None and remaining is not None:
                    exit_filled = max(Decimal("0"), entry_filled - remaining)

                entry_order = orders_by_client.get(p.get("entry_client_order_id")) or {}
                exit_order = orders_by_client.get(p.get("exit_client_order_id")) or {}
                entry_telemetry = _json_dict(entry_order.get("telemetry_json"))
                exit_telemetry = _json_dict(exit_order.get("telemetry_json"))
                # Execution quality is per broker order. Never multiply the
                # first order's quantity by the aggregate position average.
                entry_quality = _execution_quality("BUY", None, entry_telemetry)
                exit_quality = _execution_quality("SELL", None, exit_telemetry)
                round_trip_quality = _round_trip_quality(entry_quality, exit_quality, position=p)

                cur.execute(
                    """
                    INSERT INTO managed_position_mirror (
                      position_id,run_id,market,symbol,strategy_version,state,
                      entry_signal_as_of,entry_client_order_id,entry_order_id,
                      entry_filled_quantity,entry_average_price,remaining_quantity,
                      target_exit_buckets,exit_client_order_id,exit_order_id,
                      exit_filled_quantity,exit_average_price,exit_reason,note,metadata,
                      first_seen_at,updated_at
                    ) VALUES (
                      %s,%s,'US',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                    )
                    ON CONFLICT (position_id) DO UPDATE SET
                      run_id=EXCLUDED.run_id,
                      symbol=EXCLUDED.symbol,
                      strategy_version=EXCLUDED.strategy_version,
                      state=EXCLUDED.state,
                      entry_signal_as_of=EXCLUDED.entry_signal_as_of,
                      entry_client_order_id=EXCLUDED.entry_client_order_id,
                      entry_order_id=EXCLUDED.entry_order_id,
                      entry_filled_quantity=EXCLUDED.entry_filled_quantity,
                      entry_average_price=EXCLUDED.entry_average_price,
                      remaining_quantity=EXCLUDED.remaining_quantity,
                      target_exit_buckets=EXCLUDED.target_exit_buckets,
                      exit_client_order_id=EXCLUDED.exit_client_order_id,
                      exit_order_id=EXCLUDED.exit_order_id,
                      exit_filled_quantity=EXCLUDED.exit_filled_quantity,
                      exit_average_price=EXCLUDED.exit_average_price,
                      exit_reason=EXCLUDED.exit_reason,
                      note=EXCLUDED.note,
                      metadata=EXCLUDED.metadata,
                      updated_at=EXCLUDED.updated_at
                    """,
                    (
                        p["position_id"],
                        p.get("entry_run_id"),
                        p.get("symbol"),
                        p.get("strategy_version") or strategy_default,
                        p.get("state"),
                        p.get("entry_signal_as_of"),
                        p.get("entry_client_order_id"),
                        p.get("entry_order_id"),
                        entry_filled,
                        _dec(p.get("entry_avg_fill_price")),
                        remaining,
                        p.get("target_exit_buckets"),
                        p.get("exit_client_order_id"),
                        p.get("exit_order_id"),
                        exit_filled,
                        _dec(p.get("exit_avg_fill_price")),
                        p.get("exit_reason"),
                        p.get("note"),
                        Jsonb({
                            "entry_status": p.get("entry_status"),
                            "exit_status": p.get("exit_status"),
                            "exit_attempt": p.get("exit_attempt"),
                            "execution_quality": {
                                "entry": entry_quality,
                                "exit": exit_quality,
                                "round_trip": round_trip_quality,
                            },
                            "source": "local_managed_position",
                        }),
                        p.get("created_at"),
                        p.get("updated_at"),
                    ),
                )

            for o in orders:
                telemetry = _json_dict(o.get("telemetry_json"))
                match = pos_by_client.get(o.get("client_order_id"))
                pos = match[0] if match else None
                leg = match[1] if match else None
                position_link_source = "MANAGED_POSITION_ORDER_ID" if match else None
                if match is None:
                    explicit_link = explicit_buy_link(o, telemetry, positions)
                    if explicit_link.get("status") == "EXPLICIT_LOCAL_LINK":
                        # The contract matches exactly one position; never infer by
                        # symbol/time. This is a LOCAL link, not broker confirmation.
                        pos = next(p for p in positions if p["position_id"] == explicit_link["position_id"])
                        leg = explicit_link["leg"]
                        position_link_source = "EXPLICIT_SIGNAL_CONTEXT"
                # A managed-position total is NOT an individual order's fill.
                # Never duplicate the total initial entry across ADD_ON trades.
                # A broker-order-specific fill is mandatory for event quantities.
                broker_fill = historical_broker_fill(o, telemetry)
                filled = broker_fill["filled_quantity"] if broker_fill else None
                avg = broker_fill["average_filled_price"] if broker_fill else None
                fill_source = "BROKER_ORDER_TELEMETRY" if broker_fill else "UNVERIFIED"

                signal_context = (
                    telemetry.get("signal_context")
                    if isinstance(telemetry.get("signal_context"), dict)
                    else {}
                )
                row_execution_mode = signal_context.get("execution_mode") or execution_mode
                row_signal_policy = signal_context.get("signal_policy") or signal_policy
                row_strategy_version = (
                    pos.get("strategy_version") if pos else None
                ) or signal_context.get("strategy_version") or strategy_default
                # An ADD_ON has its own signal run/time, distinct from initial entry.
                row_run_id = (
                    signal_context.get("run_id") if leg == "ADD_ON" else
                    (pos.get("entry_run_id") if pos else None) or signal_context.get("run_id")
                )
                row_signal_as_of = (
                    signal_context.get("signal_as_of") if leg == "ADD_ON" else
                    (pos.get("entry_signal_as_of") if pos else None) or signal_context.get("signal_as_of")
                )
                execution_quality = _execution_quality(o.get("side"), avg, telemetry)
                execution_status, status_source = _execution_status(o, pos, leg, telemetry)
                reconciled_position_status = None
                if pos and leg == "ENTRY":
                    reconciled_position_status = pos.get("entry_status")
                elif pos and leg == "EXIT":
                    reconciled_position_status = pos.get("exit_status")

                cur.execute(
                    """
                    INSERT INTO trade_execution (
                      client_order_id,broker_order_id,run_id,market,symbol,side,
                      strategy_version,execution_mode,signal_policy,signal_as_of,status,
                      filled_quantity,average_filled_price,estimated_notional_krw,
                      position_id,error,metadata,created_at,updated_at
                    ) VALUES (
                      %s,%s,%s,'US',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()
                    )
                    ON CONFLICT (client_order_id) DO UPDATE SET
                      broker_order_id=EXCLUDED.broker_order_id,
                      run_id=EXCLUDED.run_id,
                      symbol=EXCLUDED.symbol,
                      side=EXCLUDED.side,
                      strategy_version=EXCLUDED.strategy_version,
                      execution_mode=COALESCE(trade_execution.execution_mode, EXCLUDED.execution_mode),
                      signal_policy=COALESCE(trade_execution.signal_policy, EXCLUDED.signal_policy),
                      signal_as_of=COALESCE(trade_execution.signal_as_of, EXCLUDED.signal_as_of),
                      status=EXCLUDED.status,
                      filled_quantity=EXCLUDED.filled_quantity,
                      average_filled_price=EXCLUDED.average_filled_price,
                      estimated_notional_krw=EXCLUDED.estimated_notional_krw,
                      position_id=EXCLUDED.position_id,
                      error=EXCLUDED.error,
                      metadata=EXCLUDED.metadata,
                      updated_at=now()
                    """,
                    (
                        o.get("client_order_id"),
                        o.get("toss_order_id"),
                        row_run_id,
                        o.get("symbol"),
                        o.get("side"),
                        row_strategy_version,
                        row_execution_mode,
                        row_signal_policy,
                        row_signal_as_of,
                        execution_status,
                        filled,
                        avg,
                        o.get("estimated_notional_krw"),
                        pos.get("position_id") if pos else None,
                        o.get("error"),
                        Jsonb({
                            "trade_date_kst": o.get("trade_date_kst"),
                            "local_created_at": o.get("created_at"),
                            "position_leg": leg,
                            "position_link_source": position_link_source,
                            "order_fill_source": fill_source,
                            "exit_reason": pos.get("exit_reason") if pos else None,
                            "order_guard_status": o.get("status"),
                            "reconciled_position_status": reconciled_position_status,
                            "status_source": status_source,
                            "signal_context": signal_context,
                            "execution_telemetry": telemetry,
                            "execution_quality": execution_quality,
                            "source": "local_order_guard",
                        }),
                        o.get("created_at"),
                    ),
                )
        conn.commit()

    print(json.dumps({
        "status": "MIRRORED",
        "positions": len(positions),
        "orders": len(orders),
        "executionMode": execution_mode,
        "signalPolicy": signal_policy,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
